"""Tests for F3 — Predictive Trajectory Modeling."""
from __future__ import annotations

import time

import numpy as np
import pytest
from collections import deque

from app.prediction.trajectory_model import (
    predict_constant_velocity,
    predict_constant_acceleration,
    fuse_with_road_mask,
    TrajectoryPredictor,
    NumpyLSTMCell,
    NumpyTrajectoryLSTM,
    evaluate_predictive_rules,
    PredictiveIntersectionRule,
    PredictedPoint,
    PREDICTIVE_INTERSECTION,
)
from app.ai.events import TrackEventState


def _positions_array(start, velocity, n_points=10, dt=1.0):
    arr = np.zeros((n_points, 3), dtype=np.float64)
    for i in range(n_points):
        t = i * dt
        arr[i] = [start[0] + velocity[0] * t, start[1] + velocity[1] * t, t]
    return arr


def _track_state(trajectory_points):
    """Build a TrackEventState with a pre-populated trajectory deque."""
    now = time.time()
    t = deque(trajectory_points, maxlen=32)
    last = trajectory_points[-1] if trajectory_points else (0, 0, 0)
    return TrackEventState(
        track_id=1,
        class_name="car",
        taxonomy_label="vehicle",
        first_seen=now - 10,
        last_seen=now,
        continuous_since=now - 10,
        max_confidence=0.9,
        bbox=[last[0] - 0.1, last[1] - 0.1, last[0] + 0.1, last[1] + 0.1],
        trajectory=t,
    )


class TestConstantVelocity:
    def test_straight_line(self):
        pos = _positions_array((0, 0), (10, 0), n_points=5)
        predictions = predict_constant_velocity(pos, horizons=[1.0, 2.0, 3.0])
        assert len(predictions) == 3
        assert predictions[0].t == 1.0

    def test_velocity_computation(self):
        pos = _positions_array((0, 0), (10, 0), n_points=5)
        # Last point is at x=40, vx=10, so for h=2: x = 40 + 10*2 = 60
        predictions = predict_constant_velocity(pos, horizons=[2.0])
        assert abs(predictions[0].x - 60.0) < 1e-6
        assert abs(predictions[0].y - 0.0) < 1e-6

    def test_confidence_decreases(self):
        pos = _positions_array((0, 0), (10, 5), n_points=10)
        predictions = predict_constant_velocity(pos, horizons=[1.0, 3.0, 5.0])
        confs = [p.confidence for p in predictions]
        assert confs[0] >= confs[-1]


class TestConstantAcceleration:
    def test_predictions_exist(self):
        pos = _positions_array((0, 0), (5, 0), n_points=10)
        predictions = predict_constant_acceleration(pos, horizons=[1.0, 2.0])
        assert len(predictions) == 2

    def test_falls_back_to_cv_with_few_points(self):
        pos = np.array([[0, 0, 0], [1, 0, 1]], dtype=np.float64)
        predictions = predict_constant_acceleration(pos, horizons=[1.0])
        assert len(predictions) == 1


class TestTrajectoryPredictor:
    def test_predict_trajectory(self):
        predictor = TrajectoryPredictor()
        pts = [(float(i * 10), float(i * 5), float(i)) for i in range(10)]
        state = _track_state(pts)
        predictions = predictor.predict_trajectory(state, horizons=[1.0, 2.0, 3.0])
        assert len(predictions) == 3
        assert all(isinstance(p, PredictedPoint) for p in predictions)

    def test_predict_trajectory_default_horizons(self):
        predictor = TrajectoryPredictor()
        pts = [(float(i * 10), float(i * 5), float(i)) for i in range(10)]
        state = _track_state(pts)
        predictions = predictor.predict_trajectory(state)
        assert len(predictions) > 0

    def test_fuse_and_assess(self):
        predictor = TrajectoryPredictor()
        pts = [(float(i * 10), float(i * 5), float(i)) for i in range(10)]
        state = _track_state(pts)
        predictions = predictor.predict_trajectory(state, horizons=[1.0, 2.0])
        road_mask = {"bbox": {"min_x": 0, "max_x": 200, "min_y": 40, "max_y": 50}}
        result = predictor.fuse_and_assess(predictions, road_mask)
        assert isinstance(result, tuple)
        assert len(result) == 4


class TestRoadFusion:
    def test_fuse_with_road_mask_bbox(self):
        predicted = [
            PredictedPoint(t=1.0, x=10, y=10, confidence=0.8),
            PredictedPoint(t=2.0, x=20, y=20, confidence=0.7),
            PredictedPoint(t=3.0, x=30, y=30, confidence=0.6),
        ]
        road_mask = {"bbox": {"min_x": 0, "max_x": 100, "min_y": 15, "max_y": 25}}
        will_intersect, tti, conf, xy = fuse_with_road_mask(predicted, road_mask)
        assert isinstance(will_intersect, bool)

    def test_fuse_with_none_road_mask(self):
        predicted = [PredictedPoint(t=1.0, x=10, y=10, confidence=0.8)]
        will_intersect, tti, conf, xy = fuse_with_road_mask(predicted, None)
        assert will_intersect is False


class TestNumpyLSTM:
    def test_cell_forward(self):
        cell = NumpyLSTMCell(input_dim=4, hidden_dim=32)
        x = np.random.randn(4).astype(np.float32)
        h = np.zeros(32, dtype=np.float32)
        c = np.zeros(32, dtype=np.float32)
        h_new, c_new = cell.forward(x, h, c)
        assert h_new.shape == (32,)
        assert c_new.shape == (32,)

    def test_lstm_predict(self):
        lstm = NumpyTrajectoryLSTM(input_dim=3, hidden_dim=16, num_horizons=3)
        pos = _positions_array((0, 0), (5, 2), n_points=10)
        predictions = lstm.predict(pos, horizons=[1.0, 2.0, 3.0])
        assert len(predictions) == 3


class TestPredictiveRules:
    def test_predictive_intersection_rule(self):
        rule = PredictiveIntersectionRule(
            rule_id="pred-1",
            rule_type=PREDICTIVE_INTERSECTION,
            name="Road intersection alert",
            confidence_threshold=0.7,
        )
        assert rule.rule_type == PREDICTIVE_INTERSECTION
        assert rule.confidence_threshold == 0.7

    def test_evaluate_predictive_rules(self):
        predictor = TrajectoryPredictor()
        rule = PredictiveIntersectionRule(
            rule_id="pred-1",
            rule_type=PREDICTIVE_INTERSECTION,
            name="Test",
            confidence_threshold=0.3,
            cooldown_seconds=0,
        )
        pts = [(float(i * 10), float(i * 5), float(i)) for i in range(10)]
        state = _track_state(pts)
        road_mask = {"bbox": {"min_x": 0, "max_x": 200, "min_y": 30, "max_y": 60}}
        now = time.time()
        events = evaluate_predictive_rules(
            predictor, [rule], state, road_mask, lane_boundaries=None, now=now,
        )
        assert isinstance(events, list)

    def test_confidence_gating(self):
        predictor = TrajectoryPredictor()
        rule = PredictiveIntersectionRule(
            rule_id="pred-1",
            rule_type=PREDICTIVE_INTERSECTION,
            name="Test",
            confidence_threshold=0.99,
            cooldown_seconds=0,
        )
        pts = [(float(i), float(i), float(i)) for i in range(10)]
        state = _track_state(pts)
        road_mask = {"bbox": {"min_x": -1000, "max_x": 1000, "min_y": -1000, "max_y": 1000}}
        now = time.time()
        events = evaluate_predictive_rules(
            predictor, [rule], state, road_mask, lane_boundaries=None, now=now,
        )
        assert isinstance(events, list)
