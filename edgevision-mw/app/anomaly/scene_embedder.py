"""Self-supervised scene embedding model, trained per-camera.

Extracts a fixed-length feature vector from raw frames and learns a compact
bottleneck representation via a shallow autoencoder.  The encoder weights
are kept in-memory, one set per ``camera_node_id``.

Feature vector layout (86 dimensions)
--------------------------------------
- 24  colour histogram  (3 channels x 8 bins, normalised)
- 8   edge orientation histogram (Sobel magnitude, 8 orientation bins)
- 48  spatial colour moments (4x4 grid x 3 channels x 1 stat: mean)
- 6   global statistics (brightness, saturation, contrast, edge density,
      R-channel spread, G-channel spread)

Minimum data-volume guard
-------------------------
A camera must have observed at least ``ANOMALY_MIN_TRAINING_FRAMES``
normal frames before the autoencoder is trained and embeddings become
available.  Before that threshold the ``encode`` method returns ``None``
and ``is_ready`` returns ``False``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_RAW_DIM = 86
_DEFAULT_EMBED_DIM = 16
_MIN_TRAINING_FRAMES = settings.ANOMALY_MIN_TRAINING_FRAMES
_EMBED_DIM = settings.ANOMALY_EMBEDDING_DIM

# Autoencoder hyper-parameters
_LEARNING_RATE = 1e-3
_EPOCHS = 50
_BATCH_SIZE = 32
_REGULARISATION = 1e-5
_GRAD_CLIP = 5.0


# ---------------------------------------------------------------------------
# Feature extraction (pure numpy, optional cv2 acceleration)
# ---------------------------------------------------------------------------

def _extract_features(frame_bytes: bytes | None = None, frame_rgb: np.ndarray | None = None) -> np.ndarray:
    """Extract an 86-dim feature vector from a single frame.

    Accepts either raw JPEG/PNG bytes or an already-decoded RGB ndarray
    of shape ``(H, W, 3)`` with dtype ``uint8``.
    """
    img = frame_rgb
    if img is None and frame_bytes is not None:
        img = _decode_bytes(frame_bytes)
    if img is None:
        # Degenerate fallback — return zeros so callers never crash.
        return np.zeros(_RAW_DIM, dtype=np.float64)

    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    if img.shape[2] == 4:
        img = img[:, :, :3]

    features: list[float] = []

    # 1. Colour histogram (24-dim) — 8 bins per channel
    for ch in range(3):
        channel = img[:, :, ch].astype(np.float64)
        hist, _ = np.histogram(channel, bins=8, range=(0, 256))
        hist = hist.astype(np.float64)
        total = hist.sum()
        if total > 0:
            hist /= total
        features.extend(hist.tolist())

    # 2. Edge orientation histogram (8-dim)
    gray = np.mean(img.astype(np.float64), axis=2)
    gx, gy = _sobel(gray)
    magnitude = np.sqrt(gx ** 2 + gy ** 2)
    orientation = (np.arctan2(gy, gx) + np.pi) * (180.0 / np.pi)  # [0, 360)
    orient_hist, _ = np.histogram(orientation[magnitude > 10], bins=8, range=(0, 360))
    orient_sum = orient_hist.sum()
    if orient_sum > 0:
        orient_hist = orient_hist.astype(np.float64) / orient_sum
    features.extend(orient_hist.astype(np.float64).tolist())

    # 3. Spatial colour moments (48-dim) — 4x4 grid x 3 channels x 1 stat (mean)
    h, w = img.shape[:2]
    grid_h, grid_w = 4, 4
    cell_h, cell_w = max(h // grid_h, 1), max(w // grid_w, 1)
    for gi in range(grid_h):
        for gj in range(grid_w):
            cell = img[gi * cell_h:(gi + 1) * cell_h, gj * cell_w:(gj + 1) * cell_w].astype(np.float64)
            for ch in range(3):
                features.append(float(np.mean(cell[:, :, ch]) / 255.0))

    # 4. Global statistics (6-dim)
    hsv = _rgb_to_hsv(img)
    features.append(float(np.mean(hsv[:, :, 2]) / 255.0))   # brightness
    features.append(float(np.mean(hsv[:, :, 1]) / 255.0))   # saturation
    features.append(float(np.std(hsv[:, :, 2]) / 255.0))    # contrast
    features.append(float(np.mean(magnitude) / 128.0))       # edge density
    # Colour spread: std of R and G channels (B captured by contrast)
    features.append(float(np.std(img[:, :, 0]) / 255.0))
    features.append(float(np.std(img[:, :, 1]) / 255.0))

    vec = np.array(features, dtype=np.float64)
    assert vec.shape[0] == _RAW_DIM, f"Feature dim mismatch: {vec.shape[0]} != {_RAW_DIM}"
    return vec


def _decode_bytes(frame_bytes: bytes) -> np.ndarray | None:
    """Attempt to decode image bytes to an RGB numpy array."""
    try:
        import cv2

        nparr = np.frombuffer(frame_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if bgr is not None:
            return bgr[:, :, ::-1].copy()  # BGR → RGB
    except Exception:
        pass
    # Pure-numpy PPM fallback (rare but avoids hard cv2 dep)
    try:
        if frame_bytes[:3] == b"P6":
            return _decode_ppm(frame_bytes)
    except Exception:
        pass
    return None


def _decode_ppm(data: bytes) -> np.ndarray:
    """Minimal P6 PPM decoder."""
    tokens = data.split()
    if len(tokens) < 4:
        raise ValueError("Invalid PPM")
    w, h = int(tokens[1]), int(tokens[2])
    maxval = int(tokens[3])
    offset = data.index(tokens[3]) + len(tokens[3]) + 1
    raw = data[offset:w * h * 3]
    arr = np.frombuffer(raw, dtype=np.uint8 if maxval < 256 else np.uint16)
    arr = arr.reshape(h, w, 3)
    if maxval > 255:
        arr = (arr / 256).astype(np.uint8)
    return arr


def _sobel(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """3x3 Sobel operator, pure numpy."""
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float64)
    h, w = gray.shape
    padded = np.pad(gray, 1, mode="edge")
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    for i in range(3):
        for j in range(3):
            gx += kx[i, j] * padded[i:i + h, j:j + w]
            gy += ky[i, j] * padded[i:i + h, j:j + w]
    return gx, gy


def _rgb_to_hsv(img: np.ndarray) -> np.ndarray:
    """Vectorised RGB→HSV, output in [0, 1] x [0, 1] x [0, 255]."""
    r = img[:, :, 0].astype(np.float64) / 255.0
    g = img[:, :, 1].astype(np.float64) / 255.0
    b = img[:, :, 2].astype(np.float64) / 255.0
    mx = np.maximum(r, np.maximum(g, b))
    mn = np.minimum(r, np.minimum(g, b))
    diff = mx - mn

    hue = np.zeros_like(mx)
    sat = np.zeros_like(mx)
    val = mx * 255.0

    nonzero = diff > 1e-8
    sat[nonzero] = diff[nonzero] / mx[nonzero]

    r_eq = nonzero & (mx == r)
    g_eq = nonzero & (mx == g)
    b_eq = nonzero & (mx == b)
    hue[r_eq] = 60.0 * (((g[r_eq] - b[r_eq]) / diff[r_eq]) % 6)
    hue[g_eq] = 60.0 * (((b[g_eq] - r[g_eq]) / diff[g_eq]) + 2)
    hue[b_eq] = 60.0 * (((r[b_eq] - g[b_eq]) / diff[b_eq]) + 4)

    hsv = np.stack([hue / 360.0, sat, val], axis=2)
    return hsv


# ---------------------------------------------------------------------------
# Per-camera autoencoder (numpy only)
# ---------------------------------------------------------------------------

class _Autoencoder:
    """Shallow linear autoencoder implemented in pure numpy."""

    __slots__ = ("w_enc", "b_enc", "w_dec", "b_dec", "raw_dim", "embed_dim", "trained")

    def __init__(self, raw_dim: int, embed_dim: int) -> None:
        self.raw_dim = raw_dim
        self.embed_dim = embed_dim
        self.trained = False
        # Xavier init
        lim_enc = math.sqrt(6.0 / (raw_dim + embed_dim))
        self.w_enc = np.random.uniform(-lim_enc, lim_enc, (embed_dim, raw_dim))
        self.b_enc = np.zeros(embed_dim, dtype=np.float64)
        lim_dec = math.sqrt(6.0 / (embed_dim + raw_dim))
        self.w_dec = np.random.uniform(-lim_dec, lim_dec, (raw_dim, embed_dim))
        self.b_dec = np.zeros(raw_dim, dtype=np.float64)

    def encode(self, x: np.ndarray) -> np.ndarray:
        """Encode a single feature vector or batch.  Returns bottleneck activation."""
        if x.ndim == 1:
            x = x[np.newaxis, :]
        hidden = x @ self.w_enc.T + self.b_enc
        return np.maximum(hidden, 0.0)  # ReLU

    def decode(self, z: np.ndarray) -> np.ndarray:
        if z.ndim == 1:
            z = z[np.newaxis, :]
        return z @ self.w_dec.T + self.b_dec

    def reconstruct(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        z = self.encode(x)
        return self.decode(z), z

    def train(self, data: np.ndarray) -> list[float]:
        """Train on ``(N, raw_dim)`` array with mini-batch SGD."""
        n = data.shape[0]
        losses: list[float] = []
        rng = np.random.default_rng(42)

        for epoch in range(_EPOCHS):
            perm = rng.permutation(n)
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, n, _BATCH_SIZE):
                idx = perm[start:start + _BATCH_SIZE]
                batch = data[idx]
                bs = batch.shape[0]

                # Forward
                z_pre = batch @ self.w_enc.T + self.b_enc
                z = np.maximum(z_pre, 0.0)
                y = z @ self.w_dec.T + self.b_dec

                # MSE loss
                diff = y - batch
                loss = float(np.mean(diff ** 2))
                epoch_loss += loss
                n_batches += 1

                # Backward
                # dL/dy = 2*(y - x) / bs
                d_out = 2.0 * diff / bs

                # Decoder grads
                d_w_dec = d_out.T @ z
                d_b_dec = d_out.sum(axis=0)

                # Through ReLU
                d_z = d_out @ self.w_dec
                d_z *= (z_pre > 0).astype(np.float64)

                # Encoder grads
                d_w_enc = d_z.T @ batch
                d_b_enc = d_z.sum(axis=0)

                # Gradient clipping
                for g in (d_w_enc, d_b_enc, d_w_dec, d_b_dec):
                    np.clip(g, -_GRAD_CLIP, _GRAD_CLIP, out=g)

                # Update with L2 regularisation
                self.w_enc -= _LEARNING_RATE * (d_w_enc + _REGULARISATION * self.w_enc)
                self.b_enc -= _LEARNING_RATE * d_b_enc
                self.w_dec -= _LEARNING_RATE * (d_w_dec + _REGULARISATION * self.w_dec)
                self.b_dec -= _LEARNING_RATE * d_b_dec

            avg_loss = epoch_loss / max(n_batches, 1)
            losses.append(avg_loss)

        self.trained = True
        return losses


# ---------------------------------------------------------------------------
# SceneEmbedder — public API
# ---------------------------------------------------------------------------

class SceneEmbedder:
    """Per-camera self-supervised scene embedding.

    Maintains one :class:`_Autoencoder` per camera and a rolling buffer of
    feature vectors used for (re-)training.

    Parameters
    ----------
    embed_dim : int
        Bottleneck dimension (default from ``ANOMALY_EMBEDDING_DIM``).
    min_frames : int
        Minimum frames before training is triggered (default from
        ``ANOMALY_MIN_TRAINING_FRAMES``).
    retrain_every : int
        Re-train the autoencoder every *N* new frames after the initial fit.
    """

    def __init__(
        self,
        embed_dim: int = _EMBED_DIM,
        min_frames: int = _MIN_TRAINING_FRAMES,
        retrain_every: int = 50,
    ) -> None:
        self._embed_dim = embed_dim
        self._min_frames = min_frames
        self._retrain_every = retrain_every

        # Per-camera state
        self._buffers: dict[str, list[np.ndarray]] = {}
        self._autoencoders: dict[str, _Autoencoder] = {}
        self._frame_counts: dict[str, int] = {}
        self._train_losses: dict[str, list[float]] = {}
        self._feature_means: dict[str, np.ndarray] = {}
        self._feature_stds: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def is_ready(self, camera_id: str) -> bool:
        """Return ``True`` when the camera has enough data and a trained model."""
        return (
            camera_id in self._autoencoders
            and self._autoencoders[camera_id].trained
            and self._frame_counts.get(camera_id, 0) >= self._min_frames
        )

    def frame_count(self, camera_id: str) -> int:
        return self._frame_counts.get(camera_id, 0)

    def embedding_dim(self) -> int:
        return self._embed_dim

    def raw_dim(self) -> int:
        return _RAW_DIM

    def get_train_losses(self, camera_id: str) -> list[float]:
        return list(self._train_losses.get(camera_id, []))

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def feed_frame(
        self,
        camera_id: str,
        frame_bytes: bytes | None = None,
        frame_rgb: np.ndarray | None = None,
    ) -> np.ndarray | None:
        """Ingest a new frame: extract features, buffer, and optionally train.

        Returns the raw feature vector.  Returns ``None`` if the frame could
        not be decoded.
        """
        feat = _extract_features(frame_bytes=frame_bytes, frame_rgb=frame_rgb)
        if not np.any(feat):
            return None

        count = self._frame_counts.get(camera_id, 0)
        self._frame_counts[camera_id] = count + 1

        # Buffer up to 2x min_frames for training (bounded memory)
        buf = self._buffers.setdefault(camera_id, [])
        if len(buf) < self._min_frames * 2:
            buf.append(feat)

        # Train / retrain gate
        should_train = (
            count + 1 == self._min_frames
            or (count + 1 > self._min_frames and (count + 1) % self._retrain_every == 0)
        )
        if should_train and len(buf) >= self._min_frames:
            self._train_autoencoder(camera_id)

        return feat

    def encode(
        self,
        camera_id: str,
        frame_bytes: bytes | None = None,
        frame_rgb: np.ndarray | None = None,
    ) -> np.ndarray | None:
        """Encode a frame into the learned embedding space.

        Returns an ``(embed_dim,)`` ndarray or ``None`` if the camera is not
        yet ready or the frame is invalid.
        """
        if not self.is_ready(camera_id):
            return None

        feat = _extract_features(frame_bytes=frame_bytes, frame_rgb=frame_rgb)
        if not np.any(feat):
            return None

        # Z-score normalise using the camera-specific statistics
        mean = self._feature_means[camera_id]
        std = self._feature_stds[camera_id]
        feat_norm = (feat - mean) / np.where(std > 1e-8, std, 1.0)

        embedding = self._autoencoders[camera_id].encode(feat_norm)
        return embedding.flatten()

    def encode_feature(self, camera_id: str, feature_vec: np.ndarray) -> np.ndarray | None:
        """Encode an externally-computed feature vector (e.g. from the existing
        ``compute_scene_embedding`` dict-based pipeline).

        The vector is z-score normalised using the camera's stored statistics
        before encoding.
        """
        if not self.is_ready(camera_id):
            return None
        if feature_vec.shape[0] != _RAW_DIM:
            return None

        mean = self._feature_means[camera_id]
        std = self._feature_stds[camera_id]
        feat_norm = (feature_vec - mean) / np.where(std > 1e-8, std, 1.0)

        embedding = self._autoencoders[camera_id].encode(feat_norm)
        return embedding.flatten()

    def reconstruction_error(self, camera_id: str, feature_vec: np.ndarray) -> float | None:
        """MSE reconstruction error — higher means more anomalous."""
        if not self.is_ready(camera_id):
            return None
        if feature_vec.shape[0] != _RAW_DIM:
            return None

        mean = self._feature_means[camera_id]
        std = self._feature_stds[camera_id]
        feat_norm = (feature_vec - mean) / np.where(std > 1e-8, std, 1.0)

        recon, _ = self._autoencoders[camera_id].reconstruct(feat_norm)
        recon = recon.flatten()
        return float(np.mean((feat_norm - recon) ** 2))

    def snapshot(self, camera_id: str) -> dict[str, Any] | None:
        """Return a serialisable snapshot of the camera's model state."""
        if camera_id not in self._autoencoders:
            return None
        ae = self._autoencoders[camera_id]
        return {
            "camera_id": camera_id,
            "frame_count": self._frame_counts.get(camera_id, 0),
            "is_ready": self.is_ready(camera_id),
            "embed_dim": self._embed_dim,
            "raw_dim": _RAW_DIM,
            "min_frames": self._min_frames,
            "w_enc": ae.w_enc.tolist(),
            "b_enc": ae.b_enc.tolist(),
            "w_dec": ae.w_dec.tolist(),
            "b_dec": ae.b_dec.tolist(),
            "feature_mean": self._feature_means.get(camera_id, np.zeros(_RAW_DIM)).tolist(),
            "feature_std": self._feature_stds.get(camera_id, np.ones(_RAW_DIM)).tolist(),
            "train_losses": self._train_losses.get(camera_id, []),
        }

    def load_snapshot(self, snap: dict[str, Any]) -> None:
        """Restore a camera's model from a snapshot."""
        cid = snap["camera_id"]
        ae = _Autoencoder(snap["raw_dim"], snap["embed_dim"])
        ae.w_enc = np.array(snap["w_enc"], dtype=np.float64)
        ae.b_enc = np.array(snap["b_enc"], dtype=np.float64)
        ae.w_dec = np.array(snap["w_dec"], dtype=np.float64)
        ae.b_dec = np.array(snap["b_dec"], dtype=np.float64)
        ae.trained = True
        self._autoencoders[cid] = ae
        self._frame_counts[cid] = snap["frame_count"]
        if "min_frames" in snap:
            self._min_frames = min(self._min_frames, snap["min_frames"])
        self._feature_means[cid] = np.array(snap["feature_mean"], dtype=np.float64)
        self._feature_stds[cid] = np.array(snap["feature_std"], dtype=np.float64)
        self._train_losses[cid] = snap.get("train_losses", [])

    def reset(self, camera_id: str) -> None:
        """Discard all state for a camera."""
        self._buffers.pop(camera_id, None)
        self._autoencoders.pop(camera_id, None)
        self._frame_counts.pop(camera_id, None)
        self._train_losses.pop(camera_id, None)
        self._feature_means.pop(camera_id, None)
        self._feature_stds.pop(camera_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _train_autoencoder(self, camera_id: str) -> None:
        buf = self._buffers.get(camera_id, [])
        if len(buf) < self._min_frames:
            return

        data = np.stack(buf, axis=0).astype(np.float64)

        # Z-score normalisation (fit on training data)
        mean = data.mean(axis=0)
        std = data.std(axis=0)
        std = np.where(std < 1e-8, 1.0, std)
        data_norm = (data - mean) / std

        self._feature_means[camera_id] = mean
        self._feature_stds[camera_id] = std

        ae = _Autoencoder(_RAW_DIM, self._embed_dim)
        losses = ae.train(data_norm)
        self._autoencoders[camera_id] = ae
        self._train_losses[camera_id] = losses

        logger.info(
            "anomaly_embedder_trained camera=%s frames=%d final_loss=%.6f",
            camera_id,
            len(buf),
            losses[-1] if losses else 0.0,
        )
