from sqlalchemy.orm import validates

from app.core.logging import get_logger

logger = get_logger("edgevision.models.mixins")


class StorageKeyMixin:
    """Auto-strip leading slashes from storage path columns.

    Apply to any model that stores MinIO keys or filesystem paths.
    Prevents NoSuchKey errors caused by paths like '/datasets/foo.jpg'.
    """

    PATH_COLUMNS = {
        "image_path",
        "thumbnail_path",
        "storage_key",
        "thumbnail_key",
        "artifact_path",
        "storage_path",
        "output_path",
        "file_path",
        "export_path",
        "model_path",
    }

    @validates(*PATH_COLUMNS)
    def _sanitize_path(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value.strip("/")) == 0:
            raise ValueError(f"{key} cannot be empty or just slashes")
        stripped = value.lstrip("/")
        if stripped != value:
            logger.warning(
                "leading_slash_stripped",
                extra={"column": key, "original": value, "stripped": stripped},
            )
        return stripped
