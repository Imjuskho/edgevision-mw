from app.api.admin import admin_router
from app.api.agri import agri_router
from app.api.analytics import analytics_router
from app.api.annotation import annotation_router
from app.api.annotations_live import annotations_live_router
from app.api.assignment import assignment_router
from app.api.billing import billing_router
from app.api.catalog import catalog_router
from app.api.clip_embed import clip_router
from app.api.compliance import compliance_router
from app.api.fleet import fleet_router
from app.api.health import health_router
from app.api.images import images_router as image_upload_router
from app.api.images import serve_router
from app.api.ingestion import ingestion_router
from app.api.metrics import metrics_router
from app.api.model_registry import model_registry_router
from app.api.prelabel import prelabel_router
from app.api.review import review_router
from app.api.road import road_router
from app.api.studio import studio_router
from app.api.studio_ai import studio_ai_router
from app.api.studio_intelligence import studio_intelligence_router
from app.api.studio_sync import router as studio_sync_router
from app.api.training import training_router
from app.api.ws_annotation import ws_annotation_router

__all__ = [
    "admin_router",
    "agri_router",
    "analytics_router",
    "annotation_router",
    "annotations_live_router",
    "assignment_router",
    "billing_router",
    "catalog_router",
    "clip_router",
    "compliance_router",
    "fleet_router",
    "health_router",
    "image_upload_router",
    "ingestion_router",
    "metrics_router",
    "model_registry_router",
    "prelabel_router",
    "review_router",
    "road_router",
    "serve_router",
    "studio_ai_router",
    "studio_intelligence_router",
    "studio_router",
    "studio_sync_router",
    "training_router",
    "ws_annotation_router",
]
