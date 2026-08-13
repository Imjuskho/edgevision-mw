import enum


class NodeCategory(str, enum.Enum):
    ROAD = "ROAD"
    AGRI = "AGRI"
    WILDLIFE = "WILDLIFE"
    DOC = "DOC"
    BIOMETRIC = "BIOMETRIC"


class NodeStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"


class PIIMode(str, enum.Enum):
    STRICT = "STRICT"
    MODERATE = "MODERATE"
    NONE = "NONE"


class BatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    INGESTED = "INGESTED"
    REJECTED = "REJECTED"


class AnnotationStatus(str, enum.Enum):
    PENDING = "PENDING"
    AUTO_LABELED = "AUTO_LABELED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    QA_REVIEW = "QA_REVIEW"
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"


class DatasetStatus(str, enum.Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    FOR_SALE = "FOR_SALE"
    SOLD = "SOLD"
    RETRACTED = "RETRACTED"


class LicenseType(str, enum.Enum):
    PERPETUAL = "PERPETUAL"
    ANNUAL = "ANNUAL"
    EXCLUSIVE = "EXCLUSIVE"


class ExportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    ANNOTATOR = "ANNOTATOR"
    QA = "QA"
    BUYER = "BUYER"
    FIELD_TECH = "FIELD_TECH"


class ImageSource(str, enum.Enum):
    FILE = "file"
    WEBCAM = "webcam"
    URL = "url"
    DRONE = "drone"
    SCREEN_CAPTURE = "screen_capture"


class ModelType(str, enum.Enum):
    road_segmentation = "road_segmentation"
    agri_crop_classification = "agri_crop_classification"
    agri_health_classification = "agri_health_classification"
    object_detection = "object_detection"
    classification = "classification"


class ModelFormat(str, enum.Enum):
    ULTRALYTICS = "ultralytics"
    ONNX = "onnx"
    TORCHSCRIPT = "torchscript"


class TrainingStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ConsentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
