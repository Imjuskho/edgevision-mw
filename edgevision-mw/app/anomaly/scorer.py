"""GMM-based outlier scorer for per-camera scene embeddings.

Fits a diagonal-covariance Gaussian Mixture Model to the learned embedding
space of each camera.  Frames whose embeddings fall outside the learned
normal distribution are flagged as anomalous.

Design
------
- Independent of object class labels (open-set detection).
- Runs as a parallel branch alongside YOLO-seg detection.
- Minimum data-volume guard: refuses to score until at least
  ``ANOMALY_MIN_TRAINING_FRAMES`` embeddings have been observed.
- Temporal smoothing: a frame is only flagged after ``ANOMALY_TEMPORAL_MIN_FLAGS``
  of the last ``ANOMALY_TEMPORAL_SMOOTH_WINDOW`` frames were anomalous.

GMM implementation
------------------
Full EM algorithm with diagonal covariance matrices (more stable than full
covariance with limited data).  K-means++ initialisation.  Log-likelihood
computed with the log-sum-exp trick for numerical stability.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_MIN_TRAINING_FRAMES = settings.ANOMALY_MIN_TRAINING_FRAMES
_GMM_COMPONENTS = settings.ANOMALY_GMM_COMPONENTS
_GMM_MAX_ITER = settings.ANOMALY_GMM_MAX_ITER
_GMM_TOLERANCE = settings.ANOMALY_GMM_TOLERANCE
_ANOMALY_THRESHOLD = settings.ANOMALY_DETECTION_THRESHOLD
_TEMPORAL_WINDOW = settings.ANOMALY_TEMPORAL_SMOOTH_WINDOW
_TEMPORAL_MIN_FLAGS = settings.ANOMALY_TEMPORAL_MIN_FLAGS


# ---------------------------------------------------------------------------
# GMM (diagonal covariance)
# ---------------------------------------------------------------------------

class _DiagonalGMM:
    """Gaussian Mixture Model with diagonal covariance matrices."""

    __slots__ = ("n_components", "dim", "weights", "means", "variances", "trained", "log_likelihoods")

    def __init__(self, n_components: int, dim: int) -> None:
        self.n_components = n_components
        self.dim = dim
        self.weights = np.ones(n_components) / n_components
        self.means = np.zeros((n_components, dim), dtype=np.float64)
        self.variances = np.ones((n_components, dim), dtype=np.float64)
        self.trained = False
        self.log_likelihoods: list[float] = []

    def fit(self, data: np.ndarray, max_iter: int = _GMM_MAX_ITER, tol: float = _GMM_TOLERANCE) -> None:
        """Fit via EM.  ``data`` shape: ``(N, dim)``."""
        n = data.shape[0]
        k = self.n_components

        # K-means++ initialisation
        self._kmeans_init(data)

        prev_ll = -np.inf

        for iteration in range(max_iter):
            # E-step: compute responsibilities
            resp = self._e_step(data)

            # M-step
            self._m_step(data, resp)

            # Log-likelihood
            ll = self._log_likelihood(data)
            self.log_likelihoods.append(ll)

            if abs(ll - prev_ll) < tol:
                logger.debug("GMM converged at iteration %d (ll=%.4f)", iteration, ll)
                break
            prev_ll = ll

        self.trained = True

    def score(self, x: np.ndarray) -> float:
        """Return negative log-likelihood of a single observation."""
        if x.ndim == 1:
            x = x[np.newaxis, :]
        return float(-self._log_likelihood(x))

    def score_batch(self, data: np.ndarray) -> np.ndarray:
        """Return negative log-likelihoods for a batch."""
        return -self._log_likelihood_batch(data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _kmeans_init(self, data: np.ndarray) -> None:
        """K-means++ initialisation for GMM means."""
        n, dim = data.shape
        rng = np.random.default_rng(42)

        # First centre: random
        idx = rng.integers(n)
        self.means[0] = data[idx]

        for c in range(1, self.n_components):
            dists = np.min(
                np.sum((data[:, np.newaxis] - self.means[np.newaxis, :c]) ** 2, axis=2),
                axis=1,
            )
            probs = dists / dists.sum()
            idx = rng.choice(n, p=probs)
            self.means[c] = data[idx]

        # Assign points and set variances
        for _ in range(10):
            dists = np.sum(
                (data[:, np.newaxis] - self.means[np.newaxis, :]) ** 2, axis=2
            )
            labels = np.argmin(dists, axis=1)
            for c in range(self.n_components):
                mask = labels == c
                if mask.any():
                    self.means[c] = data[mask].mean(axis=0)
                    self.variances[c] = np.maximum(data[mask].var(axis=0), 1e-6)
                    self.weights[c] = mask.sum() / n
                else:
                    self.weights[c] = 1e-6
            self.weights /= self.weights.sum()

    def _log_gaussian(self, x: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
        """Log of a single Gaussian pdf, diagonal covariance.

        x: (N, dim), mu: (dim,), var: (dim,)
        Returns: (N,)
        """
        diff = x - mu
        log_coef = -0.5 * self.dim * math.log(2.0 * math.pi)
        log_det = -0.5 * np.sum(np.log(np.maximum(var, 1e-30)))
        log_exp = -0.5 * np.sum(diff ** 2 / np.maximum(var, 1e-30), axis=1)
        return log_coef + log_det + log_exp

    def _log_likelihood(self, data: np.ndarray) -> float:
        """Scalar log-likelihood of the full dataset."""
        lls = self._log_likelihood_batch(data)
        return float(np.sum(lls))

    def _log_likelihood_batch(self, data: np.ndarray) -> np.ndarray:
        """Per-sample log-likelihood.  Returns ``(N,)`` array."""
        n = data.shape[0]
        k = self.n_components
        # (N, K) log-probs
        log_probs = np.zeros((n, k), dtype=np.float64)
        for c in range(k):
            log_probs[:, c] = (
                math.log(max(self.weights[c], 1e-30))
                + self._log_gaussian(data, self.means[c], self.variances[c])
            )
        # Log-sum-exp across K
        max_lp = log_probs.max(axis=1, keepdims=True)
        return (max_lp.ravel() + np.log(np.sum(np.exp(log_probs - max_lp), axis=1)))

    def _e_step(self, data: np.ndarray) -> np.ndarray:
        """Compute responsibilities ``(N, K)``."""
        n = data.shape[0]
        k = self.n_components
        log_resp = np.zeros((n, k), dtype=np.float64)
        for c in range(k):
            log_resp[:, c] = (
                math.log(max(self.weights[c], 1e-30))
                + self._log_gaussian(data, self.means[c], self.variances[c])
            )
        # Normalise with log-sum-exp
        max_lr = log_resp.max(axis=1, keepdims=True)
        log_resp -= max_lr
        resp = np.exp(log_resp)
        resp /= resp.sum(axis=1, keepdims=True)
        return resp

    def _m_step(self, data: np.ndarray, resp: np.ndarray) -> None:
        """Update parameters from responsibilities."""
        n = data.shape[0]
        k = self.n_components
        for c in range(k):
            nk = resp[:, c].sum()
            if nk < 1e-6:
                continue
            self.weights[c] = nk / n
            self.means[c] = resp[:, c] @ data / nk
            diff = data - self.means[c]
            self.variances[c] = np.maximum(
                resp[:, c] @ (diff ** 2) / nk,
                1e-6,
            )


# ---------------------------------------------------------------------------
# AnomalyScorer — public API
# ---------------------------------------------------------------------------

class AnomalyScorer:
    """GMM-based open-set outlier scorer, one model per camera.

    Parameters
    ----------
    n_components : int
        Number of GMM mixture components (default from config).
    threshold : float
        NLL threshold above which a frame is considered anomalous.
    min_frames : int
        Minimum embeddings required before scoring is enabled.
    """

    def __init__(
        self,
        n_components: int = _GMM_COMPONENTS,
        threshold: float = _ANOMALY_THRESHOLD,
        min_frames: int = _MIN_TRAINING_FRAMES,
    ) -> None:
        self._n_components = n_components
        self._threshold = threshold
        self._min_frames = min_frames

        self._gmm: dict[str, _DiagonalGMM] = {}
        self._buffers: dict[str, list[np.ndarray]] = {}
        self._frame_counts: dict[str, int] = {}
        self._anomaly_windows: dict[str, list[bool]] = {}
        self._embed_dim: int = 0
        self._thresholds: dict[str, float] = {}  # per-camera adaptive thresholds

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def is_ready(self, camera_id: str) -> bool:
        return (
            camera_id in self._gmm
            and self._gmm[camera_id].trained
            and self._frame_counts.get(camera_id, 0) >= self._min_frames
        )

    def frame_count(self, camera_id: str) -> int:
        return self._frame_counts.get(camera_id, 0)

    def set_threshold(self, camera_id: str, threshold: float) -> None:
        self._thresholds[camera_id] = threshold

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def feed_embedding(
        self,
        camera_id: str,
        embedding: np.ndarray,
    ) -> None:
        """Ingest an embedding and optionally (re-)fit the GMM.

        Call this every frame to keep the normal-distribution model current.
        """
        if embedding.ndim == 1:
            embedding = embedding.flatten()

        self._embed_dim = embedding.shape[0]

        count = self._frame_counts.get(camera_id, 0)
        self._frame_counts[camera_id] = count + 1

        buf = self._buffers.setdefault(camera_id, [])
        # Keep bounded buffer: at most 5x min_frames
        max_buf = self._min_frames * 5
        if len(buf) >= max_buf:
            buf.pop(0)
        buf.append(embedding)

        # Fit gate: first time we hit min_frames, and every 100 frames after
        should_fit = (
            count + 1 == self._min_frames
            or (count + 1 > self._min_frames and (count + 1) % 100 == 0)
        )
        if should_fit and len(buf) >= self._min_frames:
            self._fit_gmm(camera_id)

    def score(
        self,
        camera_id: str,
        embedding: np.ndarray,
    ) -> dict[str, Any] | None:
        """Score a single embedding against the learned normal distribution.

        Returns a result dict when the frame is anomalous, ``None`` otherwise.
        The result includes NLL-based score, per-component responsibilities,
        and temporal-smoothing state.

        A ``None`` is also returned when the camera is not yet ready (minimum
        data-volume guard).
        """
        if not self.is_ready(camera_id):
            return None

        if embedding.ndim == 1:
            embedding = embedding.flatten()

        gmm = self._gmm[camera_id]
        nll = gmm.score(embedding)

        # Per-camera adaptive threshold (95th-percentile of training NLLs)
        threshold = self._thresholds.get(camera_id, self._threshold)

        is_anomalous = nll > threshold

        # Temporal smoothing
        window = self._anomaly_windows.setdefault(camera_id, [])
        window.append(is_anomalous)
        if len(window) > _TEMPORAL_WINDOW:
            window.pop(0)
        flagged_count = sum(window)

        if flagged_count < _TEMPORAL_MIN_FLAGS:
            return None

        # Compute per-component responsibilities for explainability
        resp = gmm._e_step(embedding.reshape(1, -1)).flatten()
        dominant_component = int(np.argmax(resp))

        # Feature importance: which embedding dims contribute most to the NLL
        contributing_dims = self._embedding_contribution(gmm, embedding)

        return {
            "camera_id": camera_id,
            "anomaly_score": round(float(nll), 6),
            "threshold": round(float(threshold), 6),
            "is_anomalous": True,
            "dominant_component": dominant_component,
            "component_responsibilities": {
                f"comp_{i}": round(float(r), 6) for i, r in enumerate(resp)
            },
            "contributing_dims": contributing_dims,
            "temporal_flag_count": flagged_count,
            "temporal_window_size": _TEMPORAL_WINDOW,
            "embedding_dim": int(embedding.shape[0]),
        }

    def score_batch(
        self,
        camera_id: str,
        embeddings: np.ndarray,
    ) -> list[dict[str, Any] | None]:
        """Score a batch of embeddings."""
        return [self.score(camera_id, e) for e in embeddings]

    def compute_threshold(
        self,
        camera_id: str,
        percentile: float = 95.0,
    ) -> float | None:
        """Compute an adaptive threshold from training data NLLs.

        Returns the NLL value at the given percentile, or ``None`` if
        insufficient data.
        """
        buf = self._buffers.get(camera_id, [])
        if len(buf) < self._min_frames or camera_id not in self._gmm:
            return None

        data = np.stack(buf, axis=0)
        nlls = self._gmm[camera_id].score_batch(data)
        threshold = float(np.percentile(nlls, percentile))
        self._thresholds[camera_id] = threshold
        return threshold

    def snapshot(self, camera_id: str) -> dict[str, Any] | None:
        """Serialisable state snapshot for persistence."""
        if camera_id not in self._gmm:
            return None
        gmm = self._gmm[camera_id]
        return {
            "camera_id": camera_id,
            "n_components": gmm.n_components,
            "dim": gmm.dim,
            "weights": gmm.weights.tolist(),
            "means": gmm.means.tolist(),
            "variances": gmm.variances.tolist(),
            "trained": gmm.trained,
            "frame_count": self._frame_counts.get(camera_id, 0),
            "min_frames": self._min_frames,
            "threshold": self._thresholds.get(camera_id, self._threshold),
            "log_likelihoods": gmm.log_likelihoods,
        }

    def load_snapshot(self, snap: dict[str, Any]) -> None:
        """Restore from a snapshot."""
        cid = snap["camera_id"]
        gmm = _DiagonalGMM(snap["n_components"], snap["dim"])
        gmm.weights = np.array(snap["weights"], dtype=np.float64)
        gmm.means = np.array(snap["means"], dtype=np.float64)
        gmm.variances = np.array(snap["variances"], dtype=np.float64)
        gmm.trained = snap["trained"]
        gmm.log_likelihoods = snap.get("log_likelihoods", [])
        self._gmm[cid] = gmm
        self._frame_counts[cid] = snap["frame_count"]
        if "min_frames" in snap:
            self._min_frames = min(self._min_frames, snap["min_frames"])
        self._thresholds[cid] = snap.get("threshold", self._threshold)

    def reset(self, camera_id: str) -> None:
        self._gmm.pop(camera_id, None)
        self._buffers.pop(camera_id, None)
        self._frame_counts.pop(camera_id, None)
        self._anomaly_windows.pop(camera_id, None)
        self._thresholds.pop(camera_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fit_gmm(self, camera_id: str) -> None:
        buf = self._buffers.get(camera_id, [])
        if len(buf) < self._min_frames:
            return

        data = np.stack(buf, axis=0).astype(np.float64)
        n, dim = data.shape
        k = min(self._n_components, max(1, n // 5))  # don't over-fit with too many components

        gmm = _DiagonalGMM(k, dim)
        gmm.fit(data)
        self._gmm[camera_id] = gmm

        # Auto-compute adaptive threshold at 95th percentile
        nlls = gmm.score_batch(data)
        self._thresholds[camera_id] = float(np.percentile(nlls, 95.0))

        logger.info(
            "anomaly_scorer_fitted camera=%s frames=%d components=%d threshold=%.4f",
            camera_id,
            n,
            k,
            self._thresholds[camera_id],
        )

    @staticmethod
    def _embedding_contribution(
        gmm: _DiagonalGMM,
        embedding: np.ndarray,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Identify which embedding dimensions contribute most to the anomaly score.

        Uses a simple per-dimension NLL decomposition under the dominant
        component.
        """
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)

        resp = gmm._e_step(embedding).flatten()
        dominant = int(np.argmax(resp))
        mu = gmm.means[dominant]
        var = gmm.variances[dominant]

        # Per-dimension contribution: (x - mu)^2 / var
        diff_sq = (embedding.flatten() - mu) ** 2 / np.maximum(var, 1e-30)
        dim_scores = diff_sq / diff_sq.sum()  # normalised

        top_dims = np.argsort(dim_scores)[::-1][:top_k]
        return [
            {
                "dim": int(d),
                "contribution": round(float(dim_scores[d]), 6),
                "value": round(float(embedding.flatten()[d]), 6),
                "expected": round(float(mu[d]), 6),
            }
            for d in top_dims
        ]
