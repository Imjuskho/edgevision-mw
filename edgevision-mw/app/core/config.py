from decimal import Decimal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "EdgeVision-MW Control Plane"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_USER: str = "edgevision"
    POSTGRES_PASSWORD: str = "edgevision_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "edgevision_mw"

    DATABASE_URL: str = ""

    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""

    REDIS_URL: str = "redis://redis:6379/0"

    CELERY_TASK_HEARTBEAT_TTL: int = 300  # 5 minutes

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "edgevision-data-lake"
    MINIO_SECURE: bool = False

    ENVIRONMENT: str = "development"

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    NODE_HEARTBEAT_INTERVAL: int = 30
    STUCK_BATCH_THRESHOLD_MINUTES: int = 30

    ANNOTATION_TARGET_IAA: float = 0.96
    MINIMUM_ANNOTATOR_WAGE_MWK: Decimal = Decimal("5000.00")
    MWK_TO_USD_RATE: Decimal = Decimal("0.0006")

    MAX_EXPORT_JURISDICTIONS: list[str] = [
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
        "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
        "PL", "PT", "RO", "SK", "SI", "ES", "SE",
        "US",
        "GB",
        "CA",
        "AU",
    ]

    CELERY_BROKER_URL: str = "redis://redis:6379/1"

    REDIS_PASSWORD: str = "edgevision_redis"
    CORS_ORIGINS: str = ""

    INSTALL_TRAINING_DEPS: bool = False

    ROAD_SEG_MODEL_PATH: str = "models/road_seg/best.onnx"
    ROAD_SEG_CONF_THRESHOLD: float = 0.5

    AGRI_CROP_SEG_MODEL_PATH: str = ""
    AGRI_HEALTH_SEG_MODEL_PATH: str = ""
    AGRI_SEG_CONF_THRESHOLD: float = 0.35

    YOLOV8X_PATH: str = ""
    SAM_VIT_H_PATH: str = ""
    SAM_ENCODER_ONNX_PATH: str = ""
    SAM_DECODER_ONNX_PATH: str = ""
    CLIP_VIT_L_PATH: str = ""
    CLIP_VIT_B32_PATH: str = ""
    PRELABEL_YOLO_CLS_PATH: str = ""
    YOLOV8_SEG_MODEL_PATH: str = ""
    LOCATE_ANYTHING_MODEL_PATH: str = ""
    ROAD_SEGMENTER_BASE_MODEL: str = "yolov8n-seg.pt"
    DEPTH_MODEL_PATH: str = ""
    DEPTH_ANYTHING_MODEL_PATH: str = ""

    # Feature flags
    AUTO_PRELABEL_ON_UPLOAD: bool = True

    LOGIN_RATE_LIMIT_MAX: int = 5
    LOGIN_RATE_LIMIT_WINDOW: int = 60
    REGISTER_RATE_LIMIT_MAX: int = 3
    REGISTER_RATE_LIMIT_WINDOW: int = 60

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def model_post_init(self, __context: object) -> None:
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if not self.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set via environment variable. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )


settings = Settings()
