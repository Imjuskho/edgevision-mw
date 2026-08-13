from pydantic import BaseModel, ConfigDict


class ImageUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    annotation_id: str
    status: str
    checksum: str
    source: str = "file"


class BatchUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str
    dataset_name: str
    uploaded: int
    skipped: int
    total: int
    images: list[ImageUploadResponse]
    errors: list[dict[str, str]] = []
    source: str = "file"


class DuplicateCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_duplicate: bool
    existing_annotation_id: str | None = None
    message: str
