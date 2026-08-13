from __future__ import annotations

import re

import pytest

from app.models.dataset import Dataset
from app.models.enums import DatasetStatus, LicenseType


@pytest.mark.asyncio
async def test_metrics_gauges_populated(db_session, test_client):

    ds = Dataset(
        dataset_id=f"MTR-{__import__('uuid').uuid4().hex[:8]}",
        name="Metrics Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=10,
        classes={"vehicle": 5},
        annotations_per_image=1.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={},
        demographic_report={},
        consent_coverage_pct=1.0,
        pii_scrub_verified=True,
        iaa_score=0.9,
        formats=[],
        price_usd=100,
        license_type=LicenseType.ANNUAL,
    )
    db_session.add(ds)
    await db_session.commit()

    resp = await test_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text

    assert "edgevision_http_requests_total" in body
    assert "edgevision_datasets_total" in body
    assert "edgevision_active_sessions" in body
    assert "edgevision_celery_task_queue_depth" in body

    assert re.search(r"edgevision_datasets_total [0-9.]+", body)
