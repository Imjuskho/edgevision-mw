"""Tests for GeoPoint and Detection schemas (F1+F2)."""

import pytest
from pydantic import ValidationError

from app.schemas.common import Detection, GeoPoint

# ── GeoPoint: valid inputs ───────────────────────────────────────────────────


def test_geopoint_valid_blantyre():
    gp = GeoPoint(lat=-15.7861, lng=35.0058)
    assert gp.lat == pytest.approx(-15.7861)
    assert gp.lng == pytest.approx(35.0058)


def test_geopoint_valid_lilongwe():
    gp = GeoPoint(lat=-13.9626, lng=33.7741)
    assert gp.lat == pytest.approx(-13.9626)


def test_geopoint_valid_extreme_values():
    gp = GeoPoint(lat=-90.0, lng=-180.0)
    assert gp.lat == -90.0
    assert gp.lng == -180.0

    gp2 = GeoPoint(lat=90.0, lng=180.0)
    assert gp2.lat == 90.0
    assert gp2.lng == 180.0


# ── GeoPoint: invalid inputs ─────────────────────────────────────────────────


def test_geopoint_zero_origin_rejected():
    with pytest.raises(ValidationError, match="invalid coordinates"):
        GeoPoint(lat=0.0, lng=0.0)


def test_geopoint_lat_out_of_range():
    with pytest.raises(ValidationError):
        GeoPoint(lat=91.0, lng=35.0)

    with pytest.raises(ValidationError):
        GeoPoint(lat=-91.0, lng=35.0)


def test_geopoint_lng_out_of_range():
    with pytest.raises(ValidationError):
        GeoPoint(lat=-15.0, lng=181.0)

    with pytest.raises(ValidationError):
        GeoPoint(lat=-15.0, lng=-181.0)


def test_geopoint_lat_zero_lng_nonzero_valid():
    gp = GeoPoint(lat=0.0, lng=35.0)
    assert gp.lat == 0.0
    assert gp.lng == 35.0


def test_geopoint_lng_zero_lat_nonzero_valid():
    gp = GeoPoint(lat=-15.0, lng=0.0)
    assert gp.lng == 0.0


# ── Detection: valid inputs ──────────────────────────────────────────────────


def test_detection_valid_minimal():
    d = Detection(
        class_id=0,
        class_name="CAR",
        confidence=0.95,
        bbox=[0.1, 0.2, 0.3, 0.4],
    )
    assert d.class_id == 0
    assert d.class_name == "CAR"
    assert d.mask is None
    assert d.track_id is None


def test_detection_valid_all_fields():
    d = Detection(
        class_id=5,
        class_name="PERSON",
        confidence=1.0,
        bbox=[0.0, 0.0, 1.0, 1.0],
        mask="RLE_abc123",
        track_id=42,
    )
    assert d.mask == "RLE_abc123"
    assert d.track_id == 42


def test_detection_rejects_zero_size_bbox():
    with pytest.raises(ValidationError):
        Detection(
            class_id=1,
            class_name="VEHICLE",
            confidence=0.0,
            bbox=[0.0, 0.0, 0.0, 0.0],
        )


def test_detection_rejects_out_of_frame_bbox():
    with pytest.raises(ValidationError):
        Detection(
            class_id=1,
            class_name="TRUCK",
            confidence=0.5,
            bbox=[1.0, 1.0, 1.0, 1.0],
        )


# ── Detection: invalid inputs ────────────────────────────────────────────────


def test_detection_negative_class_id_rejected():
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Detection(
            class_id=-1,
            class_name="CAR",
            confidence=0.9,
            bbox=[0.1, 0.2, 0.3, 0.4],
        )


def test_detection_empty_class_name_rejected():
    with pytest.raises(ValidationError, match="at least 1 character"):
        Detection(
            class_id=0,
            class_name="",
            confidence=0.9,
            bbox=[0.1, 0.2, 0.3, 0.4],
        )


def test_detection_confidence_out_of_range():
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=1.5,
            bbox=[0.1, 0.2, 0.3, 0.4],
        )

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=-0.1,
            bbox=[0.1, 0.2, 0.3, 0.4],
        )


def test_detection_bbox_wrong_length():
    with pytest.raises(ValidationError, match="at least 4 items"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=0.9,
            bbox=[0.1, 0.2, 0.3],
        )

    with pytest.raises(ValidationError, match="at most 4 items"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=0.9,
            bbox=[0.1, 0.2, 0.3, 0.4, 0.5],
        )


def test_detection_bbox_value_out_of_range():
    with pytest.raises(ValueError, match="bbox values"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=0.9,
            bbox=[0.1, 0.2, 0.3, 1.5],
        )


def test_detection_bbox_negative_value():
    with pytest.raises(ValueError, match="bbox values"):
        Detection(
            class_id=0,
            class_name="CAR",
            confidence=0.9,
            bbox=[-0.1, 0.2, 0.3, 0.4],
        )


# ── Detection: from dict (EventPacket use case) ──────────────────────────────


def test_detection_from_dict():
    data = {
        "class_id": 2,
        "class_name": "BUS",
        "confidence": 0.87,
        "bbox": [0.15, 0.25, 0.35, 0.45],
    }
    d = Detection(**data)
    assert d.class_name == "BUS"
    assert d.track_id is None
