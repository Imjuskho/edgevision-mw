from __future__ import annotations

import asyncio
import sys
import uuid
from contextlib import asynccontextmanager

sys.path.insert(0, ".")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai import model_inference as model_inference_module
from app.ai.object_tracker import ByteTrack
from app.api.ws_annotation import ws_annotation_router
from app.core.security import create_access_token
from app.models.enums import ModelType


@pytest.fixture
def websocket_app(monkeypatch):
    class DummyEngine:
        def is_loaded(self) -> bool:
            return True

        def detect(self, image, conf_threshold=0.35):
            return []

    @asynccontextmanager
    async def fake_async_session():
        yield None

    async def fake_get_active_engine(*args, **kwargs):
        return DummyEngine()

    monkeypatch.setattr("app.core.database.async_session", fake_async_session)
    monkeypatch.setattr("app.api.ws_annotation.get_active_engine", fake_get_active_engine)

    app = FastAPI()
    app.include_router(ws_annotation_router)
    return app


def test_websocket_rejects_no_token(websocket_app):
    """WebSocket endpoint should deny unauthenticated websocket connections."""
    with TestClient(websocket_app) as client, pytest.raises(Exception):
        with client.websocket_connect("/ws/annotate/live?model_type=object_detection") as ws:
            ws.receive_json()


def test_websocket_accepts_valid_token(websocket_app):
    """WebSocket endpoint should accept a valid websocket token."""
    token = create_access_token(data={"sub": str(uuid.uuid4()), "role": "ADMIN"})

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(f"/ws/annotate/live?model_type=object_detection&token={token}") as ws,
    ):
        assert ws is not None


def test_websocket_alias_path_accepts_valid_token(websocket_app):
    """Legacy /api/v1/ws/annotate/live should also accept websocket connections."""
    token = create_access_token(data={"sub": str(uuid.uuid4()), "role": "ADMIN"})

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(f"/api/v1/ws/annotate/live?model_type=object_detection&token={token}") as ws,
    ):
        assert ws is not None


def test_websocket_rejects_bad_model_type(websocket_app):
    """WebSocket should reject invalid model_type."""
    token = create_access_token(data={"sub": str(uuid.uuid4()), "role": "ADMIN"})

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(f"/ws/annotate/live?model_type=invalid_type&token={token}") as ws,
    ):
        result = ws.receive_json()
        assert "error" in result


def test_websocket_accepts_bearer_header(websocket_app):
    """WebSocket should accept a bearer token sent in the Authorization header."""
    token = create_access_token(data={"sub": str(uuid.uuid4()), "role": "ADMIN"})

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(
            "/ws/annotate/live?model_type=object_detection",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws,
    ):
        assert ws is not None


def test_get_local_fallback_engine_searches_frontend_model_mount(monkeypatch):
    """Local fallback engine search should include mounted frontend/public/models."""

    class DummyEngine:
        def is_loaded(self) -> bool:
            return True

        def detect(self, image, conf_threshold=0.35):
            return []

    def fake_exists(path):
        return path.endswith("frontend/public/models/yolov8x.pt")

    monkeypatch.setattr(model_inference_module.os.path, "exists", fake_exists)
    monkeypatch.setattr(model_inference_module, "YOLODetector", lambda path: DummyEngine())

    engine = model_inference_module._get_local_fallback_engine(ModelType.object_detection)

    assert engine is not None
    assert engine.is_loaded() is True


def test_get_active_engine_falls_back_to_local_model(monkeypatch):
    """A local fallback engine should be used when no deployed model is active."""

    class DummyEngine:
        def is_loaded(self) -> bool:
            return True

        def detect(self, image, conf_threshold=0.35):
            return []

    async def fake_get_active_deployed_model(*args, **kwargs):
        return None

    monkeypatch.setattr(model_inference_module, "get_active_deployed_model", fake_get_active_deployed_model)
    monkeypatch.setattr(model_inference_module, "get_trained_engine", lambda artifact_path, model_type: DummyEngine())
    monkeypatch.setattr(model_inference_module, "_get_lkg", lambda model_type: None)
    monkeypatch.setattr(model_inference_module, "_set_lkg", lambda model_type, engine: None)
    monkeypatch.setattr(model_inference_module, "YOLODetector", lambda path: DummyEngine())

    async def run_check():
        return await model_inference_module.get_active_engine(None, ModelType.object_detection)

    engine = asyncio.run(run_check())
    assert engine is not None
    assert engine.is_loaded() is True


def test_get_active_engine_falls_back_when_deployed_engine_is_unloaded(monkeypatch):
    """A fallback engine should be used when the deployed engine cannot be loaded."""

    class UnloadedEngine:
        def is_loaded(self) -> bool:
            return False

        def detect(self, image, conf_threshold=0.35):
            return []

    class DummyFallbackEngine:
        def is_loaded(self) -> bool:
            return True

        def detect(self, image, conf_threshold=0.35):
            return []

    async def fake_get_active_deployed_model(*args, **kwargs):
        return type("DeployedModel", (), {"id": "1", "artifact_path": "artifact"})()

    monkeypatch.setattr(model_inference_module, "get_active_deployed_model", fake_get_active_deployed_model)
    monkeypatch.setattr(
        model_inference_module, "get_trained_engine", lambda artifact_path, model_type: UnloadedEngine()
    )
    monkeypatch.setattr(model_inference_module, "_get_lkg", lambda model_type: None)
    monkeypatch.setattr(model_inference_module, "_set_lkg", lambda model_type, engine: None)
    monkeypatch.setattr(model_inference_module, "_get_local_fallback_engine", lambda model_type: DummyFallbackEngine())

    async def run_check():
        return await model_inference_module.get_active_engine(object(), ModelType.object_detection)

    engine = asyncio.run(run_check())
    assert engine is not None
    assert engine.is_loaded() is True


def test_get_active_engine_uses_simple_fallback_when_yolo_missing(monkeypatch):
    """A lightweight fallback engine should be returned when local YOLO loading is unavailable."""

    class UnloadedYOLO:
        def __init__(self, path):
            self.path = path

        def is_loaded(self) -> bool:
            return False

    async def fake_get_active_deployed_model(*args, **kwargs):
        return None

    monkeypatch.setattr(model_inference_module, "get_active_deployed_model", fake_get_active_deployed_model)
    monkeypatch.setattr(model_inference_module, "_get_lkg", lambda model_type: None)
    monkeypatch.setattr(model_inference_module, "_set_lkg", lambda model_type, engine: None)
    monkeypatch.setattr(model_inference_module, "YOLODetector", lambda path: UnloadedYOLO(path))

    async def run_check():
        return await model_inference_module.get_active_engine(object(), ModelType.object_detection)

    engine = asyncio.run(run_check())
    assert engine is not None
    assert engine.is_loaded() is False
    assert engine.detect([]) == []


def test_byte_track_returns_tentative_tracks():
    tracker = ByteTrack(track_high_thresh=0.5, track_low_thresh=0.1)
    detections = [{"bbox": [0.0, 0.0, 10.0, 10.0], "class_name": "person", "confidence": 0.8}]

    result = tracker.update(detections)

    assert len(result) == 1
    assert result[0]["track_id"] == 1
    assert result[0]["class_name"] == "person"
    assert result[0]["confidence"] == pytest.approx(0.8)


def test_websocket_inference_returns_frame_size(websocket_app):
    token = create_access_token(data={"sub": "test-user", "role": "ADMIN"})

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(f"/ws/annotate/live?model_type=object_detection&token={token}") as ws,
    ):
        cv2 = pytest.importorskip("cv2")
        np = pytest.importorskip("numpy")
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        success, buf = cv2.imencode(".jpg", img)
        assert success
        ws.send_bytes(buf.tobytes())

        result = ws.receive_json()
        assert result["frame_width"] == 8
        assert result["frame_height"] == 8
        assert isinstance(result["annotations"], list)
        assert "depth_available" in result
        assert result.get("dropped") is False


def test_websocket_drops_concurrent_frame(websocket_app, monkeypatch):
    import time

    class SlowEngine:
        def is_loaded(self) -> bool:
            return True

        def detect(self, image, conf_threshold=0.35):
            time.sleep(0.3)
            return []

    async def slow_get_active_engine(*args, **kwargs):
        return SlowEngine()

    monkeypatch.setattr("app.api.ws_annotation.get_active_engine", slow_get_active_engine)

    token = create_access_token(data={"sub": "test-user", "role": "ADMIN"})
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(f"/ws/annotate/live?model_type=object_detection&token={token}") as ws,
    ):
        ws.send_bytes(buf.tobytes())
        ws.send_bytes(buf.tobytes())
        first = ws.receive_json()
        second = ws.receive_json()
        responses = [first, second]
        dropped = [r for r in responses if r.get("dropped")]
        assert len(dropped) >= 1
        assert any(r.get("busy") for r in dropped)


def _tracked_person(*args, **kwargs):
    return [
        {
            "track_id": 7,
            "bbox": [0, 0, 50, 50],
            "class_name": "person",
            "confidence": 0.85,
        }
    ], [{"bbox": [0, 0, 50, 50], "class_name": "person", "confidence": 0.85}]


def test_websocket_events_mode_emits_event(websocket_app, monkeypatch):
    """events=1 should emit a presence event for a tracked pedestrian."""
    monkeypatch.setattr(
        "app.api.ws_annotation.run_seg_primary_detection",
        _tracked_person,
    )

    token = create_access_token(data={"sub": "test-user", "role": "ADMIN"})
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(
            f"/ws/annotate/live?model_type=object_detection&token={token}&events=1"
        ) as ws,
    ):
        ws.send_bytes(buf.tobytes())
        event_msg = ws.receive_json()
        assert event_msg["type"] == "event", event_msg
        assert event_msg["event"]["event_type"] == "presence"
        assert event_msg["event"]["rule_id"] == "presence_pedestrian"
        assert event_msg["event"]["track_id"] == 7

        result = ws.receive_json()
        assert result.get("dropped") is False


def test_websocket_events_disabled_when_events_param_zero(websocket_app, monkeypatch):
    """events=0 should suppress event messages while frames still stream."""
    monkeypatch.setattr(
        "app.api.ws_annotation.run_seg_primary_detection",
        _tracked_person,
    )

    token = create_access_token(data={"sub": "test-user", "role": "ADMIN"})
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(
            f"/ws/annotate/live?model_type=object_detection&token={token}&events=0"
        ) as ws,
    ):
        ws.send_bytes(buf.tobytes())
        result = ws.receive_json()
        assert result.get("dropped") is False
        assert "type" not in result


def test_websocket_auto_save_sends_event_saved(websocket_app, monkeypatch):
    """An auto_save presence rule should produce an event_saved confirmation."""
    from app.ai.events import PRESENCE, EventEngine, EventRule

    monkeypatch.setattr(
        "app.api.ws_annotation.run_seg_primary_detection",
        _tracked_person,
    )

    custom_rule = EventRule(
        rule_id="presence_pedestrian",
        rule_type=PRESENCE,
        name="Pedestrian present",
        taxonomy_labels=("pedestrian_roadside", "person"),
        min_confidence=0.0,
        cooldown_seconds=0.0,
        auto_save=True,
        pre_frames=1,
        post_frames=0,
    )
    monkeypatch.setattr(
        "app.api.ws_annotation.EventEngine",
        lambda rules: EventEngine([custom_rule]),
    )

    token = create_access_token(data={"sub": "test-user", "role": "ADMIN"})
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)

    with (
        TestClient(websocket_app) as client,
        client.websocket_connect(
            f"/ws/annotate/live?model_type=object_detection&token={token}&events=1&auto_save=1&dataset_id=abc-123"
        ) as ws,
    ):
        ws.send_bytes(buf.tobytes())

        first = ws.receive_json()
        assert first["type"] == "event", first

        second = ws.receive_json()
        assert second["type"] == "event_saved", second
        assert second["dataset_id"] == "abc-123"
        assert second["frames"] >= 0

        result = ws.receive_json()
        assert result.get("dropped") is False
