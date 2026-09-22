from __future__ import annotations

import asyncio
import contextlib
import os
import time
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.ai.live_inference import (
    LIVE_CONF,
    attach_depth_boxes,
    build_annotations,
    maybe_estimate_depth,
    preload_agri_segmenter,
    preload_road_segmenter,
    run_agri_segmentation_live,
    run_engine_detection,
    run_road_segmentation_live,
    run_seg_primary_detection,
)
from app.ai.events import EventEngine, FrameRingBuffer, default_rules, rules_from_dicts
from app.ai.model_inference import get_active_engine
from app.ai.object_tracker import ByteTrack, get_track_config
from app.ai.yolo_seg import SEG_TO_TAXONOMY
from app.core.dependencies import get_current_user_ws
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
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
        annotations.append(
            {
                "class_name": text,
                "taxonomy_label": text,
                "confidence": round(r.get("confidence", 0.0), 4),
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "mask_format": None,
            }
        )
    return annotations


async def _warmup_depth_estimator() -> None:
    """Pre-load depth ONNX session on a background thread."""
    try:
        from app.ai.depth_estimator import get_depth_estimator

        dummy = np.zeros((64, 64, 3), dtype=np.uint8)
        await asyncio.to_thread(get_depth_estimator().estimate_depth_map, dummy)
    except Exception as exc:
        logger.debug("ws_depth_warmup_skipped", error=str(exc))


async def _warmup_pii_redaction() -> None:
    """Pre-load face and plate detectors so first live save is not delayed."""
    try:
        from app.ai.face_privacy import get_face_blurrer
        from app.ai.plate_privacy import get_plate_blurrer

        face_blurrer = get_face_blurrer()
        plate_blurrer = get_plate_blurrer()
        if face_blurrer.is_loaded():
            logger.info("ws_face_blurrer_warm")
        if plate_blurrer.is_loaded():
            logger.info("ws_plate_blurrer_warm")
    except Exception as exc:
        logger.debug("ws_pii_redaction_warmup_skipped", error=str(exc))


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
    seg_segmenter = None  # RoadSegmenter or AgriSegmenter for live ONNX path
    if not is_text_mode:
        _needs_engine = mt not in (
            ModelType.road_segmentation,
            ModelType.agri_crop_classification,
            ModelType.agri_health_classification,
        )
        if _needs_engine:
            async with async_session() as db:
                engine = await get_active_engine(db, mt)
            if engine is None or not engine.is_loaded():
                await websocket.send_json({"error": "No deployed model available for this model type"})
                await websocket.close(code=1011)
                return
        else:
            async with async_session() as db:
                if mt == ModelType.road_segmentation:
                    seg_segmenter = await preload_road_segmenter(db)
                elif mt in (ModelType.agri_crop_classification, ModelType.agri_health_classification):
                    seg_segmenter = await preload_agri_segmenter(model_type, db)
            if seg_segmenter is None or not seg_segmenter.is_loaded():
                await websocket.send_json({"error": f"No ONNX segmenter available for {model_type}"})
                await websocket.close(code=1011)
                return

    tracker = ByteTrack(config=get_track_config(model_type), model_type=model_type)
    processing = False
    pending_frame: bytes | None = None
    dropped_frames = 0
    frame_index = 0
    cached_depth: tuple | None = None

    # ─── Sprint 3 event layer setup ──────────────────────────────────────────
    is_obj_det = model_type == ModelType.object_detection.value
    events_param = websocket.query_params.get("events")
    events_enabled = is_obj_det if events_param is None else events_param in ("1", "true", "on")
    auto_save_enabled = websocket.query_params.get("auto_save", "0") in ("1", "true", "on")
    auto_save_dataset_id = websocket.query_params.get("dataset_id") or None

    event_engine: EventEngine | None = None
    frame_buffer = FrameRingBuffer(maxlen=24)
    active_clip: dict | None = None

    if events_enabled and is_obj_det:
        rules = default_rules()
        try:
            async with async_session() as db:
                from app.services.perception_events import get_event_rules

                rules = rules_from_dicts(await get_event_rules(db))
        except Exception as exc:
            logger.debug("event_rules_load_fallback_default", error=str(exc))
        event_engine = EventEngine(rules)
        logger.info("ws_annotation_events_enabled", rules=len(rules), auto_save=auto_save_enabled)

    if model_type == ModelType.object_detection.value:
        warmup_tasks = [
            asyncio.create_task(_warmup_depth_estimator()),
            asyncio.create_task(_warmup_pii_redaction()),
        ]
        del warmup_tasks

    logger.info("ws_annotation_connected", model_type=model_type, user_id=str(user.get("sub", "")))

    from app.api.metrics import (
        depth_inference_ms,
        ws_annotate_dropped_total,
        ws_annotate_duration_seconds,
        ws_annotate_events_total,
        ws_annotate_frames_total,
    )

    user_id = str(user.get("sub", ""))
    tenant_id = get_current_tenant_id()

    async def _finalize_clip(clip: dict) -> None:
        """Save buffered pre/post frames as an auto-captured clip."""
        from uuid import UUID

        from app.services.live_capture import save_live_capture
        from app.services.perception_events import record_perception_event

        storage_keys: list[str] = []
        saved_count = 0
        async with async_session() as db:
            for entry in clip["entries"]:
                try:
                    result = await save_live_capture(
                        db,
                        content=entry["frame_bytes"],
                        ann_list=entry["annotations"],
                        source="live_camera",
                        dataset_id=auto_save_dataset_id,
                        confidence_threshold=LIVE_CONF,
                        orientation="normal",
                        depth_available=entry.get("depth_available", False),
                        user_id=UUID(user_id),
                        tenant_id=tenant_id,
                        capture_reason="auto_event",
                        event_id=clip.get("event_id"),
                    )
                    storage_keys.append(result["image_path"])
                    saved_count += 1
                except Exception as exc:
                    logger.error("auto_save_frame_failed", error=str(exc))

            event_dict = clip["event"]
            rule = clip.get("rule")
            if rule is None:
                from app.ai.events import EventRule

                rule = EventRule(
                    rule_id=event_dict["rule_id"],
                    rule_type=event_dict["event_type"],
                    name=event_dict["rule_name"],
                    auto_save=True,
                )
            started_at = None
            if event_dict.get("duration_seconds") is not None and event_dict.get("triggered_at"):
                started_at = datetime.fromtimestamp(event_dict["triggered_at"], tz=timezone.utc)
            try:
                await record_perception_event(
                    db,
                    event=event_dict,
                    rule=rule,
                    storage_keys=storage_keys,
                    dataset_id=None,
                    tenant_id=tenant_id,
                    started_at=started_at,
                )
            except Exception as exc:
                logger.error("perception_event_record_failed", error=str(exc))

        ws_annotate_events_total.labels(model_type=model_type, event_type=event_dict["event_type"], status="saved").inc()
        await websocket.send_json(
            {
                "type": "event_saved",
                "event_id": clip.get("event_id"),
                "event": event_dict,
                "frames": saved_count,
                "storage_keys": storage_keys,
                "dataset_id": auto_save_dataset_id,
            }
        )
        logger.info("ws_annotation_clip_saved", event_id=clip.get("event_id"), frames=saved_count)

    async def _dispatch_alert(event_dict: dict, rule_dict: dict) -> None:
        """Deliver push alert for an alert-enabled event; never blocks streaming."""
        try:
            from app.services.alerts import dispatch_event_alert

            async with async_session() as db:
                results = await dispatch_event_alert(db, event_dict, rule_dict, tenant_id=tenant_id)
                if results:
                    logger.info(
                        "ws_annotation_alert_dispatched",
                        event_id=event_dict.get("event_id"),
                        rule_id=rule_dict.get("rule_id"),
                        channels=len(results),
                    )
        except Exception as exc:
            logger.debug("ws_annotation_alert_dispatch_failed", error=str(exc))

    try:
        while True:
            message = await websocket.receive_bytes()

            if not message:
                continue

            if processing:
                dropped_frames += 1
                pending_frame = message
                ws_annotate_dropped_total.labels(model_type=model_type, reason="busy").inc()
                await websocket.send_json(
                    {
                        "dropped": True,
                        "busy": True,
                        "model_type": model_type,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                continue

            processing = True
            frame_index += 1
            current_index = frame_index
            current_dropped = dropped_frames

            async def _process_frame(frame_bytes: bytes, idx: int, *, dropped_total: int) -> None:
                nonlocal processing, dropped_frames, pending_frame, cached_depth, frame_index, active_clip
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
                    is_road_seg = model_type == ModelType.road_segmentation.value
                    is_agri = model_type in (
                        ModelType.agri_crop_classification.value,
                        ModelType.agri_health_classification.value,
                    )

                    def _run_detection():
                        if use_seg_primary:
                            return run_seg_primary_detection(frame_bytes, image, tracker, model_type, LIVE_CONF)
                        if is_road_seg:
                            return run_road_segmentation_live(image, tracker, LIVE_CONF, segmenter=seg_segmenter)
                        if is_agri:
                            return run_agri_segmentation_live(image, tracker, model_type, LIVE_CONF, segmenter=seg_segmenter)
                        return run_engine_detection(engine, image, frame_bytes, tracker, model_type, LIVE_CONF)

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

                    try:
                        from app.ai.class_confusion import detect_confusions, resolve_confusion
                        confusion_events = detect_confusions(tracked)
                        if confusion_events:
                            tracked = resolve_confusion(tracked, confusion_events)
                    except Exception:
                        pass

                    # ─── Anomaly detection ─────────────────────────────────────
                    anomaly_result = None
                    try:
                        from app.services.anomaly_detection import (
                            compute_scene_embedding,
                            detect_anomaly,
                            update_scene_baseline,
                        )
                        camera_id = websocket.query_params.get("camera_id", "ws_default")
                        frame_embedding = compute_scene_embedding(
                            detections=tracked,
                            image_width=int(image.shape[1]),
                            image_height=int(image.shape[0]),
                        )
                        update_scene_baseline(camera_id, frame_embedding)
                        anomaly_result = detect_anomaly(camera_id, frame_embedding)
                    except Exception:
                        pass

                    annotations = build_annotations(tracked)

                    # ─── Data flywheel: collect edge cases (every 10th frame) ───
                    if idx % 10 == 0:
                        try:
                            from app.services.data_flywheel import get_default_flywheel

                            flywheel = get_default_flywheel()
                            frame_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            det_list = []
                            for t in tracked:
                                det_list.append({
                                    "class_name": t.get("class_name", ""),
                                    "confidence": t.get("confidence", 0.0),
                                    "bbox": t.get("bbox", []),
                                })
                            flywheel.collect_from_detection_frame(
                                frame_data={"timestamp": frame_ts},
                                detections=det_list,
                                camera_node_id=user_id,
                            )
                        except Exception:
                            pass

                    # ─── Sprint 3 event layer: rules + auto-save clip buffering ───
                    if event_engine is not None:
                        now = time.time()
                        for det in tracked:
                            if "taxonomy_label" not in det:
                                det["taxonomy_label"] = SEG_TO_TAXONOMY.get(
                                    det.get("class_name", ""), det.get("class_name")
                                )
                        triggered = event_engine.update(tracked, now)
                        for ev in triggered:
                            ws_annotate_events_total.labels(
                                model_type=model_type, event_type=ev.event_type, status="triggered"
                            ).inc()
                            await websocket.send_json({"type": "event", "event": ev.to_dict()})
                            rule_obj = next(
                                (r for r in event_engine.rules if r.rule_id == ev.rule_id),
                                None,
                            )
                            if rule_obj is not None and rule_obj.alert:
                                asyncio.create_task(_dispatch_alert(ev.to_dict(), rule_obj.to_dict()))
                            if auto_save_enabled and ev.auto_save:
                                if active_clip is not None:
                                    await _finalize_clip(active_clip)
                                active_clip = {
                                    "event_id": ev.event_id,
                                    "event": ev.to_dict(),
                                    "rule": next(
                                        (r for r in event_engine.rules if r.rule_id == ev.rule_id),
                                        None,
                                    ),
                                    "remaining": max(0, ev.post_frames),
                                    "entries": frame_buffer.recent(ev.pre_frames),
                                }

                        frame_buffer.push(
                            frame_bytes=frame_bytes,
                            annotations=annotations,
                            timestamp=now,
                            frame_index=idx,
                            depth_available=depth_available,
                        )
                        if active_clip is not None:
                            active_clip["remaining"] -= 1
                            active_clip["entries"].append(
                                {
                                    "frame_bytes": frame_bytes,
                                    "annotations": annotations,
                                    "timestamp": now,
                                    "frame_index": idx,
                                    "depth_available": depth_available,
                                }
                            )
                            if active_clip["remaining"] <= 0:
                                await _finalize_clip(active_clip)
                                active_clip = None

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

                    if anomaly_result is not None:
                        result["anomaly"] = anomaly_result

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
                        dropped_total=dropped_total,
                    )
                except Exception as exc:
                    logger.error("ws_annotation_frame_error", error=str(exc), exc_info=True)
                    with contextlib.suppress(Exception):
                        await websocket.send_json({"error": "Inference failed", "detail": str(exc)})
                finally:
                    processing = False
                    if pending_frame is not None:
                        next_frame = pending_frame
                        pending_frame = None
                        frame_index += 1
                        processing = True
                        pending_tasks = [
                            asyncio.create_task(_process_frame(next_frame, frame_index, dropped_total=dropped_total))
                        ]
                        del pending_tasks

            frame_tasks = [asyncio.create_task(_process_frame(message, current_index, dropped_total=current_dropped))]
            del frame_tasks

    except WebSocketDisconnect:
        logger.info("ws_annotation_disconnected", model_type=model_type, dropped_frames=dropped_frames)
    except Exception as exc:
        logger.error("ws_annotation_error", error=str(exc))
        with contextlib.suppress(Exception):
            await websocket.send_json({"error": "Inference failed", "detail": str(exc)})
