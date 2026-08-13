from __future__ import annotations

import re

import pytest


def test_ws_metrics_registered():
    from app.api.metrics import (
        depth_inference_ms,
        ws_annotate_dropped_total,
        ws_annotate_duration_seconds,
        ws_annotate_frames_total,
    )

    ws_annotate_frames_total.labels(model_type="object_detection", status="ok").inc()
    ws_annotate_dropped_total.labels(model_type="object_detection", reason="busy").inc()
    ws_annotate_duration_seconds.labels(model_type="object_detection").observe(0.25)
    depth_inference_ms.observe(0.05)


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_ws_counters(db_session, test_client):
    from app.api.metrics import ws_annotate_frames_total

    ws_annotate_frames_total.labels(model_type="object_detection", status="ok").inc()

    resp = await test_client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "edgevision_ws_annotate_frames_total" in body
    assert "edgevision_ws_annotate_dropped_total" in body
    assert "edgevision_depth_inference_seconds" in body
    assert re.search(r"edgevision_ws_annotate_frames_total\{", body)
