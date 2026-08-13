from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_success

from app.core.config import settings

celery_app = Celery(
    "edgevision_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=600,
    task_time_limit=900,
    beat_schedule={
        "check-heartbeat-timeouts": {
            "task": "workers.check_heartbeat_timeouts",
            "schedule": 300.0,  # every 5 minutes
        },
        "expire-consents": {
            "task": "workers.expire_consents",
            "schedule": crontab(hour=2, minute=0),  # Daily at 02:00 UTC
        },
        "reconcile-stuck-batches": {
            "task": "workers.reconcile_stuck_batches",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

# Explicitly import studio tasks to ensure they're registered
# (autodiscover may not catch all patterns)
import app.workers.tasks  # noqa: E402, F401


@task_success.connect
def _on_task_success(sender=None, **kwargs):
    try:
        from app.api.metrics import celery_tasks_total

        celery_tasks_total.labels(task_name=sender.name, status="success").inc()
    except Exception:
        pass


@task_failure.connect
def _on_task_failure(sender=None, **kwargs):
    try:
        from app.api.metrics import celery_tasks_total

        celery_tasks_total.labels(task_name=sender.name, status="failure").inc()
    except Exception:
        pass
