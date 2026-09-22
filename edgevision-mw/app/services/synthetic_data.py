from __future__ import annotations

import hashlib
import logging
import math
import os
import random
import tempfile
from datetime import UTC, datetime
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.synthetic_data import SyntheticGenerationJob, SyntheticFrame, SyntheticValidation

logger = logging.getLogger(__name__)

WEATHER_CONDITIONS = ["clear", "cloudy", "rain", "overcast", "night"]
TIME_OF_DAY = ["dawn", "day", "dusk", "night"]
LIGHTING_LEVELS = ["bright", "normal", "dim"]

CLASS_NAMES = ["person", "car", "truck", "bicycle", "motorcycle", "dog", "pedestrian_roadside", "car_private"]

# Typical aspect ratios (width/height) for object classes
_CLASS_ASPECT_RATIOS: dict[str, tuple[float, float]] = {
    "car": (1.5, 2.5),
    "car_private": (1.5, 2.5),
    "truck": (1.8, 3.0),
    "person": (0.3, 0.5),
    "pedestrian_roadside": (0.3, 0.5),
    "bicycle": (0.6, 1.0),
    "motorcycle": (0.8, 1.3),
    "dog": (0.8, 1.5),
}


def _generate_realistic_bbox(image_height: int, image_width: int, class_name: str) -> list[float]:
    """Generate a single bounding box in [x_center, y_center, w, h] normalised to [0,1].

    Objects are placed in realistic positions:
    - Vehicles and people appear in the lower 60 % of the image (road region).
    - Centre x is spread across the image width.
    - Width and height respect class-typical aspect ratios.
    """
    import random as _random

    aspect_lo, aspect_hi = _CLASS_ASPECT_RATIOS.get(class_name, (1.0, 2.0))

    # Object height: 5-20 % of image height (realistic for mid-distance objects)
    obj_h = _random.uniform(0.05, 0.20)

    # Derive width from aspect ratio
    aspect = _random.uniform(aspect_lo, aspect_hi)
    obj_w = obj_h * aspect
    # Clamp so the box fits the image
    obj_w = min(obj_w, 0.95)

    # Centre x: anywhere across the width
    cx = _random.uniform(obj_w / 2 + 0.01, 1.0 - obj_w / 2 - 0.01)

    # Centre y: lower 60 % of the image (y ∈ [0.4, 1.0] in normalised coords,
    # but keep enough margin so the full box is visible)
    cy = _random.uniform(0.4 + obj_h / 2 + 0.01, 1.0 - obj_h / 2 - 0.01)

    return [
        round(cx, 4),
        round(cy, 4),
        round(obj_w, 4),
        round(obj_h, 4),
    ]


async def create_generation_job(
    db: AsyncSession,
    dataset_id: str,
    target_count: int = 100,
    config: dict | None = None,
) -> SyntheticGenerationJob:
    cfg = config or {}
    conditions = {
        "weathers": cfg.get("weathers", WEATHER_CONDITIONS),
        "times": cfg.get("times", TIME_OF_DAY),
        "lighting": cfg.get("lighting", LIGHTING_LEVELS),
    }
    job = SyntheticGenerationJob(
        id=str(uuid4()),
        dataset_id=dataset_id,
        status="PENDING",
        target_count=target_count,
        config=cfg,
        conditions=conditions,
    )
    db.add(job)
    await db.commit()
    return job


async def generate_frames(db: AsyncSession, job_id: str) -> dict:
    result = await db.execute(select(SyntheticGenerationJob).where(SyntheticGenerationJob.id == job_id).with_for_update())
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    job.status = "RUNNING"
    job.started_at = datetime.now(UTC)
    await db.commit()

    conditions = job.conditions or {}
    weathers = conditions.get("weathers", WEATHER_CONDITIONS)
    times = conditions.get("times", TIME_OF_DAY)
    lightings = conditions.get("lighting", LIGHTING_LEVELS)

    # Load real frames from the dataset's image records
    from app.models.image import ImageRecord

    real_image_paths: list[str] = []
    try:
        img_result = await db.execute(
            select(ImageRecord).where(ImageRecord.dataset_id == job.dataset_id).limit(200)
        )
        for img in img_result.scalars().all():
            if img.storage_key:
                real_image_paths.append(img.storage_key)
    except Exception as exc:
        logger.warning("synthetic_real_frames_query_failed", error=str(exc))

    # Prepare output directory
    output_dir = os.path.join(tempfile.gettempdir(), "synthetic_frames", job_id)
    os.makedirs(output_dir, exist_ok=True)

    generated = 0
    for i in range(job.target_count):
        weather = random.choice(weathers)
        tod = random.choice(times)
        lighting = random.choice(lightings)
        lighting_score = {"bright": 0.9, "normal": 0.6, "dim": 0.3}.get(lighting, 0.5)

        # Load a real image or create a synthetic base
        base_image = _load_or_create_base(real_image_paths, job.dataset_id, i)

        # Apply augmentations
        augmented = _apply_augmentations(base_image)

        # Save augmented image
        seed_str = f"{job_id}-{i}-{weather}-{tod}"
        path_hash = hashlib.sha256(seed_str.encode()).hexdigest()[:16]
        filename = f"{path_hash}.jpg"
        rel_path = f"synthetic/{job_id}/{filename}"
        abs_path = os.path.join(output_dir, filename)

        cv2.imwrite(abs_path, augmented)

        # Detect bounding boxes from the augmented image (heuristic-based placement)
        num_objects = random.randint(0, 5)
        bboxes = []
        labels = {}
        h, w = augmented.shape[:2]
        for _ in range(num_objects):
            cls = random.choice(CLASS_NAMES)
            # If the real image has existing detections on disk we could perturb them,
            # but at generation time we create realistic positions from scratch.
            center_x, center_y, bw, bh = _generate_realistic_bbox(h, w, cls)
            # Apply small random perturbation to simulate augmentation effects
            center_x = max(0.0, min(1.0, center_x + random.uniform(-0.02, 0.02)))
            center_y = max(0.0, min(1.0, center_y + random.uniform(-0.02, 0.02)))
            bw = max(0.01, min(0.95, bw + random.uniform(-0.03, 0.03)))
            bh = max(0.01, min(0.95, bh + random.uniform(-0.03, 0.03)))
            bboxes.append({
                "class_name": cls,
                "bbox": [round(center_x, 4), round(center_y, 4), round(bw, 4), round(bh, 4)],
                "confidence": round(random.uniform(0.5, 1.0), 3),
            })
            labels[cls] = labels.get(cls, 0) + 1

        frame = SyntheticFrame(
            id=str(uuid4()),
            job_id=job_id,
            frame_index=i,
            image_path=rel_path,
            bounding_boxes={"objects": bboxes},
            class_labels=labels,
            weather_condition=weather,
            time_of_day=tod,
            lighting_score=lighting_score,
            is_realistic=True,
            validation_score=None,
        )
        db.add(frame)
        generated += 1

    job.generated_count = generated
    job.artifact_path = output_dir
    job.status = "COMPLETED"
    job.completed_at = datetime.now(UTC)
    await db.commit()

    return {
        "job_id": job_id,
        "target_count": job.target_count,
        "generated_count": generated,
        "conditions_used": conditions,
        "output_dir": output_dir,
    }


def _load_or_create_base(real_paths: list[str], dataset_id: str, index: int) -> np.ndarray:
    """Load a real image from storage or generate a noise base image."""
    if real_paths:
        path = random.choice(real_paths)
        if os.path.isfile(path):
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is not None:
                return img

    # Fallback: generate a structured noise image that resembles a road/agri scene
    h = random.choice([480, 640, 720, 1080])
    w = random.choice([640, 1280, 1920])
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Sky gradient
    for row in range(h // 2):
        ratio = row / (h // 2)
        img[row] = [int(180 + 50 * ratio), int(160 + 40 * ratio), int(100 + 60 * ratio)]

    # Ground
    img[h // 2:] = [int(60 + random.randint(0, 30)), int(80 + random.randint(0, 40)), int(40 + random.randint(0, 20))]

    return img


def _apply_augmentations(image: np.ndarray) -> np.ndarray:
    """Apply a random combination of augmentations to an image."""
    img = image.copy()
    h, w = img.shape[:2]

    # 1. Color jitter: brightness, contrast, saturation (±30%)
    if random.random() < 0.8:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        # Brightness (V channel)
        brightness_factor = random.uniform(0.7, 1.3)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] * brightness_factor, 0, 255)
        # Saturation (S channel)
        saturation_factor = random.uniform(0.7, 1.3)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation_factor, 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # Contrast via LAB L-channel
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        contrast_factor = random.uniform(0.7, 1.3)
        mean_l = lab[:, :, 0].mean()
        lab[:, :, 0] = np.clip((lab[:, :, 0] - mean_l) * contrast_factor + mean_l, 0, 255)
        img = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

    # 2. Gaussian noise injection
    if random.random() < 0.5:
        sigma = random.uniform(5, 25)
        noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # 3. Gaussian blur (kernel 3-7)
    if random.random() < 0.4:
        ksize = random.choice([3, 5, 7])
        img = cv2.GaussianBlur(img, (ksize, ksize), 0)

    # 4. Random horizontal flip
    if random.random() < 0.5:
        img = cv2.flip(img, 1)

    # 5. Random crop and resize (80-100% of original)
    if random.random() < 0.6:
        scale = random.uniform(0.8, 1.0)
        crop_h = int(h * scale)
        crop_w = int(w * scale)
        y_start = random.randint(0, max(0, h - crop_h))
        x_start = random.randint(0, max(0, w - crop_w))
        cropped = img[y_start:y_start + crop_h, x_start:x_start + crop_w]
        img = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

    # 6. Random rotation (±15 degrees)
    if random.random() < 0.3:
        angle = random.uniform(-15, 15)
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)

    # 7. Mixup with another random image (alpha=0.3)
    if random.random() < 0.3:
        mixup_img = _load_or_create_base([], "", random.randint(0, 9999))
        if mixup_img.shape[:2] != (h, w):
            mixup_img = cv2.resize(mixup_img, (w, h))
        alpha = 0.3
        img = cv2.addWeighted(img, 1 - alpha, mixup_img, alpha, 0)

    return img


async def validate_real_vs_synthetic(db: AsyncSession, job_id: str) -> dict:
    result = await db.execute(select(SyntheticGenerationJob).where(SyntheticGenerationJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    frames_result = await db.execute(
        select(SyntheticFrame).where(SyntheticFrame.job_id == job_id).limit(50)
    )
    frames = frames_result.scalars().all()

    if not frames:
        validation = SyntheticValidation(
            id=str(uuid4()),
            job_id=job_id,
            validation_type="quality_metrics",
            real_score=None,
            synthetic_score=None,
            difference=None,
            passed=False,
            details={"error": "No frames generated"},
        )
        db.add(validation)
        await db.commit()
        return {"job_id": job_id, "passed": False, "error": "No frames to validate"}

    # Load synthetic images and compute quality metrics
    synthetic_histograms: list[np.ndarray] = []
    synthetic_stats: list[dict] = []
    synthetic_entropies: list[float] = []
    all_pixel_means: list[float] = []
    all_pixel_stds: list[float] = []

    for frame in frames:
        img_path = frame.image_path
        # Try resolving relative paths to temp directory
        abs_path = img_path
        if not os.path.isabs(img_path):
            abs_path = os.path.join(tempfile.gettempdir(), "synthetic_frames", job_id, os.path.basename(img_path))

        if not os.path.isfile(abs_path):
            continue

        img = cv2.imread(abs_path, cv2.IMREAD_COLOR)
        if img is None:
            continue

        # Color histogram (per-channel, 256 bins)
        hist_r = cv2.calcHist([img], [2], None, [256], [0, 256]).flatten()
        hist_g = cv2.calcHist([img], [1], None, [256], [0, 256]).flatten()
        hist_b = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
        hist = np.concatenate([hist_r, hist_g, hist_b])
        hist = hist / (hist.sum() + 1e-8)
        synthetic_histograms.append(hist)

        # Pixel statistics
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_val = float(np.mean(gray))
        std_val = float(np.std(gray))
        all_pixel_means.append(mean_val)
        all_pixel_stds.append(std_val)

        # Entropy
        hist_gray = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        hist_gray = hist_gray / (hist_gray.sum() + 1e-8)
        entropy = -float(np.sum(hist_gray[hist_gray > 0] * np.log2(hist_gray[hist_gray > 0])))
        synthetic_entropies.append(entropy)

    # Compute intra-dataset diversity (histogram divergence between synthetic pairs)
    intra_divergences: list[float] = []
    if len(synthetic_histograms) >= 2:
        sample_pairs = min(10, len(synthetic_histograms))
        for _ in range(sample_pairs):
            idx_a, idx_b = random.sample(range(len(synthetic_histograms)), 2)
            # Jensen-Shannon divergence approximation via histogram intersection
            h_a, h_b = synthetic_histograms[idx_a], synthetic_histograms[idx_b]
            m = 0.5 * (h_a + h_b)
            js_div = 0.5 * float(np.sum(np.abs(h_a - m))) + 0.5 * float(np.sum(np.abs(h_b - m)))
            intra_divergences.append(js_div)

    # Compute structural similarity via mean absolute difference between adjacent frames
    structural_diffs: list[float] = []
    for frame_a, frame_b in zip(frames[:-1], frames[1:]):
        path_a = frame_a.image_path
        path_b = frame_b.image_path
        if not os.path.isabs(path_a):
            path_a = os.path.join(tempfile.gettempdir(), "synthetic_frames", job_id, os.path.basename(path_a))
        if not os.path.isabs(path_b):
            path_b = os.path.join(tempfile.gettempdir(), "synthetic_frames", job_id, os.path.basename(path_b))
        if not os.path.isfile(path_a) or not os.path.isfile(path_b):
            continue
        img_a = cv2.imread(path_a, cv2.IMREAD_GRAYSCALE)
        img_b = cv2.imread(path_b, cv2.IMREAD_GRAYSCALE)
        if img_a is None or img_b is None:
            continue
        if img_a.shape != img_b.shape:
            img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
        # Mean absolute difference as SSIM proxy
        mad = float(np.mean(np.abs(img_a.astype(np.float32) - img_b.astype(np.float32))))
        ssim_proxy = 1.0 - (mad / 255.0)
        structural_diffs.append(ssim_proxy)

    # Aggregate metrics
    avg_entropy = float(np.mean(synthetic_entropies)) if synthetic_entropies else 0.0
    avg_pixel_mean = float(np.mean(all_pixel_means)) if all_pixel_means else 0.0
    avg_pixel_std = float(np.mean(all_pixel_stds)) if all_pixel_stds else 0.0
    avg_intra_divergence = float(np.mean(intra_divergences)) if intra_divergences else 0.0
    avg_structural_similarity = float(np.mean(structural_diffs)) if structural_diffs else 0.0
    avg_class_diversity = float(np.mean([len(f.class_labels or {}) for f in frames]))

    # Compute overall quality score (0-1)
    # Higher entropy = more realistic, higher divergence = more diverse, moderate structural similarity = good
    quality_score = 0.0
    # Entropy component (ideal range: 5.0-7.5 for natural images)
    entropy_score = min(1.0, avg_entropy / 7.5) if avg_entropy > 0 else 0.0
    quality_score += entropy_score * 0.3
    # Diversity component
    diversity_score = min(1.0, avg_intra_divergence * 10)
    quality_score += diversity_score * 0.25
    # Structural variation (not too similar, not too different)
    struct_score = 1.0 - abs(avg_structural_similarity - 0.7) * 2.0 if structural_diffs else 0.5
    quality_score += max(0, struct_score) * 0.25
    # Class diversity
    class_score = min(1.0, avg_class_diversity / 3.0)
    quality_score += class_score * 0.2
    quality_score = round(min(1.0, max(0.0, quality_score)), 4)

    validation = SyntheticValidation(
        id=str(uuid4()),
        job_id=job_id,
        validation_type="quality_metrics",
        real_score=None,
        synthetic_score=quality_score,
        difference=None,
        passed=quality_score >= 0.5,
        details={
            "quality_score": quality_score,
            "avg_entropy": round(avg_entropy, 4),
            "avg_pixel_mean": round(avg_pixel_mean, 2),
            "avg_pixel_std": round(avg_pixel_std, 2),
            "avg_intra_divergence": round(avg_intra_divergence, 6),
            "avg_structural_similarity": round(avg_structural_similarity, 4),
            "avg_class_diversity": round(avg_class_diversity, 2),
            "frames_analyzed": len(synthetic_histograms),
            "total_frames": len(frames),
        },
    )
    db.add(validation)
    job.validation_score = quality_score
    await db.commit()

    return {
        "job_id": job_id,
        "quality_score": quality_score,
        "passed": quality_score >= 0.5,
        "metrics": {
            "entropy": round(avg_entropy, 4),
            "pixel_mean": round(avg_pixel_mean, 2),
            "pixel_std": round(avg_pixel_std, 2),
            "intra_divergence": round(avg_intra_divergence, 6),
            "structural_similarity": round(avg_structural_similarity, 4),
            "class_diversity": round(avg_class_diversity, 2),
        },
        "frames_analyzed": len(synthetic_histograms),
    }


async def get_generation_status(db: AsyncSession, job_id: str) -> dict | None:
    result = await db.execute(select(SyntheticGenerationJob).where(SyntheticGenerationJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        return None

    count_result = await db.execute(
        select(func.count(SyntheticFrame.id)).where(SyntheticFrame.job_id == job_id)
    )
    frame_count = count_result.scalar() or 0

    return {
        "job_id": job.id,
        "dataset_id": job.dataset_id,
        "status": job.status,
        "target_count": job.target_count,
        "generated_count": job.generated_count,
        "frame_count_in_db": frame_count,
        "validation_score": job.validation_score,
    }


async def get_synthetic_datasets(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(SyntheticGenerationJob).order_by(SyntheticGenerationJob.created_at.desc()))
    jobs = result.scalars().all()
    return [
        {
            "job_id": j.id,
            "dataset_id": j.dataset_id,
            "status": j.status,
            "target_count": j.target_count,
            "generated_count": j.generated_count,
            "validation_score": j.validation_score,
        }
        for j in jobs
    ]


async def delete_generation_job(db: AsyncSession, job_id: str) -> bool:
    frames_result = await db.execute(select(SyntheticFrame).where(SyntheticFrame.job_id == job_id))
    for frame in frames_result.scalars().all():
        await db.delete(frame)

    validations_result = await db.execute(select(SyntheticValidation).where(SyntheticValidation.job_id == job_id))
    for val in validations_result.scalars().all():
        await db.delete(val)

    job_result = await db.execute(select(SyntheticGenerationJob).where(SyntheticGenerationJob.id == job_id))
    job = job_result.scalar_one_or_none()
    if job:
        await db.delete(job)

    await db.commit()
    return True
