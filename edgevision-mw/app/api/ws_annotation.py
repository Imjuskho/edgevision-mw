from __future__ import annotations

import asyncio
import os
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.ai.live_inference import (
    LIVE_CONF,
    attach_depth_boxes,
    build_annotations,
    maybe_estimate_depth,
    run_engine_detection,
    run_seg_primary_detection,
)
from app.ai.model_inference import get_active_engine
from app.ai.object_tracker import ByteTrack, get_track_config
from app.core.dependencies import get_current_user_ws
from app.core.logging import get_logger
from app.models.enums import ModelType

logger = get_logger("edgevision.ws_annotation")

ws_annotation_router = APIRouter()

TEXT_DETECTION = "text_detection"
VALID_MODEL_TYPES = {e.value for e in ModelType} | {TEXT_DETECTION}
WS_FRAME_BUDGET_MS = int(os.environ.get("WS_FRAME_BUDGET_MS", "500"))


def _run_text_detection(image: np.ndarray) -> list[dict]:
    from app.ai.text_detection import detect_and_ocr

    rgb = image[:, :, ::-1] if image.ndim == 3 else image
    results = detect_and_ocr(rgb)
    annotations = []
    for r in results:
        x1, y1, x2, y2 = r["bbox"]
        text = r.get("text") or "text"
        annotations.append({
            "class_name": text,
            "taxonomy_label": text,
            "confidence": round(r.get("confidence", 0.0), 4),
            "bbox": [x1, y1, x2 - x1, y2 - y1],
            "mask_format": None,
        })
    return annotations


async def _warmup_depth_estimator() -> None:
    """Pre-load depth ONNX session on a background thread."""
    try:

        from app.ai.depth_estimator import get_depth_estimator

        dummy = np.zeros((64, 64, 3), dtype=np.uint8)
        await asyncio.to_thread(get_depth_estimator().estimate_depth_map, dummy)
    except Exception as exc:
        logger.debug("ws_depth_warmup_skipped", error=str(exc))


async def _warmup_face_blurrer() -> None:
    """Pre-load YuNet face detector so first live save is not delayed."""
    try:
        from app.ai.face_privacy import get_face_blurrer

        blurrer = get_face_blurrer()
        if blurrer.is_loaded():
            logger.info("ws_face_blurrer_warm")
    except Exception as exc:
        logger.debug("ws_face_blurrer_warmup_skipped", error=str(exc))


@ws_annotation_router.websocket("/ws/annotate/live")
@ws_annotation_router.websocket("/api/v1/ws/annotate/live")
async def websocket_annotate(websocket: WebSocket, model_type: str = "object_detection"):
    user = await get_current_user_ws(websocket)
    if user is None:
        logger.warning(
            "ws_annotation_unauthenticated",
            origin=websocket.headers.get("origin"),
            path=websocket.scope.get("path"),
            query_params=dict(websocket.query_params),
        )
        response = JSONResponse(
            {"detail": "Missing or invalid websocket token"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        await websocket.send_denial_response(response)
        return

    await websocket.accept()

    if model_type not in VALID_MODEL_TYPES:
        await websocket.send_json({"error": f"Invalid model_type: {model_type}"})
        await websocket.close(code=1003)
        return

    is_text_mode = model_type == TEXT_DETECTION
    mt = None if is_text_mode else ModelType(model_type)

    from app.core.database import async_session

    engine = None
    if not is_text_mode:
        async with async_session() as db:
            engine = await get_active_engine(db, mt)
        if engine is None or not engine.is_loaded():
            await websocket.send_json({"error": "No deployed model available for this model type"})
            await websocket.close(code=1011)
            return

    tracker = ByteTrack(config=get_track_config(model_type), model_type=model_type)
    processing = False
    pending_frame: bytes | None = None
    dropped_frames = 0
    frame_index = 0
    cached_depth: tuple | None = None

    if model_type == ModelType.object_detection.value:
        asyncio.create_task(_warmup_depth_estimator())
        asyncio.create_task(_warmup_face_blurrer())

    logger.info("ws_annotation_connected", model_type=model_type, user_id=str(user.get("sub", "")))

    from app.api.metrics import (
        depth_inference_ms,
        ws_annotate_dropped_total,
        ws_annotate_duration_seconds,
        ws_annotate_frames_total,
    )

    try:
        while True:
            message = await websocket.receive_bytes()

            if not message:
                continue

            if processing:
                dropped_frames += 1
                pending_frame = message
                ws_annotate_dropped_total.labels(model_type=model_type, reason="busy").inc()
                await websocket.send_json({
                    "dropped": True,
                    "busy": True,
                    "model_type": model_type,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                continue

            processing = True
            frame_index += 1
            current_index = frame_index

            async def _process_frame(frame_bytes: bytes, idx: int) -> None:
                nonlocal processing, dropped_frames, pending_frame, cached_depth
                start = time.time()
                try:
                    nparr = np.frombuffer(frame_bytes, dtype=np.uint8)
                    import cv2

                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if image is None:
                        await websocket.send_json({"error": "Failed to decode JPEG"})
                        return

                    if is_text_mode:
                        annotations = await asyncio.to_thread(_run_text_detection, image)
                        duration_ms = round((time.time() - start) * 1000, 1)
                        result = {
                            "annotations": annotations,
                            "inference_ms": duration_ms,
                            "model_type": model_type,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "frame_width": int(image.shape[1]),
                            "frame_height": int(image.shape[0]),
                            "depth_available": False,
                            "dropped": False,
                        }
                        ws_annotate_frames_total.labels(model_type=model_type, status="ok").inc()
                        ws_annotate_duration_seconds.labels(model_type=model_type).observe(duration_ms / 1000)
                        await websocket.send_json(result)
                        return

                    use_seg_primary = model_type == ModelType.object_detection.value

                    def _run_detection():
                        if use_seg_primary:
                            return run_seg_primary_detection(
                                frame_bytes, image, tracker, model_type, LIVE_CONF
                            )
                        return run_engine_detection(
                            engine, image, frame_bytes, tracker, model_type, LIVE_CONF
                        )

                    tracked, raw_detections = await asyncio.to_thread(_run_detection)

                    depth_map = None
                    depth_available = False
                    depth_from_cache = True
                    depth_map, depth_available, depth_from_cache = await asyncio.to_thread(
                        maybe_estimate_depth,
                        image,
                        tracked,
                        model_type,
                        idx,
                        cached_depth,
                    )
                    if depth_map is not None or depth_available:
                        cached_depth = (depth_map, depth_available)
                        if not depth_from_cache:
                            try:
                                from app.ai.depth_estimator import get_depth_estimator

                                depth_ms = get_depth_estimator().last_inference_ms
                                if depth_ms > 0:
                                    depth_inference_ms.observe(depth_ms / 1000)
                            except Exception:
                                pass

                    tracked = attach_depth_boxes(tracked, image, depth_map, depth_available)
                    annotations = build_annotations(tracked)

                    duration_ms = round((time.time() - start) * 1000, 1)

                    result = {
                        "annotations": annotations,
                        "inference_ms": duration_ms,
                        "model_type": model_type,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "frame_width": int(image.shape[1]),
                        "frame_height": int(image.shape[0]),
                        "depth_available": depth_available,
                        "dropped": False,
                    }

                    if duration_ms > WS_FRAME_BUDGET_MS:
                        result["warning"] = "slow_inference"

                    status_label = "slow" if duration_ms > WS_FRAME_BUDGET_MS else "ok"
                    ws_annotate_frames_total.labels(model_type=model_type, status=status_label).inc()
                    ws_annotate_duration_seconds.labels(model_type=model_type).observe(duration_ms / 1000)

                    await websocket.send_json(result)

                    logger.info(
                        "ws_annotation_frame",
                        model_type=model_type,
                        detections=len(raw_detections) if raw_detections else len(tracked),
                        duration_ms=duration_ms,
                        depth_available=depth_available,
                        dropped_total=dropped_frames,
                    )
                except Exception as exc:
                    logger.error("ws_annotation_frame_error", error=str(exc))
                    try:
                        await websocket.send_json({"error": "Inference failed", "detail": str(exc)})
                    except Exception:
                        pass
                finally:
                    processing = False
                    if pending_frame is not None:
                        next_frame = pending_frame
                        pending_frame = None
                        frame_index += 1
                        processing = True
                        asyncio.create_task(_process_frame(next_frame, frame_index))

            asyncio.create_task(_process_frame(message, current_index))

    except WebSocketDisconnect:
        logger.info("ws_annotation_disconnected", model_type=model_type, dropped_frames=dropped_frames)
    except Exception as exc:
        logger.error("ws_annotation_error", error=str(exc))
        try:
            await websocket.send_json({"error": "Inference failed", "detail": str(exc)})
        except Exception:
            pass
