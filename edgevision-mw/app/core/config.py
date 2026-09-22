from __future__ import annotations

import warnings
from decimal import Decimal

from pydantic_settings import BaseSettings

_INSECURE_DEFAULTS: dict[str, str] = {
    "POSTGRES_PASSWORD": "edgevision_secret",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minioadmin",
    "REDIS_PASSWORD": "edgevision_redis",
}


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

    SMS_PROVIDER_URL: str = ""
    PUSH_PROVIDER_URL: str = ""

    ANNOTATION_TARGET_IAA: float = 0.96
    MINIMUM_ANNOTATOR_WAGE_MWK: Decimal = Decimal("5000.00")
    MWK_TO_USD_RATE: Decimal = Decimal("0.0006")

    # D1: Operator stipend
    OPERATOR_STIPEND_MWK: Decimal = Decimal("42500.00")
    OPERATOR_STIPEND_DAY: int = 1  # day of month to process stipends

    # D2: Buyer dashboard
    CORRIDOR_UNIT_PRICE_USD: Decimal = Decimal("50.00")  # per node per month
    SUBSCRIPTION_DEFAULT_NODES: int = 5

    # D3: Subject rewards
    SUBJECT_REWARD_THRESHOLD_MWK: Decimal = Decimal("500.00")
    SMS_GATEWAY_URL: str = ""
    SMS_GATEWAY_API_KEY: str = ""
    AIRTIME_PROVIDER_URL: str = ""
    AIRTIME_PROVIDER_API_KEY: str = ""

    MAX_EXPORT_JURISDICTIONS: list[str] = [
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
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

    # Depth calibration
    DEPTH_CALIBRATION_ENABLED: bool = True
    DEPTH_CALIBRATION_TOLERANCE_NEAR_M: float = 0.5
    DEPTH_CALIBRATION_TOLERANCE_MID_M: float = 1.5
    DEPTH_CALIBRATION_TOLERANCE_FAR_M: float = 3.0
    DEPTH_CALIBRATION_MAX_ERROR_PCT: float = 20.0
    DEPTH_DRIFT_WARN_PCT: float = 15.0
    DEPTH_DRIFT_FAIL_PCT: float = 25.0
    DEPTH_CALIBRATION_MIN_POINTS: int = 1

    # Feature flags
    AUTO_PRELABEL_ON_UPLOAD: bool = True
    LEARNED_TRAJECTORY_MODEL: bool = False
    TRAJECTORY_LSTM_WEIGHTS: str = ""

    # Frontier capabilities
    TRAJECTORY_PREDICTION_HORIZONS: list[float] = [0.5, 1.0, 2.0, 3.0, 5.0]
    TRAJECTORY_ROAD_INTERSECTION_THRESHOLD_M: float = 2.0
    ANOMALY_BASELINE_WINDOW: int = 100
    ANOMALY_DETECTION_THRESHOLD: float = 2.0
    ANOMALY_DESCRIPTION_ENABLED: bool = True

    # F4: Open-set anomaly detection sub-package
    ANOMALY_MIN_TRAINING_FRAMES: int = 30
    ANOMALY_EMBEDDING_DIM: int = 16
    ANOMALY_GMM_COMPONENTS: int = 3
    ANOMALY_GMM_MAX_ITER: int = 100
    ANOMALY_GMM_TOLERANCE: float = 1e-4
    ANOMALY_VLM_DESCRIPTION_ENABLED: bool = True
    ANOMALY_TEMPORAL_SMOOTH_WINDOW: int = 10
    ANOMALY_TEMPORAL_MIN_FLAGS: int = 3
    SCENE_RECONSTRUCTION_KEYFRAME_INTERVAL: int = 30
    SCENE_STATIC_OBJECT_THRESHOLD: int = 5
    SCENE_CHANGE_DETECTION_ENABLED: bool = True

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
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )

        if self.ENVIRONMENT == "production":
            for field, default_val in _INSECURE_DEFAULTS.items():
                current = getattr(self, field, None)
                if current == default_val:
                    raise ValueError(
                        f"Production requires {field} to be set to a unique value "
                        f"(not the default '{default_val}')."
                    )

        self._validate_provider_pairs("SMS_GATEWAY", self.SMS_GATEWAY_URL, self.SMS_GATEWAY_API_KEY)
        self._validate_provider_pairs("AIRTIME_PROVIDER", self.AIRTIME_PROVIDER_URL, self.AIRTIME_PROVIDER_API_KEY)
        self._validate_provider_pairs("SMS_PROVIDER", self.SMS_PROVIDER_URL, "")
        self._validate_provider_pairs("PUSH_PROVIDER", self.PUSH_PROVIDER_URL, "")

    @staticmethod
    def _validate_provider_pairs(name: str, url: str, api_key: str) -> None:
        if url and not api_key:
            warnings.warn(
                f"{name}_URL is set but {name}_API_KEY is empty — provider calls will fail.",
                stacklevel=2,
            )
        elif api_key and not url:
            warnings.warn(
                f"{name}_API_KEY is set but {name}_URL is empty — provider calls will fail.",
                stacklevel=2,
            )


settings = Settings()
