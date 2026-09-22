"""F3 Predictive Trajectory Modeling package.

Physics-based and learned trajectory prediction fused with road/curb
segmentation for proactive road-intersection alerting.
"""

from app.prediction.trajectory_model import (
    ConfidenceGatedAlert,
    PredictedPoint,
    PredictiveIntersectionRule,
    TrajectoryPredictor,
    fuse_with_road_mask,
)

__all__ = [
    "ConfidenceGatedAlert",
    "PredictedPoint",
    "PredictiveIntersectionRule",
    "TrajectoryPredictor",
    "fuse_with_road_mask",
]
