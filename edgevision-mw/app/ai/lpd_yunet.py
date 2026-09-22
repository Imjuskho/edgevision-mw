"""LPD-YuNet license plate detector (OpenCV Zoo, Apache 2.0).

Vendored from opencv/opencv_zoo models/license_plate_detection_yunet.
"""

from __future__ import annotations

from itertools import product

import cv2 as cv
import numpy as np


class LPD_YuNet:
    def __init__(
        self,
        model_path: str,
        input_size: list[int] | None = None,
        conf_threshold: float = 0.55,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        keep_top_k: int = 750,
        backend_id: int = 0,
        target_id: int = 0,
    ):
        self.model_path = model_path
        self.input_size = np.array(input_size or [320, 240])
        self.confidence_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self.keep_top_k = keep_top_k
        self.backend_id = backend_id
        self.target_id = target_id

        self.output_names = ["loc", "conf", "iou"]
        self.min_sizes = [[10, 16, 24], [32, 48], [64, 96], [128, 192, 256]]
        self.steps = [8, 16, 32, 64]
        self.variance = [0.1, 0.2]

        self.model = cv.dnn.readNet(self.model_path)
        self.model.setPreferableBackend(self.backend_id)
        self.model.setPreferableTarget(self.target_id)
        self._prior_gen()

    def set_input_size(self, input_size: list[int]) -> None:
        self.input_size = np.array(input_size)
        self._prior_gen()

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        return cv.dnn.blobFromImage(image)

    def infer(self, image: np.ndarray) -> np.ndarray:
        assert image.shape[0] == self.input_size[1]
        assert image.shape[1] == self.input_size[0]

        input_blob = self._preprocess(image)
        self.model.setInput(input_blob)
        output_blob = self.model.forward(self.output_names)
        return self._postprocess(output_blob)

    def _postprocess(self, blob) -> np.ndarray:
        dets = self._decode(blob)
        keep_idx = cv.dnn.NMSBoxes(
            bboxes=dets[:, 0:4].tolist(),
            scores=dets[:, -1].tolist(),
            score_threshold=self.confidence_threshold,
            nms_threshold=self.nms_threshold,
            top_k=self.top_k,
        )
        if len(keep_idx) == 0:
            return np.empty(shape=(0, 9))

        if isinstance(keep_idx, np.ndarray):
            keep_idx = keep_idx.flatten()
        else:
            keep_idx = [idx[0] if isinstance(idx, (list, tuple)) else idx for idx in keep_idx]

        return dets[keep_idx][: self.keep_top_k]

    def _prior_gen(self) -> None:
        w, h = self.input_size
        feature_map_2th = [int(int((h + 1) / 2) / 2), int(int((w + 1) / 2) / 2)]
        feature_map_3th = [int(feature_map_2th[0] / 2), int(feature_map_2th[1] / 2)]
        feature_map_4th = [int(feature_map_3th[0] / 2), int(feature_map_3th[1] / 2)]
        feature_map_5th = [int(feature_map_4th[0] / 2), int(feature_map_4th[1] / 2)]
        feature_map_6th = [int(feature_map_5th[0] / 2), int(feature_map_5th[1] / 2)]

        feature_maps = [feature_map_3th, feature_map_4th, feature_map_5th, feature_map_6th]
        priors: list[list[float]] = []
        for k, f_map in enumerate(feature_maps):
            for i, j in product(range(f_map[0]), range(f_map[1])):
                for min_size in self.min_sizes[k]:
                    s_kx = min_size / w
                    s_ky = min_size / h
                    cx = (j + 0.5) * self.steps[k] / w
                    cy = (i + 0.5) * self.steps[k] / h
                    priors.append([cx, cy, s_kx, s_ky])
        self.priors = np.array(priors, dtype=np.float32)

    def _decode(self, blob) -> np.ndarray:
        loc, conf, iou = blob
        cls_scores = conf[:, 1]
        iou_scores = iou[:, 0]
        iou_scores = np.clip(iou_scores, 0.0, 1.0)
        scores = np.sqrt(cls_scores * iou_scores)[:, np.newaxis]
        scale = self.input_size

        bboxes = np.hstack(
            (
                (self.priors[:, 0:2] + loc[:, 4:6] * self.variance[0] * self.priors[:, 2:4]) * scale,
                (self.priors[:, 0:2] + loc[:, 6:8] * self.variance[0] * self.priors[:, 2:4]) * scale,
                (self.priors[:, 0:2] + loc[:, 10:12] * self.variance[0] * self.priors[:, 2:4]) * scale,
                (self.priors[:, 0:2] + loc[:, 12:14] * self.variance[0] * self.priors[:, 2:4]) * scale,
            )
        )
        return np.hstack((bboxes, scores))
