from __future__ import annotations

from datetime import datetime

import pytest

from app.ai.events import (
    CONFIDENCE_DROP,
    DISTANCE,
    DWELL,
    PRESENCE,
    EventEngine,
    EventRule,
    FrameRingBuffer,
    MAX_TRACK_GAP_SECONDS,
    default_rules,
    rules_from_dicts,
)


def _det(track_id=1, cls="person", taxonomy="pedestrian_roadside", conf=0.9, bbox=None):
    return {
        "track_id": track_id,
        "class_name": cls,
        "taxonomy_label": taxonomy,
        "confidence": conf,
        "smoothed_confidence": conf,
        "bbox": bbox or [10.0, 10.0, 40.0, 80.0],
    }


def _epoch(hhmm: str, day: int = 0) -> float:
    hh, mm = (int(v) for v in hhmm.split(":"))
    return datetime(2026, 1, 1 + day, hh, mm).astimezone().timestamp()


class TestDwell:
    def test_fires_after_dwell_window(self):
        rule = EventRule(rule_id="r1", rule_type=DWELL, name="dwell", taxonomy_labels=("pedestrian_roadside",), dwell_seconds=5.0)
        engine = EventEngine([rule])
        det = _det()
        assert engine.update([det], now=0.0) == []
        assert engine.update([det], now=2.0) == []
        assert engine.update([det], now=4.0) == []
        events = engine.update([det], now=6.0)
        assert len(events) == 1
        assert events[0].rule_id == "r1"
        assert events[0].duration_seconds == pytest.approx(6.0)

    def test_resets_after_gap(self):
        rule = EventRule(rule_id="r1", rule_type=DWELL, name="dwell", dwell_seconds=3.0)
        engine = EventEngine([rule])
        det = _det()
        assert engine.update([det], now=0.0) == []
        # Long gap (> MAX_TRACK_GAP) resets the continuous clock.
        assert engine.update([det], now=100.0) == []
        assert engine.update([det], now=102.0) == []
        events = engine.update([det], now=103.5)
        assert len(events) == 1

    def test_cooldown_dedups(self):
        rule = EventRule(
            rule_id="r1",
            rule_type=DWELL,
            name="dwell",
            dwell_seconds=2.0,
            cooldown_seconds=10.0,
        )
        engine = EventEngine([rule])
        det = _det()
        fired_at: list[float] = []
        for now in range(0, 13):
            events = engine.update([det], now=float(now))
            fired_at.extend(e.triggered_at for e in events)
        assert fired_at == [2.0, 12.0]


class TestFilters:
    def test_class_filter(self):
        rule = EventRule(
            rule_id="r1", rule_type=PRESENCE, name="p", taxonomy_labels=("car_private",)
        )
        engine = EventEngine([rule])
        assert engine.update([_det(cls="person", taxonomy="pedestrian_roadside")], now=1.0) == []
        events = engine.update([_det(cls="car", taxonomy="car_private")], now=2.0)
        assert len(events) == 1

    def test_confidence_filter(self):
        rule = EventRule(rule_id="r1", rule_type=PRESENCE, name="p", min_confidence=0.5)
        engine = EventEngine([rule])
        assert engine.update([_det(conf=0.4)], now=1.0) == []
        assert len(engine.update([_det(conf=0.6)], now=2.0)) == 1

    def test_disabled_rule_never_fires(self):
        rule = EventRule(rule_id="r1", rule_type=PRESENCE, name="p", enabled=False)
        engine = EventEngine([rule])
        assert engine.update([_det()], now=1.0) == []

    def test_time_of_day_window(self):
        rule = EventRule(rule_id="r1", rule_type=PRESENCE, name="p", time_of_day=("08:00", "10:00"))
        engine = EventEngine([rule])
        assert engine.update([_det()], now=_epoch("07:59")) == []
        assert len(engine.update([_det()], now=_epoch("08:30"))) == 1
        assert engine.update([_det()], now=_epoch("10:01")) == []

    def test_time_of_day_wraparound(self):
        rule = EventRule(rule_id="r1", rule_type=PRESENCE, name="p", time_of_day=("22:00", "06:00"), cooldown_seconds=0)
        engine = EventEngine([rule])
        assert engine.update([_det()], now=_epoch("21:00")) == []
        assert len(engine.update([_det()], now=_epoch("23:30"))) == 1
        assert len(engine.update([_det()], now=_epoch("00:30", day=1))) == 1
        assert engine.update([_det()], now=_epoch("12:00", day=1)) == []


class TestConfidenceDrop:
    def test_fires_on_collapse(self):
        rule = EventRule(
            rule_id="r1",
            rule_type=CONFIDENCE_DROP,
            name="drop",
            confidence_drop_from=0.55,
            confidence_drop_below=0.3,
        )
        engine = EventEngine([rule])
        assert engine.update([_det(conf=0.9)], now=1.0) == []
        events = engine.update([_det(conf=0.2)], now=2.0)
        assert len(events) == 1
        assert events[0].details["max_confidence"] == pytest.approx(0.9)


class TestDistance:
    def test_fires_within_threshold(self):
        rule = EventRule(rule_id="r1", rule_type=DISTANCE, name="d", distance_m_max=3.0)
        engine = EventEngine([rule])
        far = _det()
        far["distance_m"] = 4.0
        assert engine.update([far], now=1.0) == []
        near = _det()
        near["distance_m"] = 2.5
        events = engine.update([near], now=2.0)
        assert len(events) == 1
        assert events[0].details["distance_m"] == pytest.approx(2.5)

    def test_noop_without_distance(self):
        rule = EventRule(rule_id="r1", rule_type=DISTANCE, name="d", distance_m_max=3.0)
        engine = EventEngine([rule])
        assert engine.update([_det()], now=1.0) == []

    def test_unrated_distance_rule_is_counted(self):
        rule = EventRule(rule_id="close_approach", rule_type=DISTANCE, name="d", distance_m_max=3.0)
        engine = EventEngine([rule])
        for now in (1.0, 2.0, 3.0):
            assert engine.update([_det()], now=now) == []
        summary = engine.state_summary()
        assert summary["distance_unrated_by_rule"] == {"close_approach": 3}


class TestRulesParsing:
    def test_rules_from_dicts(self):
        raw = [
            {
                "rule_id": "a",
                "rule_type": "presence",
                "name": "A",
                "class_names": ["person"],
                "time_of_day": ["09:00", "17:00"],
            }
        ]
        rules = rules_from_dicts(raw)
        assert len(rules) == 1
        assert rules[0].rule_id == "a"
        assert rules[0].class_names == ("person",)
        assert rules[0].time_of_day == ("09:00", "17:00")

    def test_rules_from_dicts_falls_back_to_defaults_on_empty(self):
        assert rules_from_dicts([]) and rules_from_dicts(None)
        assert [r.rule_id for r in rules_from_dicts(None)] == [r.rule_id for r in default_rules()]

    def test_invalid_rule_type_rejected(self):
        with pytest.raises(ValueError):
            EventRule(rule_id="x", rule_type="bogus", name="x")

    def test_invalid_time_window_rejected(self):
        with pytest.raises(ValueError):
            EventRule(rule_id="x", rule_type=PRESENCE, name="x", time_of_day=("9:00", "25:00"))

    def test_default_rules_are_independent_instances(self):
        first = default_rules()
        second = default_rules()
        assert [r.rule_id for r in first] == [r.rule_id for r in second]
        assert first is not second
        assert first[0] is not second[0]
        assert first[0].to_dict() == second[0].to_dict()


class TestFrameRingBuffer:
    def test_keeps_last_n(self):
        buf = FrameRingBuffer(maxlen=4)
        for i in range(6):
            buf.push(frame_bytes=b"f", annotations=[], timestamp=float(i), frame_index=i)
        recent = buf.recent(4)
        assert [e["frame_index"] for e in recent] == [2, 3, 4, 5]

    def test_recent_clamps_to_size(self):
        buf = FrameRingBuffer(maxlen=4)
        buf.push(frame_bytes=b"a", annotations=[], timestamp=0.0, frame_index=0)
        assert len(buf.recent(10)) == 1

    def test_clear(self):
        buf = FrameRingBuffer(maxlen=4)
        buf.push(frame_bytes=b"a", annotations=[], timestamp=0.0, frame_index=0)
        buf.clear()
        assert len(buf) == 0
