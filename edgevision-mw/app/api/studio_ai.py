from __future__ import annotations

import base64
import io
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import model_inference
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_minio_client
from app.core.logging import get_logger
from app.models.annotation import Annotation
from app.models.deployed_model import DeployedModel
from app.models.enums import ModelType
from app.models.image import ImageRecord

logger = get_logger("edgevision.studio_ai")

studio_ai_router = APIRouter(prefix="/studio", tags=["studio-ai"])


# ─── Request / Response Models ───

class PointPrompt(BaseModel):
    x: float = Field(..., ge=0, le=1, description="Normalized x coordinate")
    y: float = Field(..., ge=0, le=1, description="Normalized y coordinate")


class BoxPrompt(BaseModel):
    x1: float = Field(..., ge=0, le=1)
    y1: float = Field(..., ge=0, le=1)
    x2: float = Field(..., ge=0, le=1)
    y2: float = Field(..., ge=0, le=1)


class AIAssistRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID | None = None
    image_data: str | None = None  # base64 JPEG
    prompt_type: Literal["point", "box", "full_image"] = "full_image"
    prompt_data: dict | None = None  # {x, y} for point; {x1,y1,x2,y2} for box
    model_preference: Literal["fast", "accurate"] = "fast"
    return_polygons: bool = True


class AIAnnotation(BaseModel):
    class_name: str
    confidence: float = Field(..., ge=0, le=1)
    bbox: list[float]  # [x, y, w, h] normalized
    polygon: list[list[float]] | None = None  # [[x,y], ...] normalized


class AIAssistResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    annotations: list[AIAnnotation]
    inference_time_ms: float
    model_used: str
    fallback: bool = False


# ─── Endpoints ───

@studio_ai_router.post("/label/ai-assist", response_model=AIAssistResponse)
async def ai_assist(
    request: AIAssistRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    AI-assisted labeling endpoint.

    Supports three modes:
    - point: Click on object → SAM mask + YOLO classification
    - box: Draw rough box → SAM refines + YOLO classifies
    - full_image: Detect all objects → YOLO bboxes + optional SAM polygons
    """
    pil_image = await _load_image(request, db)

    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    import numpy as np
    image_np = np.array(pil_image)

    start = time.perf_counter()

    try:
        from app.ai.locate_anything import get_locate_anything_segmenter

        yolo, base_model_used = await _get_detector(db)
        la = get_locate_anything_segmenter()

        annotations: list[AIAnnotation] = []
        model_used = base_model_used

        if request.prompt_type == "full_image":
            detections = []
            if la.is_loaded():
                raw = la.detect(image_np, conf_threshold=0.35)
                for det in raw:
                    annotations.append(AIAnnotation(
                        class_name=det.get("class_name", det.get("taxonomy", "object")),
                        confidence=_clamp_confidence(det.get("confidence", 0.0)),
                        bbox=det.get("bbox", [0.0, 0.0, 1.0, 1.0]),
                        polygon=_mask_to_polygon(det.get("mask"), pil_image.width, pil_image.height)
                        if request.return_polygons and det.get("mask") is not None else None,
                    ))
                if annotations:
                    model_used = "locate_anything"

            if not annotations:
                detections = yolo.detect(image_np, conf_threshold=0.35)
                seg_masks: dict[int, object] = {}
                if request.return_polygons and request.model_preference == "accurate":
                    seg_masks = _yolo_seg_masks_by_detection(image_np, detections)

                for idx, det in enumerate(detections):
                    ann = AIAnnotation(
                        class_name=det.class_name,
                        confidence=_clamp_confidence(det.confidence),
                        bbox=[det.x1, det.y1, det.x2 - det.x1, det.y2 - det.y1],
                    )
                    mask = seg_masks.get(idx)
                    if mask is not None:
                        ann.polygon = _mask_to_polygon(mask, pil_image.width, pil_image.height)
                        model_used = f"{base_model_used}+yolov8-seg"
                    annotations.append(ann)

        elif request.prompt_type == "point":
            point = PointPrompt(**(request.prompt_data or {}))
            px = int(point.x * pil_image.width)
            py = int(point.y * pil_image.height)
            yolo_mask = _yolo_seg_mask_at_point(image_np, px, py)
            mask = yolo_mask or _heuristic_point_mask(image_np, px, py)
            crop = _extract_masked_crop(image_np, mask)
            result = yolo.classify(crop)
            annotations.append(AIAnnotation(
                class_name=result["class_name"],
                confidence=_clamp_confidence(result["confidence"]),
                bbox=_mask_to_bbox(mask),
                polygon=_mask_to_polygon(mask, pil_image.width, pil_image.height),
            ))
            model_used = f"yolov8-seg+{base_model_used}" if yolo_mask is not None else f"heuristic+{base_model_used}"

        elif request.prompt_type == "box":
            box = BoxPrompt(**(request.prompt_data or {}))
            x1 = int(box.x1 * pil_image.width)
            y1 = int(box.y1 * pil_image.height)
            x2 = int(box.x2 * pil_image.width)
            y2 = int(box.y2 * pil_image.height)
            yolo_mask = _yolo_seg_mask_for_box(image_np, x1, y1, x2, y2)
            mask = yolo_mask or _heuristic_box_mask(image_np, x1, y1, x2, y2)
            crop = _extract_masked_crop(image_np, mask)
            result = yolo.classify(crop)
            annotations.append(AIAnnotation(
                class_name=result["class_name"],
                confidence=_clamp_confidence(result["confidence"]),
                bbox=_mask_to_bbox(mask),
                polygon=_mask_to_polygon(mask, pil_image.width, pil_image.height),
            ))
            model_used = f"yolov8-seg+{base_model_used}" if yolo_mask is not None else f"heuristic+{base_model_used}"

    except ImportError:
        logger.warning("ai_models_not_available", fallback=True)
        return AIAssistResponse(
            annotations=[],
            inference_time_ms=0,
            model_used="none",
            fallback=True,
        )
    except Exception as exc:
        logger.error("ai_inference_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI inference failed. Please try again or use manual labeling.",
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "ai_assist_completed",
        user_id=user["sub"],
        prompt_type=request.prompt_type,
        num_results=len(annotations),
        inference_time_ms=round(elapsed_ms, 2),
    )

    return AIAssistResponse(
        annotations=annotations,
        inference_time_ms=round(elapsed_ms, 2),
        model_used=model_used,
    )


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID = Field(..., description="Annotation/image ID to classify")
    model_type: str = Field(default="classification", description="ModelType to use for classification")


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID
    class_name: str
    confidence: float
    model_used: str
    latency_ms: float


@studio_ai_router.post("/classify", response_model=ClassifyResponse)
async def classify_image(
    request: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Classify an image using the active deployed classification model."""
    from PIL import Image

    annotation = await db.get(Annotation, request.image_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        mc = await get_minio_client()
        response = mc.get_object(settings.MINIO_BUCKET, annotation.image_path)
        pil_image = Image.open(io.BytesIO(response.read()))
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image fetch failed: {exc}")

    import numpy as np
    image_np = np.array(pil_image)

    model_type = ModelType(request.model_type)
    start = time.perf_counter()

    engine = await model_inference.get_active_engine(db, model_type)
    if engine is None or not engine.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No deployed active model available for model_type={model_type.value}",
        )

    result = engine.classify(image_np)
    deployed = await db.execute(
        select(DeployedModel).where(
            DeployedModel.model_type == model_type,
            DeployedModel.is_active.is_(True),
        )
    )
    dm = deployed.scalar_one_or_none()
    model_used = f"trained:{dm.model_name}:{dm.version}" if dm else "trained:unknown"

    elapsed_ms = (time.perf_counter() - start) * 1000

    return ClassifyResponse(
        image_id=request.image_id,
        class_name=result.get("class_name", "unknown"),
        confidence=result.get("confidence", 0.0),
        model_used=model_used,
        latency_ms=round(elapsed_ms, 2),
    )


@studio_ai_router.get("/health/models")
async def model_health(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all active deployed models and their load status."""
    from app.models.deployed_model import DeployedModel

    result = await db.execute(
        select(DeployedModel).where(DeployedModel.is_active.is_(True))
    )
    models = result.scalars().all()

    statuses = []
    for m in models:
        try:
            engine = model_inference.get_trained_engine(m.artifact_path, m.model_type)
            loaded = engine.is_loaded()
        except Exception:
            loaded = False
        statuses.append({
            "id": str(m.id),
            "model_name": m.model_name,
            "model_type": m.model_type.value,
            "version": m.version,
            "format": m.format.value,
            "is_loaded": loaded,
            "artifact_path": m.artifact_path,
            "deployed_at": m.deployed_at.isoformat() if m.deployed_at else None,
        })

    return {"models": statuses, "count": len(statuses)}


@studio_ai_router.post("/label/ai-assist/batch", response_model=list[AIAssistResponse])
async def ai_assist_batch(
    requests: list[AIAssistRequest],
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Batch AI assist for pre-labeling multiple images."""
    results = []
    for req in requests:
        result = await ai_assist(req, db, user)
        results.append(result)
    return results


# ─── Helpers ───

def _clamp_confidence(conf: float) -> float:
    """Defensive clamp for AIAnnotation confidence field."""
    if conf > 1.0:
        conf = conf / 100.0 if conf <= 100.0 else 1.0
    return max(0.0, min(1.0, conf))


def _encode_image_np(image_np) -> bytes | None:
    import cv2

    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))
    return buf.tobytes() if ok else None


def _heuristic_point_mask(image_np, px: int, py: int, radius: int = 50):
    import numpy as np

    h, w = image_np.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)
    r = min(radius, h // 4, w // 4)
    y1, y2 = max(0, py - r), min(h, py + r)
    x1, x2 = max(0, px - r), min(w, px + r)
    mask[y1:y2, x1:x2] = 1.0
    return mask


def _heuristic_box_mask(image_np, x1: int, y1: int, x2: int, y2: int):
    import numpy as np

    h, w = image_np.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)
    mask[max(0, y1):min(h, y2), max(0, x1):min(w, x2)] = 1.0
    return mask


def _yolo_seg_mask_at_point(image_np, px: int, py: int):
    from app.ai.yolo_seg import get_yolo_seg_segmenter

    yolo = get_yolo_seg_segmenter()
    if not yolo.is_loaded():
        return None
    encoded = _encode_image_np(image_np)
    if encoded is None:
        return None
    for inst in yolo.detect(encoded):
        mask = inst.get("mask")
        if mask is not None and 0 <= py < mask.shape[0] and 0 <= px < mask.shape[1] and mask[py, px]:
            return mask.astype("float32")
    return None


def _yolo_seg_mask_for_box(image_np, x1: int, y1: int, x2: int, y2: int):
    import numpy as np

    from app.ai.yolo_seg import get_yolo_seg_segmenter

    yolo = get_yolo_seg_segmenter()
    if not yolo.is_loaded():
        return None
    encoded = _encode_image_np(image_np)
    if encoded is None:
        return None
    best_mask = None
    best_iou = 0.0
    box_area = max(1, (x2 - x1) * (y2 - y1))
    for inst in yolo.detect(encoded):
        mask = inst.get("mask")
        if mask is None:
            continue
        ys, xs = np.where(mask)
        if len(xs) == 0:
            continue
        mx1, my1, mx2, my2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
        ix1, iy1 = max(x1, mx1), max(y1, my1)
        ix2, iy2 = min(x2, mx2), min(y2, my2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = box_area + max(1, (mx2 - mx1) * (my2 - my1)) - inter
        iou = inter / union if union else 0.0
        if iou > best_iou:
            best_iou = iou
            best_mask = mask.astype("float32")
    return best_mask if best_iou > 0.1 else None


def _yolo_seg_masks_by_detection(image_np, detections) -> dict[int, object]:
    from app.ai.yolo_seg import get_yolo_seg_segmenter

    yolo = get_yolo_seg_segmenter()
    if not yolo.is_loaded():
        return {}
    encoded = _encode_image_np(image_np)
    if encoded is None:
        return {}
    h, w = image_np.shape[:2]
    instances = yolo.detect(encoded)
    out: dict[int, object] = {}
    for idx, det in enumerate(detections):
        cx = int(((det.x1 + det.x2) / 2) * w)
        cy = int(((det.y1 + det.y2) / 2) * h)
        for inst in instances:
            mask = inst.get("mask")
            if mask is not None and 0 <= cy < mask.shape[0] and 0 <= cx < mask.shape[1] and mask[cy, cx]:
                out[idx] = mask.astype("float32")
                break
    return out


async def _get_detector(db: AsyncSession):
    from app.ai.yolo_detector import YOLODetector

    engine = await model_inference.get_active_engine(db, ModelType.object_detection)
    if engine is not None and engine.is_loaded():
        deployed = await db.execute(
            select(DeployedModel).where(
                DeployedModel.model_type == ModelType.object_detection,
                DeployedModel.is_active.is_(True),
            )
        )
        dm = deployed.scalar_one_or_none()
        return engine, f"trained:{dm.model_name}:{dm.version}" if dm else "trained:unknown"

    return YOLODetector(), "yolov8x"


async def _load_image(request: AIAssistRequest, db: AsyncSession):
    """Load PIL image from request (image_id or base64 data)."""
    from PIL import Image

    if request.image_id:
        annotation = await db.get(Annotation, request.image_id)
        if annotation is not None:
            image_path = annotation.image_path
        else:
            record = await db.get(ImageRecord, request.image_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Image not found")
            image_path = record.storage_key

        mc = await get_minio_client()
        from app.core.config import settings
        try:
            response = mc.get_object(settings.MINIO_BUCKET, image_path)
            return Image.open(io.BytesIO(response.read()))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Image fetch failed: {exc}")

    elif request.image_data:
        try:
            image_bytes = base64.b64decode(request.image_data.split(",")[-1])
            return Image.open(io.BytesIO(image_bytes))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image_data")

    raise HTTPException(status_code=400, detail="Provide image_id or image_data")


def _mask_to_bbox(mask) -> list[float]:
    """Convert binary mask to normalized bbox [x, y, w, h]."""
    import numpy as np
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return [0, 0, 1, 1]

    y1, y2 = np.where(rows)[0][[0, -1]]
    x1, x2 = np.where(cols)[0][[0, -1]]
    h, w = mask.shape
    return [float(x1) / w, float(y1) / h, float(x2 - x1) / w, float(y2 - y1) / h]


def _mask_to_polygon(mask, img_w: int, img_h: int) -> list[list[float]]:
    """Convert binary mask to simplified polygon via contour tracing."""
    try:
        from skimage import measure
        from skimage.measure import approximate_polygon

        contours = measure.find_contours(mask, 0.5)
        if not contours:
            return []

        largest = max(contours, key=len)
        simplified = approximate_polygon(largest, tolerance=2.0)
        return [[float(p[1]) / img_w, float(p[0]) / img_h] for p in simplified]
    except ImportError:
        return []


def _extract_masked_crop(image, mask) -> object:
    """Extract bounding crop around mask for classification."""
    bbox = _mask_to_bbox(mask)
    h, w = image.shape[:2]
    x1 = int(bbox[0] * w)
    y1 = int(bbox[1] * h)
    x2 = int((bbox[0] + bbox[2]) * w)
    y2 = int((bbox[1] + bbox[3]) * h)
    return image[y1:y2, x1:x2]
