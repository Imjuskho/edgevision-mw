import enum


class NodeCategory(enum.StrEnum):
    ROAD = "ROAD"
    AGRI = "AGRI"
    WILDLIFE = "WILDLIFE"
    DOC = "DOC"
    BIOMETRIC = "BIOMETRIC"


class NodeStatus(enum.StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"


class PIIMode(enum.StrEnum):
    STRICT = "STRICT"
    MODERATE = "MODERATE"
    NONE = "NONE"


class BatchStatus(enum.StrEnum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    INGESTED = "INGESTED"
    REJECTED = "REJECTED"


class AnnotationStatus(enum.StrEnum):
    PENDING = "PENDING"
    AUTO_LABELED = "AUTO_LABELED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    QA_REVIEW = "QA_REVIEW"
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"


class DatasetStatus(enum.StrEnum):
    BUILDING = "BUILDING"
    READY = "READY"
    FOR_SALE = "FOR_SALE"
    SOLD = "SOLD"
    RETRACTED = "RETRACTED"


class LicenseType(enum.StrEnum):
    PERPETUAL = "PERPETUAL"
    ANNUAL = "ANNUAL"
    EXCLUSIVE = "EXCLUSIVE"


class ExportStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class UserRole(enum.StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    ANNOTATOR = "ANNOTATOR"
    QA = "QA"
    BUYER = "BUYER"
    FIELD_TECH = "FIELD_TECH"


class ImageSource(enum.StrEnum):
    FILE = "file"
    WEBCAM = "webcam"
    URL = "url"
    DRONE = "drone"
    SCREEN_CAPTURE = "screen_capture"


class ModelType(enum.StrEnum):
    road_segmentation = "road_segmentation"
    agri_crop_classification = "agri_crop_classification"
    agri_health_classification = "agri_health_classification"
    object_detection = "object_detection"
    classification = "classification"


class ModelFormat(enum.StrEnum):
    ULTRALYTICS = "ultralytics"
    ONNX = "onnx"
    TORCHSCRIPT = "torchscript"


class TrainingStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ConsentStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
