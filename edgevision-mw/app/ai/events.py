"""Rule-based perception events on top of live tracking.

Pure, framework-free logic powering the Sprint 3 event layer: per-track
dwell-time / presence / confidence-drop detection, a configurable rules
engine, and a pre/post frame ring buffer for auto-saving clips.

Feeds from the ByteTrack output in ``app.ai.live_inference``: each detection
carries ``track_id``, ``class_name``, ``taxonomy_label``, ``confidence``,
``smoothed_confidence``, and ``bbox`` (xyxy).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

# Rule type constants.
DWELL = "dwell"
PRESENCE = "presence"
CONFIDENCE_DROP = "confidence_drop"
DISTANCE = "distance"

VALID_RULE_TYPES = frozenset({DWELL, PRESENCE, CONFIDENCE_DROP, DISTANCE})

# A track missing longer than this resets its continuous-presence clock.
MAX_TRACK_GAP_SECONDS = 2.0
# Track states are pruned after this long without being seen.
TRACK_STATE_TTL_SECONDS = 120.0
# Bounded trajectory history kept per track (centroid + timestamp).
TRAJECTORY_HISTORY_LEN = 32


def _dt_for(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch)


def _now_hhmm(epoch: float) -> str:
    return _dt_for(epoch).strftime("%H:%M")


def _in_time_window(hhmm: str, window: tuple[str, str] | None) -> bool:
    if window is None:
        return True
    start, end = window
    if start == end:
        return True
    if start < end:
        return start <= hhmm <= end
    return hhmm >= start or hhmm <= end


def _confidence_of(det: dict) -> float:
    return float(det.get("smoothed_confidence", det.get("confidence", 0.0)))


def _bbox_xyxy(det: dict) -> list[float]:
    bbox = det.get("bbox") or det.get("bbox_xyxy") or []
    return [float(v) for v in bbox[:4]]


def _centroid(det: dict) -> tuple[float, float]:
    bbox = _bbox_xyxy(det)
    if len(bbox) >= 4 and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    return (0.0, 0.0)


@dataclass(frozen=True)
class EventRule:
    rule_id: str
    rule_type: str
    name: str
    enabled: bool = True
    class_names: tuple[str, ...] = ()
    taxonomy_labels: tuple[str, ...] = ()
    dwell_seconds: float = 5.0
    min_confidence: float = 0.0
    confidence_drop_below: float = 0.3
    confidence_drop_from: float = 0.55
    distance_m_max: float | None = None
    time_of_day: tuple[str, str] | None = None
    cooldown_seconds: float = 30.0
    auto_save: bool = True
    pre_frames: int = 6
    post_frames: int = 4
    alert: bool = False
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rule_type not in VALID_RULE_TYPES:
            raise ValueError(f"Invalid rule_type: {self.rule_type}")
        if self.time_of_day is not None:
            start, end = self.time_of_day
            if not (len(start) == 5 and len(end) == 5):
                raise ValueError(f"time_of_day must be ('HH:MM', 'HH:MM'), got {self.time_of_day}")
            self._validate_hhmm(start)
            self._validate_hhmm(end)

    @staticmethod
    def _validate_hhmm(value: str) -> None:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"Invalid time_of_day component: {value}") from exc

    def matches_class(self, det: dict) -> bool:
        if self.class_names and det.get("class_name") in self.class_names:
            return True
        if self.taxonomy_labels and det.get("taxonomy_label") in self.taxonomy_labels:
            return True
        if not self.class_names and not self.taxonomy_labels:
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "name": self.name,
            "enabled": self.enabled,
            "class_names": list(self.class_names),
            "taxonomy_labels": list(self.taxonomy_labels),
            "dwell_seconds": self.dwell_seconds,
            "min_confidence": self.min_confidence,
            "confidence_drop_below": self.confidence_drop_below,
            "confidence_drop_from": self.confidence_drop_from,
            "distance_m_max": self.distance_m_max,
            "time_of_day": list(self.time_of_day) if self.time_of_day else None,
            "cooldown_seconds": self.cooldown_seconds,
            "auto_save": self.auto_save,
            "pre_frames": self.pre_frames,
            "post_frames": self.post_frames,
            "alert": self.alert,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "EventRule":
        def _tuple(key: str) -> tuple[str, ...]:
            value = raw.get(key)
            if not value:
                return ()
            if isinstance(value, str):
                return (value,)
            return tuple(str(v) for v in value)

        time_window: tuple[str, str] | None = None
        raw_window = raw.get("time_of_day")
        if isinstance(raw_window, (list, tuple)) and len(raw_window) >= 2:
            time_window = (str(raw_window[0]), str(raw_window[1]))

        distance = raw.get("distance_m_max")
        return cls(
            rule_id=str(raw.get("rule_id", uuid4().hex)),
            rule_type=str(raw.get("rule_type", DWELL)),
            name=str(raw.get("name", raw.get("rule_id", "event_rule"))),
            enabled=bool(raw.get("enabled", True)),
            class_names=_tuple("class_names"),
            taxonomy_labels=_tuple("taxonomy_labels"),
            dwell_seconds=float(raw.get("dwell_seconds", 5.0)),
            min_confidence=float(raw.get("min_confidence", 0.0)),
            confidence_drop_below=float(raw.get("confidence_drop_below", 0.3)),
            confidence_drop_from=float(raw.get("confidence_drop_from", 0.55)),
            distance_m_max=float(distance) if distance is not None else None,
            time_of_day=time_window,
            cooldown_seconds=float(raw.get("cooldown_seconds", 30.0)),
            auto_save=bool(raw.get("auto_save", True)),
            pre_frames=int(raw.get("pre_frames", 6)),
            post_frames=int(raw.get("post_frames", 4)),
            alert=bool(raw.get("alert", False)),
            payload=dict(raw.get("payload") or {}),
        )


DEFAULT_EVENT_RULES: list[EventRule] = [
    EventRule(
        rule_id="dwell_pedestrian_roadside",
        rule_type=DWELL,
        name="Pedestrian dwelling at roadside",
        taxonomy_labels=("pedestrian_roadside", "person"),
        dwell_seconds=8.0,
        min_confidence=0.35,
        cooldown_seconds=45.0,
        auto_save=True,
        alert=True,
        pre_frames=6,
        post_frames=4,
    ),
    EventRule(
        rule_id="dwell_vehicle",
        rule_type=DWELL,
        name="Vehicle dwelling in frame",
        taxonomy_labels=("car_private", "truck_freight", "minibus", "motorcycle_kabaza"),
        dwell_seconds=6.0,
        min_confidence=0.4,
        cooldown_seconds=60.0,
        auto_save=True,
        alert=True,
        pre_frames=6,
        post_frames=4,
    ),
    EventRule(
        rule_id="presence_pedestrian",
        rule_type=PRESENCE,
        name="Pedestrian present at roadside",
        taxonomy_labels=("pedestrian_roadside",),
        min_confidence=0.45,
        cooldown_seconds=20.0,
        auto_save=False,
    ),
    EventRule(
        rule_id="confidence_drop_track",
        rule_type=CONFIDENCE_DROP,
        name="Track confidence collapse",
        min_confidence=0.0,
        confidence_drop_from=0.55,
        confidence_drop_below=0.3,
        cooldown_seconds=30.0,
        auto_save=False,
    ),
    EventRule(
        rule_id="close_approach",
        rule_type=DISTANCE,
        name="Object within distance threshold",
        class_names=(),
        distance_m_max=3.0,
        min_confidence=0.4,
        cooldown_seconds=30.0,
        auto_save=True,
        alert=True,
        pre_frames=6,
        post_frames=4,
    ),
]


def default_rules() -> list[EventRule]:
    return [EventRule.from_dict(rule.to_dict()) for rule in DEFAULT_EVENT_RULES]


def rules_from_dicts(raw_list: list[dict] | None) -> list[EventRule]:
    if not raw_list:
        return default_rules()
    rules: list[EventRule] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        try:
            rules.append(EventRule.from_dict(raw))
        except ValueError:
            continue
    return rules or default_rules()


@dataclass
class TrackEventState:
    track_id: int
    class_name: str
    taxonomy_label: str
    first_seen: float
    last_seen: float
    continuous_since: float
    max_confidence: float
    bbox: list[float]
    missing_since: float | None = None
    trajectory: deque = field(default_factory=lambda: deque(maxlen=TRAJECTORY_HISTORY_LEN))
    fired_cooldowns: dict[str, float] = field(default_factory=dict)

    def is_stale(self, now: float) -> bool:
        return (now - self.last_seen) > TRACK_STATE_TTL_SECONDS

    def continuous_seconds(self, now: float) -> float:
        return max(0.0, now - self.continuous_since)

    def touch(self, det: dict, now: float) -> None:
        gap = now - self.last_seen
        confidence = _confidence_of(det)
        self.max_confidence = max(self.max_confidence, confidence)
        self.bbox = _bbox_xyxy(det)
        self.taxonomy_label = str(det.get("taxonomy_label", self.taxonomy_label))
        self.class_name = str(det.get("class_name", self.class_name))
        if self.missing_since is not None:
            if gap > MAX_TRACK_GAP_SECONDS:
                self.continuous_since = now
            self.missing_since = None
        elif gap > MAX_TRACK_GAP_SECONDS:
            self.continuous_since = now
        self.last_seen = now
        self.trajectory.append((*_centroid(det), now))

    def mark_missing(self, now: float) -> bool:
        if self.missing_since is None:
            self.missing_since = now
        stale = (now - self.last_seen) > MAX_TRACK_GAP_SECONDS
        if stale:
            self.continuous_since = now
        return stale


@dataclass
class PerceptionEvent:
    event_id: str
    event_type: str
    rule_id: str
    rule_name: str
    track_id: int
    class_name: str
    taxonomy_label: str
    confidence: float
    bbox: list[float]
    triggered_at: float
    duration_seconds: float | None
    auto_save: bool
    pre_frames: int
    post_frames: int
    details: dict = field(default_factory=dict)
    model_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "track_id": self.track_id,
            "class_name": self.class_name,
            "taxonomy_label": self.taxonomy_label,
            "confidence": round(self.confidence, 4),
            "bbox": self.bbox,
            "triggered_at": round(self.triggered_at, 3),
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "auto_save": self.auto_save,
            "pre_frames": self.pre_frames,
            "post_frames": self.post_frames,
            "details": self.details,
            "model_version": self.model_version,
        }


def _rule_time_window_ok(rule: EventRule, now: float) -> bool:
    return _in_time_window(_now_hhmm(now), rule.time_of_day)


def _cooldown_ok(state: TrackEventState, rule: EventRule, now: float) -> bool:
    last_fired = state.fired_cooldowns.get(rule.rule_id)
    return last_fired is None or (now - last_fired) >= rule.cooldown_seconds


def _fire(
    state: TrackEventState,
    rule: EventRule,
    now: float,
    confidence: float,
    *,
    duration_seconds: float | None = None,
    details: dict | None = None,
) -> PerceptionEvent:
    state.fired_cooldowns[rule.rule_id] = now
    return PerceptionEvent(
        event_id=uuid4().hex,
        event_type=rule.rule_type,
        rule_id=rule.rule_id,
        rule_name=rule.name,
        track_id=state.track_id,
        class_name=state.class_name,
        taxonomy_label=state.taxonomy_label,
        confidence=confidence,
        bbox=list(state.bbox),
        triggered_at=now,
        duration_seconds=duration_seconds,
        auto_save=rule.auto_save,
        pre_frames=rule.pre_frames,
        post_frames=rule.post_frames,
        details=details or {},
        model_version="yolov8-seg-1.0",
    )


class EventEngine:
    """Evaluates rules against per-frame tracked detections."""

    def __init__(self, rules: list[EventRule] | None = None, *, now_provider=None):
        self.rules: list[EventRule] = rules if rules is not None else default_rules()
        self._states: dict[int, TrackEventState] = {}
        self._now_provider = now_provider or time.time
        self._distance_unrated_counts: dict[str, int] = {}

    def _log_surface_missing_distance(self, rule: EventRule) -> None:
        """Track distance-rule evaluations that cannot be scored because the
        detection carried no ``distance_m`` (e.g. no metric-depth upstream)."""
        self._distance_unrated_counts[rule.rule_id] = self._distance_unrated_counts.get(rule.rule_id, 0) + 1

    def update(self, detections: list[dict], now: float | None = None) -> list[PerceptionEvent]:
        now = now if now is not None else self._now_provider()
        present_ids: set[int] = set()
        events: list[PerceptionEvent] = []

        for det in detections:
            track_id = det.get("track_id")
            if track_id is None:
                continue
            try:
                track_id = int(track_id)
            except (TypeError, ValueError):
                continue
            present_ids.add(track_id)

            state = self._states.get(track_id)
            if state is None:
                state = TrackEventState(
                    track_id=track_id,
                    class_name=str(det.get("class_name", "object")),
                    taxonomy_label=str(det.get("taxonomy_label", det.get("class_name", "object"))),
                    first_seen=now,
                    last_seen=now,
                    continuous_since=now,
                    max_confidence=_confidence_of(det),
                    bbox=_bbox_xyxy(det),
                )
                self._states[track_id] = state
            else:
                state.touch(det, now)

            for rule in self.rules:
                if not rule.enabled or not rule.matches_class(det):
                    continue
                if not _rule_time_window_ok(rule, now):
                    continue
                confidence = _confidence_of(det)
                if confidence < rule.min_confidence:
                    continue
                if not _cooldown_ok(state, rule, now):
                    continue

                fired = self._evaluate_rule(rule, state, det, now)
                if fired is not None:
                    events.append(fired)

        for track_id, state in list(self._states.items()):
            if track_id in present_ids:
                continue
            state.mark_missing(now)
            if state.is_stale(now):
                del self._states[track_id]

        return events

    def _evaluate_rule(
        self,
        rule: EventRule,
        state: TrackEventState,
        det: dict,
        now: float,
    ) -> PerceptionEvent | None:
        confidence = _confidence_of(det)

        if rule.rule_type == DWELL:
            if rule.dwell_seconds <= 0:
                return None
            continuous = state.continuous_seconds(now)
            if continuous >= rule.dwell_seconds:
                return _fire(
                    state,
                    rule,
                    now,
                    confidence,
                    duration_seconds=continuous,
                    details={"dwell_seconds": round(continuous, 2), "max_confidence": round(state.max_confidence, 4)},
                )
            return None

        if rule.rule_type == PRESENCE:
            return _fire(
                state,
                rule,
                now,
                confidence,
                duration_seconds=None,
                details={"max_confidence": round(state.max_confidence, 4)},
            )

        if rule.rule_type == CONFIDENCE_DROP:
            if state.max_confidence >= rule.confidence_drop_from and confidence < rule.confidence_drop_below:
                return _fire(
                    state,
                    rule,
                    now,
                    confidence,
                    details={"max_confidence": round(state.max_confidence, 4), "current_confidence": round(confidence, 4)},
                )
            return None

        if rule.rule_type == DISTANCE:
            distance = det.get("distance_m")
            if distance is None or rule.distance_m_max is None:
                if distance is None:
                    self._log_surface_missing_distance(rule)
                return None
            distance_m = float(distance)
            if distance_m <= rule.distance_m_max:
                return _fire(
                    state,
                    rule,
                    now,
                    confidence,
                    details={"distance_m": round(distance_m, 2), "max_distance_m": rule.distance_m_max},
                )
            return None

        return None

    def state_summary(self) -> dict[str, Any]:
        return {
            "tracks": len(self._states),
            "rules": [rule.to_dict() for rule in self.rules],
            "active_dwell": {
                str(track_id): round(state.continuous_seconds(time.time()), 2)
                for track_id, state in self._states.items()
            },
            "distance_unrated_by_rule": dict(self._distance_unrated_counts),
        }

    def reset(self) -> None:
        self._states.clear()


class FrameRingBuffer:
    """Bounded ring buffer of processed frames for pre/post event clips."""

    def __init__(self, maxlen: int = 16):
        self._entries: deque[dict] = deque(maxlen=maxlen)

    def push(
        self,
        *,
        frame_bytes: bytes,
        annotations: list[dict],
        timestamp: float,
        frame_index: int,
        depth_available: bool = False,
    ) -> None:
        self._entries.append(
            {
                "frame_bytes": frame_bytes,
                "annotations": annotations,
                "timestamp": timestamp,
                "frame_index": frame_index,
                "depth_available": depth_available,
            }
        )

    def recent(self, count: int) -> list[dict]:
        count = max(0, min(count, len(self._entries)))
        return list(self._entries)[-count:] if count else []

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
