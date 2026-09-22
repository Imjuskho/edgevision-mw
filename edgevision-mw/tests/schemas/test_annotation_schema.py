from pydantic import ValidationError

import pytest

from app.schemas.annotation import AnnotationLabel, LabelSubmission


class TestLabelSubmission:
    def test_accepts_class_key_and_typed_fields(self):
        sub = LabelSubmission(
            labels=[{"class": "vehicle", "bbox": [10, 10, 50, 50], "confidence": 0.9}],
            quality_score=0.95,
        )
        assert sub.labels[0].class_name == "vehicle"
        assert sub.labels[0].bbox == [10.0, 10.0, 50.0, 50.0]
        assert sub.labels[0].confidence == 0.9

    def test_rejects_empty_labels(self):
        with pytest.raises(ValidationError):
            LabelSubmission(labels=[])

    def test_rejects_out_of_range_confidence(self):
        with pytest.raises(ValidationError):
            LabelSubmission(labels=[{"class": "vehicle", "confidence": 1.5}])

    def test_serializes_to_json_safe_dict(self):
        sub = LabelSubmission(
            labels=[{"class": "vehicle", "bbox": [10, 10, 50, 50]}],
            quality_score=0.95,
        )
        dumped = {"objects": [label.model_dump(exclude_none=True) for label in sub.labels]}
        assert dumped == {
            "objects": [{"class": "vehicle", "class_name": "vehicle", "bbox": [10.0, 10.0, 50.0, 50.0]}]
        }

    def test_annotation_label_allows_extra_fields(self):
        label = AnnotationLabel.model_validate({"class": "pedestrian", "track_id": 7, "extra": "x"})
        assert label.class_name == "pedestrian"
        assert label.extra == "x"
