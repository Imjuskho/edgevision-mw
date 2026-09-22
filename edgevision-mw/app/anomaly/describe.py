"""VLM-based natural-language anomaly description generator.

When an anomaly is flagged by :mod:`app.anomaly.scorer`, this module
produces a plain-English description suitable for human operators and the
labeling queue.

Architecture
------------
1. **Template layer** — category-specific templates with dynamic fill-ins
   derived from embedding feature differences.
2. **Feature importance layer** — highlights which embedding dimensions
   contributed most to the anomaly, mapped to semantic feature names.
3. **Severity assessment** — classifies anomaly as low / medium / high /
   critical based on score, temporal persistence, and reconstruction error.
4. **Scene context** — integrates camera metadata and detection statistics
   for richer descriptions.

The VLM layer is **feature-flagged** via ``ANOMALY_VLM_DESCRIPTION_ENABLED``
and runs independently from scoring.  When the flag is ``False``,
``describe`` falls back to a minimal template-only string.

No external VLM API call is made in this module.  The template + feature
analysis engine produces structured natural language directly.  When a real
VLM endpoint is added in the future, this module provides the prompt
payload.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_VLM_ENABLED = settings.ANOMALY_VLM_DESCRIPTION_ENABLED


# ---------------------------------------------------------------------------
# Semantic feature-name mapping
# ---------------------------------------------------------------------------

_FEATURE_LABELS: dict[str, str] = {
    "color_hist_0": "blue channel (dark)",
    "color_hist_1": "blue channel (mid)",
    "color_hist_2": "blue channel (bright)",
    "color_hist_3": "green channel (dark)",
    "color_hist_4": "green channel (mid)",
    "color_hist_5": "green channel (bright)",
    "color_hist_6": "red channel (dark)",
    "color_hist_7": "red channel (mid)",
    "color_hist_8": "red channel (bright)",
    "mean_brightness": "overall brightness",
    "mean_saturation": "colour saturation",
    "brightness_std": "lighting uniformity",
    "object_counts": "object count",
    "road_ratio": "road surface coverage",
    "avg_confidence": "detection confidence",
    "depth_histogram_near": "near-field objects",
    "depth_histogram_mid": "mid-range objects",
    "depth_histogram_far": "far-field objects",
    "scene_entropy": "scene complexity",
}

# Embedding dimension labels (for the learned representation)
_EMBED_LABELS = [f"scene_feature_{i}" for i in range(64)]

# Category-specific templates
_ANOMALY_TEMPLATES: dict[str, list[str]] = {
    "object_anomaly": [
        "An unusual number of objects detected ({count} vs typical {typical}). "
        "This may indicate {possible}.",
        "Object count deviation: {count} objects observed where {typical} is normal. "
        "{context}",
        "Abnormal object density in frame: {count} detections significantly "
        "exceed or fall below the learned baseline of {typical}.",
    ],
    "scene_anomaly": [
        "Significant scene change detected: {feature_name} shifted from {expected} "
        "to {observed} ({delta_pct:.0f}% change). {context}",
        "The visual scene composition has changed abnormally. {feature_name} "
        "moved from the expected range ({expected}) to {observed}.",
        "Scene-level anomaly: {feature_name} outside normal bounds "
        "(expected ~{expected}, observed {observed}).",
    ],
    "appearance_anomaly": [
        "Unusual appearance change: {feature_name} is {observed} compared to "
        "the normal range of {expected}. Possible causes: {possible}.",
        "Visual appearance deviation detected. {feature_name} changed from "
        "{expected} to {observed} ({delta_pct:.0f}% shift).",
        "Scene appearance anomaly — {feature_name} significantly outside "
        "normal parameters ({observed} vs expected {expected}).",
    ],
    "weather_anomaly": [
        "Weather-related scene change: {feature_name} indicates {possible}. "
        "Observed {observed} vs typical {expected}.",
        "Environmental condition change detected. {feature_name} shifted to "
        "{observed} from normal {expected}. Likely cause: {possible}.",
    ],
    "traffic_anomaly": [
        "Traffic pattern anomaly: object behaviour or positioning deviates "
        "from learned normal. {context}",
        "Unusual traffic scene: {feature_name} changed from {expected} to "
        "{observed}. This may indicate {possible}.",
    ],
    "left_object": [
        "Potential abandoned or stationary object detected. An object has "
        "remained in the scene significantly longer than typical traffic flow.",
        "Stationary object alert: an object matching class '{class_name}' "
        "has been present for an unusually long duration.",
    ],
    "novel_class": [
        "Novel object class detected: '{class_name}' has not been observed "
        "in this camera's normal scenes before.",
        "New object category '{class_name}' appeared — not present in the "
        "camera's learned normal distribution.",
    ],
    "general": [
        "Anomalous scene pattern detected. The overall scene embedding "
        "deviates from the learned normal distribution for this camera.",
        "Open-set anomaly: scene characteristics fall outside the normal "
        "operating envelope. Score: {score:.2f} (threshold: {threshold:.2f}).",
        "Unusual visual pattern detected in the camera feed. "
        "Multiple features contribute to the anomaly.",
    ],
}

# Possible causes per anomaly category
_CAUSES: dict[str, list[str]] = {
    "object_anomaly": [
        "construction activity",
        "accident or incident",
        "unusual vehicle accumulation",
        "pedestrian crowd formation",
        "delivery or loading event",
        "animal intrusion",
    ],
    "scene_anomaly": [
        "camera displacement or vandalism",
        "obstruction (vegetation, debris)",
        "seasonal lighting change",
        "new construction or demolition",
        "road surface change",
    ],
    "appearance_anomaly": [
        "weather deterioration (fog, rain, dust)",
        "time-of-day shift beyond normal range",
        "camera lens obstruction or smear",
        "sensor degradation",
        "shadow pattern change",
    ],
    "weather_anomaly": [
        "heavy rain or storm conditions",
        "fog or mist formation",
        "extreme glare or overexposure",
        "dust storm or haze",
        "night-time conditions on a day-time camera",
    ],
    "traffic_anomaly": [
        "wrong-way vehicle",
        "unusual lane usage",
        "vehicle stoppage in traffic lane",
        "non-motorised traffic in motorway",
        "road obstruction forcing detour",
    ],
    "left_object": [
        "vehicle breakdown",
        "accident debris",
        "deliberately abandoned object",
        "delivery drop-off",
        "road hazard",
    ],
    "novel_class": [
        "new vehicle type not in training set",
        "animal species not previously seen",
        "temporary structure or signage",
        "person in unusual attire or with equipment",
    ],
    "general": [
        "unusual scene composition",
        "sensor anomaly or environmental change",
        "unexpected activity pattern",
        "possible infrastructure change",
    ],
}


# ---------------------------------------------------------------------------
# AnomalyDescriber
# ---------------------------------------------------------------------------

class AnomalyDescriber:
    """Generate natural-language descriptions for flagged anomalies.

    Parameters
    ----------
    enabled : bool
        Master feature flag.  When ``False``, ``describe`` returns a
        generic fallback string and skips all feature analysis.
    """

    def __init__(self, enabled: bool = _VLM_ENABLED) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def describe(
        self,
        camera_id: str,
        anomaly_result: dict[str, Any],
        feature_names: list[str] | None = None,
        detections: list[dict] | None = None,
        scene_features: dict[str, Any] | None = None,
    ) -> str:
        """Produce a plain-English description of the anomaly.

        Parameters
        ----------
        camera_id
            Camera identifier.
        anomaly_result
            Output of :meth:`AnomalyScorer.score` (must contain at least
            ``anomaly_score``, ``contributing_dims``, ``dominant_component``).
        feature_names
            Optional list of human-readable names for each embedding
            dimension (length must match ``embedding_dim``).
        detections
            YOLO detections for the flagged frame (optional, enriches
            description with object-level context).
        scene_features
            Dictionary of scene features from the existing
            ``compute_scene_embedding`` pipeline (optional).

        Returns
        -------
        str
            Natural-language description (max ~500 characters for DB storage).
        """
        if not self._enabled:
            return self._fallback_description(anomaly_result)

        score = anomaly_result.get("anomaly_score", 0.0)
        threshold = anomaly_result.get("threshold", 2.0)
        contributing = anomaly_result.get("contributing_dims", [])
        dominant_comp = anomaly_result.get("dominant_component", 0)
        temporal_flags = anomaly_result.get("temporal_flag_count", 0)

        # 1. Classify anomaly category
        category = self._classify_category(
            scene_features, detections, contributing, score, threshold
        )

        # 2. Determine severity
        severity = self._assess_severity(score, threshold, temporal_flags)

        # 3. Pick likely causes
        possible_causes = self._pick_causes(category, scene_features)

        # 4. Identify the most deviant feature
        top_feature = self._top_feature_analysis(
            contributing, feature_names, scene_features
        )

        # 5. Build context from detections
        detection_context = self._detection_context(detections)

        # 6. Fill template
        description = self._fill_template(
            category=category,
            severity=severity,
            score=score,
            threshold=threshold,
            top_feature=top_feature,
            possible_causes=possible_causes,
            detection_context=detection_context,
            scene_features=scene_features,
        )

        return description[:500]

    def describe_with_prompt(
        self,
        camera_id: str,
        anomaly_result: dict[str, Any],
        scene_features: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Return both the description and a VLM prompt for future use.

        When a real VLM API is integrated, this method provides the
        structured prompt that can be sent to the model along with the
        image frame.
        """
        description = self.describe(
            camera_id, anomaly_result, scene_features=scene_features
        )

        score = anomaly_result.get("anomaly_score", 0.0)
        threshold = anomaly_result.get("threshold", 2.0)
        contributing = anomaly_result.get("contributing_dims", [])

        prompt = (
            f"You are analysing a traffic/security camera frame from camera "
            f"'{camera_id}'. The frame has been flagged as anomalous with a "
            f"score of {score:.2f} (threshold: {threshold:.2f}).\n\n"
            f"The top contributing feature dimensions are: "
        )
        for c in contributing[:5]:
            prompt += f"dim_{c['dim']} (value={c['value']:.4f}, expected={c['expected']:.4f}), "
        prompt += (
            "\n\nPlease describe what is unusual about this scene in "
            "1-2 sentences, focusing on what a human operator should "
            "investigate."
        )

        return {
            "description": description,
            "vlm_prompt": prompt,
            "category": self._classify_category(
                scene_features, None, contributing, score, threshold
            ),
            "severity": self._assess_severity(
                score, threshold, anomaly_result.get("temporal_flag_count", 0)
            ),
        }

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_category(
        scene_features: dict[str, Any] | None,
        detections: list[dict] | None,
        contributing_dims: list[dict[str, Any]],
        score: float,
        threshold: float,
    ) -> str:
        """Determine the anomaly category from available evidence."""
        if scene_features is None and detections is None:
            return "general"

        feature_names = {c.get("dim", -1) for c in contributing_dims}

        # Novel class detection
        if detections:
            detected_classes = {d.get("class_name", d.get("label", "")) for d in detections}
            if "unknown" in detected_classes or "" in detected_classes:
                return "novel_class"

        if scene_features is None:
            return "general"

        # Weather anomalies
        if "mean_brightness" in scene_features or "mean_saturation" in scene_features:
            return "weather_anomaly"

        # Object count anomalies
        if scene_features.get("object_counts", 0) == 0 and detections:
            return "object_anomaly"
        if "object_counts" in scene_features:
            return "object_anomaly"

        # Traffic
        if "class_avg_bbox_area" in scene_features or "class_avg_confidence" in scene_features:
            return "traffic_anomaly"

        # Scene / appearance
        if "road_ratio" in scene_features:
            return "scene_anomaly"

        return "appearance_anomaly"

    @staticmethod
    def _assess_severity(score: float, threshold: float, temporal_flags: int) -> str:
        ratio = score / max(threshold, 1e-6)
        if ratio > 3.0 or temporal_flags >= 8:
            return "critical"
        if ratio > 2.0 or temporal_flags >= 5:
            return "high"
        if ratio > 1.5 or temporal_flags >= 3:
            return "medium"
        return "low"

    @staticmethod
    def _pick_causes(
        category: str,
        scene_features: dict[str, Any] | None,
    ) -> str:
        import random

        causes = _CAUSES.get(category, _CAUSES["general"])
        # Deterministic pick for reproducibility (seed from score if available)
        rng = random.Random(42)
        if scene_features:
            rng = random.Random(hash(str(sorted(scene_features.items()))))
        selected = rng.sample(causes, min(2, len(causes)))
        return " or ".join(selected)

    # ------------------------------------------------------------------
    # Feature analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _top_feature_analysis(
        contributing_dims: list[dict[str, Any]],
        feature_names: list[str] | None,
        scene_features: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Identify the most semantically meaningful deviant feature."""
        if not contributing_dims:
            return {"name": "overall scene embedding", "label": "unknown", "contribution": 0.0}

        top = contributing_dims[0]
        dim_idx = top.get("dim", 0)

        # Try to map to a semantic label
        label = "unknown"
        if feature_names and dim_idx < len(feature_names):
            label = feature_names[dim_idx]
        elif dim_idx < len(_EMBED_LABELS):
            label = _EMBED_LABELS[dim_idx]

        # Check scene features for more specific naming
        if scene_features:
            for feat_key, feat_label in _FEATURE_LABELS.items():
                if feat_key in scene_features:
                    label = feat_label
                    break

        return {
            "name": f"embedding_dim_{dim_idx}",
            "label": label,
            "value": top.get("value", 0.0),
            "expected": top.get("expected", 0.0),
            "contribution": top.get("contribution", 0.0),
        }

    @staticmethod
    def _detection_context(detections: list[dict] | None) -> str:
        """Build a brief summary of detections for the description."""
        if not detections:
            return "No object detections available for additional context."

        classes: dict[str, int] = {}
        for det in detections:
            cls = det.get("class_name", det.get("label", "unknown"))
            classes[cls] = classes.get(cls, 0) + 1

        parts = [f"{count} {cls}" for cls, count in sorted(classes.items(), key=lambda x: -x[1])]
        summary = ", ".join(parts[:5])
        return f"Detected: {summary}."

    # ------------------------------------------------------------------
    # Template filling
    # ------------------------------------------------------------------

    def _fill_template(
        self,
        category: str,
        severity: str,
        score: float,
        threshold: float,
        top_feature: dict[str, Any],
        possible_causes: str,
        detection_context: str,
        scene_features: dict[str, Any] | None,
    ) -> str:
        templates = _ANOMALY_TEMPLATES.get(category, _ANOMALY_TEMPLATES["general"])
        # Deterministic template selection
        template_idx = int(score * 10) % len(templates)
        template = templates[template_idx]

        feature_name = top_feature.get("label", "unknown feature")
        expected = top_feature.get("expected", 0.0)
        observed = top_feature.get("value", 0.0)
        delta_pct = abs(observed - expected) / max(abs(expected), 1e-6) * 100

        # Compute count/typical from scene features if available
        count = 0
        typical = 0
        if scene_features:
            count = int(scene_features.get("object_counts", 0))
        if scene_features:
            typical = int(scene_features.get("object_counts", 0))

        # Context line
        context_parts = [detection_context]
        if severity in ("critical", "high"):
            context_parts.append(f"Severity: {severity.upper()}.")
        context_parts.append(f"Score {score:.2f} vs threshold {threshold:.2f}.")
        context = " ".join(context_parts)

        try:
            description = template.format(
                feature_name=feature_name,
                expected=f"{expected:.4f}",
                observed=f"{observed:.4f}",
                delta_pct=delta_pct,
                possible=possible_causes,
                context=context,
                count=count,
                typical=typical,
                class_name=scene_features.get("novel_class", "unknown") if scene_features else "unknown",
                score=score,
                threshold=threshold,
            )
        except (KeyError, IndexError):
            description = (
                f"Anomalous scene pattern detected ({category}). "
                f"Score: {score:.2f} (threshold: {threshold:.2f}). "
                f"Severity: {severity}. {context}"
            )

        return description

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_description(anomaly_result: dict[str, Any]) -> str:
        score = anomaly_result.get("anomaly_score", 0.0)
        threshold = anomaly_result.get("threshold", 2.0)
        return (
            f"Anomalous scene detected (score {score:.2f}, "
            f"threshold {threshold:.2f}). Detailed description "
            f"generation is disabled (ANOMALY_VLM_DESCRIPTION_ENABLED=false)."
        )


# ---------------------------------------------------------------------------
# Prompt builder for future VLM integration
# ---------------------------------------------------------------------------

def build_vlm_prompt(
    camera_id: str,
    anomaly_result: dict[str, Any],
    image_description: str = "",
) -> str:
    """Build a structured prompt payload for a future VLM API call.

    This function is a convenience for callers who want to integrate a real
    vision-language model (e.g. GPT-4V, LLaVA, etc.) in place of the
    template engine.

    Parameters
    ----------
    camera_id
        Camera identifier.
    anomaly_result
        Output of :meth:`AnomalyScorer.score`.
    image_description
        Optional CLIP or other image caption to include.

    Returns
    -------
    str
        A prompt string suitable for sending to a VLM endpoint.
    """
    score = anomaly_result.get("anomaly_score", 0.0)
    threshold = anomaly_result.get("threshold", 2.0)
    contributing = anomaly_result.get("contributing_dims", [])
    dominant = anomaly_result.get("dominant_component", 0)

    prompt_lines = [
        f"Camera: {camera_id}",
        f"Anomaly score: {score:.4f} (threshold: {threshold:.4f})",
        f"Dominant GMM component: {dominant}",
        "Top contributing feature dimensions:",
    ]
    for c in contributing[:5]:
        prompt_lines.append(
            f"  - dim {c['dim']}: value={c['value']:.4f}, "
            f"expected={c['expected']:.4f}, "
            f"contribution={c['contribution']:.4f}"
        )

    if image_description:
        prompt_lines.append(f"Image caption: {image_description}")

    prompt_lines.append("")
    prompt_lines.append(
        "Based on the above analysis, describe in 1-2 sentences what is "
        "unusual about this scene and what a human operator should investigate. "
        "Be specific about the visual anomaly and its likely cause."
    )

    return "\n".join(prompt_lines)
