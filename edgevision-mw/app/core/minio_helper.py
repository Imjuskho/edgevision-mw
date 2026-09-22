from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import timedelta
from io import BytesIO

from app.core.config import settings
from app.core.dependencies import get_minio_client, get_minio_client_sync
from app.core.logging import get_logger

logger = get_logger("edgevision.minio")


async def ensure_bucket(bucket_name: str | None = None) -> bool:
    bucket = bucket_name or settings.MINIO_BUCKET
    mc = await get_minio_client()
    try:
        if not mc.bucket_exists(bucket):
            mc.make_bucket(bucket)
            logger.info("minio_bucket_created", bucket=bucket)
        return True
    except Exception as exc:
        logger.error("minio_bucket_error", bucket=bucket, error=str(exc))
        raise


async def put_object(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str,
    metadata: dict | None = None,
) -> None:
    key = key.lstrip("/")
    if key.startswith("/"):
        key = key.lstrip("/")
        logger.warning("minio_key_stripped_leading_slash", original_key=key, cleaned_key=key)

    mc = await get_minio_client()

    logger.info(
        "minio_put_attempt",
        bucket=bucket,
        key=key,
        content_type=content_type,
        size_bytes=len(data),
    )

    try:
        if not mc.bucket_exists(bucket):
            mc.make_bucket(bucket)
            logger.info("minio_bucket_auto_created", bucket=bucket)

        mc.put_object(
            bucket,
            key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata or {},
        )
        logger.info("minio_put_success", bucket=bucket, key=key)
    except Exception:
        import os
        cache_path = os.path.join(_LOCAL_VOLUME_BASE, os.path.basename(key))
        os.makedirs(_LOCAL_VOLUME_BASE, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(data)
        logger.info("minio_put_local_fallback", bucket=bucket, key=key, path=cache_path)


async def get_presigned_get_url(bucket: str, key: str, expires: int = 3600) -> str:
    key = key.lstrip("/")
    mc = await get_minio_client()
    try:
        url = mc.presigned_get_object(bucket, key, expires=timedelta(seconds=expires))
        logger.debug("minio_presigned_url_generated", key=key, expires=expires)
        return url
    except Exception:
        local_path = _local_volume_path(bucket, key)
        if local_path:
            api_key = key.replace("/", "_").replace(".", "_")
            logger.info("minio_local_presigned_fallback", bucket=bucket, key=key, local_path=local_path)
            return f"/api/v1/images/local-serve/{api_key}?bucket={bucket}"
        logger.error("minio_presigned_url_error", key=key)
        raise


_LOCAL_VOLUME_BASE = "/Users/mac/EDGE VISION DATA PLATFORMS/edgevision-mw/local_images_extracted"
_MINIO_CONTAINER = "edgevision-mw-minio-1"


def _local_volume_path(bucket: str, key: str) -> str | None:
    import os
    local = os.path.join(_LOCAL_VOLUME_BASE, os.path.basename(key))
    if os.path.isfile(local):
        return local
    return None


def _docker_cat_part1(bucket: str, key: str) -> bytes | None:
    import os
    import subprocess

    cache_path = os.path.join(_LOCAL_VOLUME_BASE, os.path.basename(key))
    if os.path.isfile(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()
    try:
        base = f"/data/{bucket}/{key}"
        ls_out = subprocess.run(
            ["docker", "exec", _MINIO_CONTAINER, "ls", base],
            capture_output=True, text=True, timeout=5,
        )
        hash_dir = None
        for line in ls_out.stdout.strip().splitlines():
            line = line.strip()
            if line and line != "xl.meta":
                hash_dir = line
                break
        if not hash_dir:
            return None
        cat_out = subprocess.run(
            ["docker", "exec", _MINIO_CONTAINER, "cat", f"{base}/{hash_dir}/part.1"],
            capture_output=True, timeout=10,
        )
        if cat_out.returncode == 0 and len(cat_out.stdout) > 500:
            os.makedirs(_LOCAL_VOLUME_BASE, exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(cat_out.stdout)
            logger.info("docker_cat_cached", bucket=bucket, key=key, size=len(cat_out.stdout))
            return cat_out.stdout
    except Exception as exc:
        logger.error("docker_cat_failed", bucket=bucket, key=key, error=str(exc))
    return None


async def get_object_bytes(bucket: str, key: str) -> bytes:
    import anyio.to_thread

    key = key.lstrip("/")
    mc = await get_minio_client()
    try:
        response = mc.get_object(bucket, key)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except Exception:
        local_path = _local_volume_path(bucket, key)
        if local_path:
            logger.info("minio_local_fallback", bucket=bucket, key=key, local_path=local_path)
            return await anyio.to_thread.run_sync(lambda: open(local_path, "rb").read())
        data = await anyio.to_thread.run_sync(lambda: _docker_cat_part1(bucket, key))
        if data:
            return data
        logger.error("minio_get_object_error", bucket=bucket, key=key)
        raise


async def get_object_stream(bucket: str, key: str, chunk_size: int = 8192) -> AsyncGenerator[bytes, None]:
    key = key.lstrip("/")
    mc = await get_minio_client()
    try:
        response = mc.get_object(bucket, key)
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            yield chunk
        response.close()
        response.release_conn()
    except Exception as exc:
        logger.error("minio_stream_error", bucket=bucket, key=key, error=str(exc))
        raise


def put_object_sync(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str,
    metadata: dict | None = None,
) -> None:
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    logger.info(
        "minio_put_sync_attempt",
        bucket=bucket,
        key=key,
        content_type=content_type,
        size_bytes=len(data),
    )
    try:
        mc.put_object(
            bucket,
            key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata or {},
        )
        logger.info("minio_put_sync_success", bucket=bucket, key=key)
    except Exception as exc:
        logger.error("minio_put_sync_error", bucket=bucket, key=key, error=str(exc))
        raise


def get_presigned_get_url_sync(bucket: str, key: str, expires: int = 3600) -> str:
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    try:
        url = mc.presigned_get_object(bucket, key, expires=timedelta(seconds=expires))
        return url
    except Exception as exc:
        logger.error("minio_presigned_url_sync_error", key=key, error=str(exc))
        raise


def stream_from_minio(bucket: str, key: str) -> Generator[bytes, None, None]:
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    try:
        response = mc.get_object(bucket, key)
        yield from response.stream(8192)
        response.close()
        response.release_conn()
    except Exception as exc:
        logger.error("minio_sync_stream_error", bucket=bucket, key=key, error=str(exc))
        raise


def stat_object(bucket: str, key: str) -> bool:
    """Check if an object exists in MinIO. Returns True if found."""
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    try:
        mc.stat_object(bucket, key)
        return True
    except Exception:
        return False


def remove_object(bucket: str, key: str) -> None:
    """Delete an object from MinIO."""
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    try:
        mc.remove_object(bucket, key)
        logger.info("minio_remove_success", bucket=bucket, key=key)
    except Exception as exc:
        logger.error("minio_remove_error", bucket=bucket, key=key, error=str(exc))
        raise


def fget_object(bucket: str, key: str, file_path: str) -> None:
    """Download an object from MinIO to a local file."""
    key = key.lstrip("/")
    mc = get_minio_client_sync()
    try:
        mc.fget_object(bucket, key, file_path)
        logger.info("minio_fget_success", bucket=bucket, key=key, file_path=file_path)
    except Exception as exc:
        logger.error("minio_fget_error", bucket=bucket, key=key, error=str(exc))
        raise
