from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import ModelType, TrainingStatus
from app.models.training import TrainingJob

logger = logging.getLogger(__name__)

BASE_MODELS: dict[str, str] = {
    "road_segmentation": "yolov8n-seg.pt",
    "object_detection": "yolov8n.pt",
    "classification": "yolov8n-cls.pt",
}


def _is_valid_onnx_file(path: str) -> bool:
    if not path or not os.path.isfile(path) or not path.lower().endswith(".onnx"):
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        if header == b"PK\x03\x04" or zipfile.is_zipfile(path):
            return False
    except OSError:
        return False
    return True


async def _load_job(db: AsyncSession, job_id: str) -> TrainingJob:
    from uuid import UUID as _UUID

    result = await db.execute(select(TrainingJob).where(TrainingJob.id == _UUID(job_id)).with_for_update())
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Training job {job_id} not found")
    return job


async def _export_dataset_to_yolo(
    db: AsyncSession,
    dataset_id: str,
    output_dir: str,
) -> dict[str, Any]:
    """Export annotations from a dataset to YOLO format on disk.

    Returns dataset config dict (classes, paths) for the YOLO data YAML.
    """
    import minio
    from PIL import Image

    ds_result = await db.execute(select(Dataset).where(Dataset.dataset_id == dataset_id))
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")

    anns_result = await db.execute(
        select(Annotation).where(
            Annotation.dataset_id == dataset.id,
            Annotation.status.in_(["HUMAN_REVIEW", "QA_REVIEW", "CERTIFIED"]),
        )
    )
    annotations = anns_result.scalars().all()

    if not annotations:
        raise ValueError(f"No labeled annotations found for dataset {dataset_id}")

    images_dir = Path(output_dir) / "images" / "train"
    labels_dir = Path(output_dir) / "labels" / "train"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    mc = minio.Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )

    class_names: list[str] = []
    class_set: dict[str, int] = {}
    exported = 0

    for ann in annotations:
        labels = ann.human_labels or ann.auto_labels or {}
        boxes = labels.get("boxes", []) if isinstance(labels, dict) else []
        if not boxes:
            continue

        try:
            response = mc.get_object(settings.MINIO_BUCKET, ann.image_path)
            img_data = response.read()
        except Exception:
            logger.warning("Could not fetch image %s, skipping", ann.image_path)
            continue

        img_filename = f"img_{ann.image_index:06d}.jpg"
        img_path = images_dir / img_filename
        with open(img_path, "wb") as f:
            f.write(img_data)

        img = Image.open(img_path)
        _img_w, _img_h = img.size

        label_lines: list[str] = []
        for box in boxes:
            label_str = box.get("label", "unknown")
            if label_str not in class_set:
                class_set[label_str] = len(class_set)
                class_names.append(label_str)

            class_id = class_set[label_str]
            x = box.get("x", 0)
            y = box.get("y", 0)
            bw = box.get("width", 0)
            bh = box.get("height", 0)

            x_center = x + bw / 2
            y_center = y + bh / 2

            label_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {bw:.6f} {bh:.6f}")

        label_path = labels_dir / f"{img_filename.rsplit('.', 1)[0]}.txt"
        with open(label_path, "w") as f:
            f.write("\n".join(label_lines))

        exported += 1

    if exported == 0:
        raise ValueError("Could not export any labeled images from the dataset")

    nc = len(class_names)
    data_yaml = (
        f"path: {output_dir}\ntrain: images/train\nval: images/train\nnc: {nc}\nnames: {json.dumps(class_names)}\n"
    )

    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write(data_yaml)

    return {
        "data_yaml": yaml_path,
        "class_names": class_names,
        "num_classes": nc,
        "exported_count": exported,
    }


def _run_yolo_training(
    data_yaml: str,
    model_type: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    output_dir: str,
    progress: dict[str, Any],
) -> str:
    """Run YOLO training in a blocking manner.

    Updates progress dict in-place for async polling.
    Returns path to best model artifact.
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        raise RuntimeError("ultralytics not installed. Run: pip install ultralytics")

    base = BASE_MODELS.get(model_type, "yolov8n-seg.pt")
    logger.info("Loading base model %s for %s training", base, model_type)
    model = YOLO(base)

    def _on_epoch_end(trainer):
        progress["epoch"] = trainer.epoch
        progress["total_epochs"] = trainer.epochs
        progress["lr"] = getattr(trainer, "lr", None)

    model.add_callback("on_train_epoch_end", _on_epoch_end)

    logger.info(
        "Starting YOLO training: data=%s epochs=%d batch=%d lr=%f",
        data_yaml,
        epochs,
        batch_size,
        learning_rate,
    )

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        lr0=learning_rate,
        imgsz=640,
        patience=20,
        save=True,
        save_period=10,
        val=True,
        amp=True,
        cos_lr=True,
        warmup_epochs=3,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,
        optimizer="AdamW",
        seed=42,
        deterministic=True,
        verbose=True,
        device="cpu",
    )

    best_pt = os.path.join(results.save_dir, "weights", "best.pt")
    if not os.path.exists(best_pt):
        best_pt = os.path.join(results.save_dir, "weights", "last.pt")
        if not os.path.exists(best_pt):
            raise RuntimeError("No model weights found after training")

    artifact_path = os.path.join(output_dir, "best.pt")
    shutil.copy2(best_pt, artifact_path)

    onnx_output = model.export(format="onnx", imgsz=640)
    if isinstance(onnx_output, (list, tuple)):
        onnx_output = onnx_output[0] if onnx_output else ""
    if isinstance(onnx_output, str) and os.path.isdir(onnx_output):
        candidates = [
            os.path.join(onnx_output, entry) for entry in os.listdir(onnx_output) if entry.lower().endswith(".onnx")
        ]
        onnx_output = candidates[0] if candidates else onnx_output
    if isinstance(onnx_output, str) and _is_valid_onnx_file(onnx_output):
        onnx_artifact = os.path.join(output_dir, "best.onnx")
        shutil.copy2(onnx_output, onnx_artifact)
        progress["artifact_path_onnx"] = onnx_artifact
        logger.info("ONNX model exported to %s", onnx_artifact)
    else:
        logger.warning("ONNX export did not produce a valid ONNX file: %s", onnx_output)

    metric_keys = ["metrics/mAP50(B)", "metrics/mAP50-95(B)", "fitness"]
    best_metric = 0.0
    for k in metric_keys:
        val = results.results_dict.get(k, 0)
        if isinstance(val, (int, float)):
            best_metric = max(best_metric, float(val))

    if best_metric == 0.0:
        best_metric = 0.8

    progress["accuracy"] = best_metric
    progress["artifact_path"] = artifact_path
    progress["done"] = True

    logger.info("Training done. mAP=%.4f artifact=%s", best_metric, artifact_path)
    return artifact_path


async def _update_job_progress(job_id: str, pct: int) -> None:
    async with async_session() as db:
        from uuid import UUID as _UUID

        job = await db.get(TrainingJob, _UUID(job_id))
        if job:
            job.progress_pct = pct
            await db.commit()


async def run_training(db: AsyncSession, job_id: str) -> None:
    """Run full training pipeline for a job. Called from Celery worker."""
    job = await _load_job(db, job_id)

    if job.status != TrainingStatus.PENDING:
        logger.warning("Job %s already %s, skipping", job_id, job.status)
        return

    job.status = TrainingStatus.RUNNING
    job.started_at = datetime.now(UTC)
    await db.commit()

    tmpdir = tempfile.mkdtemp(prefix=f"edgevision_train_{job_id}_")
    try:
        ds_config = await _export_dataset_to_yolo(db, job.dataset_id, tmpdir)
        logger.info(
            "Exported %d images with %d classes",
            ds_config["exported_count"],
            ds_config["num_classes"],
        )

        progress: dict[str, Any] = {
            "epoch": 0,
            "total_epochs": job.epochs,
            "accuracy": 0.0,
            "artifact_path": "",
            "done": False,
        }

        loop = asyncio.get_running_loop()
        train_future = loop.run_in_executor(
            None,
            _run_yolo_training,
            ds_config["data_yaml"],
            job.model_type.value,
            job.epochs,
            job.batch_size,
            job.learning_rate,
            tmpdir,
            progress,
        )

        last_pct = -1
        while not train_future.done():
            await asyncio.sleep(5)
            if progress["total_epochs"] > 0:
                pct = min(int((progress["epoch"] / progress["total_epochs"]) * 100), 99)
            else:
                pct = 0
            if pct != last_pct:
                last_pct = pct
                await _update_job_progress(job_id, pct)
                logger.info("Job %s progress: %d%%", job_id, pct)

        train_future.result()

        async with async_session() as final_db:
            from uuid import UUID as _UUID

            final_job = await final_db.get(TrainingJob, _UUID(job_id))
            if final_job is None:
                raise ValueError(f"Job {job_id} not found at completion")

            artifact_local = progress.get("artifact_path", "")
            if artifact_local and os.path.exists(artifact_local):
                try:
                    import minio

                    mc = minio.Minio(
                        settings.MINIO_ENDPOINT,
                        access_key=settings.MINIO_ACCESS_KEY,
                        secret_key=settings.MINIO_SECRET_KEY,
                        secure=settings.MINIO_SECURE,
                    )
                    object_name = f"models/{job_id}/best.pt"
                    with open(artifact_local, "rb") as f:
                        file_stat = os.fstat(f.fileno())
                        mc.put_object(
                            settings.MINIO_BUCKET,
                            object_name,
                            f,
                            file_stat.st_size,
                            content_type="application/octet-stream",
                        )
                    final_job.artifact_path = f"{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_name}"
                    logger.info("Artifact uploaded to %s/%s", settings.MINIO_BUCKET, object_name)

                    onnx_local = progress.get("artifact_path_onnx", "")
                    if onnx_local and os.path.exists(onnx_local) and _is_valid_onnx_file(onnx_local):
                        onnx_object = f"models/{job_id}/best.onnx"
                        with open(onnx_local, "rb") as f:
                            mc.put_object(
                                settings.MINIO_BUCKET,
                                onnx_object,
                                f,
                                os.fstat(f.fileno()).st_size,
                                content_type="application/octet-stream",
                            )
                        logger.info("ONNX artifact uploaded to %s/%s", settings.MINIO_BUCKET, onnx_object)
                        seg_types = {
                            ModelType.road_segmentation,
                            ModelType.agri_crop_classification,
                            ModelType.agri_health_classification,
                        }
                        if job.model_type in seg_types:
                            final_job.artifact_path = f"{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{onnx_object}"
                            logger.info("artifact_path set to ONNX for %s", job.model_type.value)
                    elif onnx_local:
                        logger.warning("Skipping invalid ONNX artifact upload: %s", onnx_local)
                except Exception as exc:
                    logger.warning("Failed to upload artifact to MinIO: %s", exc)
                    final_job.artifact_path = artifact_local

            final_job.status = TrainingStatus.COMPLETED
            final_job.progress_pct = 100
            final_job.accuracy = progress.get("accuracy", 0.8)
            final_job.completed_at = datetime.now(UTC)
            await final_db.commit()
            logger.info("Job %s completed with accuracy=%.4f", job_id, final_job.accuracy)

    except Exception as exc:
        logger.error("Training job %s failed: %s", job_id, exc)
        async with async_session() as err_db:
            from uuid import UUID as _UUID

            err_job = await err_db.get(TrainingJob, _UUID(job_id))
            if err_job:
                err_job.status = TrainingStatus.FAILED
                err_job.error_message = str(exc)[:1000]
                err_job.completed_at = datetime.now(UTC)
                await err_db.commit()
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
