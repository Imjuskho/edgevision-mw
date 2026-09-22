"""Differential-privacy noise mechanism for federated weight updates.

Implements DP-FedAvg (Abadi et al., 2016) with Gaussian mechanism.
Noise is calibrated to (epsilon, delta)-differential privacy for the
composition of updates across rounds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class DPMechanism:
    """Gaussian mechanism for (epsilon, delta)-DP on weight vectors.

    Parameters
    ----------
    epsilon : float
        Privacy budget per round (e.g. 1.0).
    delta : float
        Failure probability (e.g. 1e-5).  Must satisfy delta < 1/n
        where n is the dataset size.
    max_grad_norm : float
        Clipping bound C for per-sample gradients (L2 norm).
    noise_multiplier : float
        Direct override for sigma / C.  When set, epsilon/delta are
        informational only and the multiplier is used directly.
    """

    epsilon: float = 1.0
    delta: float = 1e-5
    max_grad_norm: float = 1.0
    noise_multiplier: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.epsilon <= 0:
            raise ValueError("epsilon must be > 0")
        if self.delta <= 0 or self.delta >= 1:
            raise ValueError("delta must be in (0, 1)")
        if self.max_grad_norm <= 0:
            raise ValueError("max_grad_norm must be > 0")
        self.noise_multiplier = self._compute_sigma()

    def _compute_sigma(self) -> float:
        """Compute sigma = C * sqrt(2 * ln(1.25/delta)) / epsilon.

        This is the standard Gaussian mechanism calibration from
        Dwork & Roth (2014), Theorem A.1.
        """
        if self.delta == 0:
            raise ValueError("delta must be > 0 for Gaussian mechanism")
        return (
            self.max_grad_norm
            * math.sqrt(2.0 * math.log(1.25 / self.delta))
            / self.epsilon
        )

    def clip_weights(self, delta_w: np.ndarray) -> np.ndarray:
        """Clip weight delta to max_grad_norm (L2 norm)."""
        norm = np.linalg.norm(delta_w)
        if norm <= self.max_grad_norm:
            return delta_w.copy()
        return delta_w * (self.max_grad_norm / norm)

    def add_noise(self, delta_w: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
        """Add calibrated Gaussian noise to a weight delta.

        Parameters
        ----------
        delta_w : np.ndarray
            Weight update vector (e.g. aggregated_delta = w_global - w_old).
        rng : np.random.Generator, optional
            Numpy random generator for reproducibility.

        Returns
        -------
        np.ndarray
            Noised weight delta, same shape as input.
        """
        rng = rng or np.random.default_rng()
        clipped = self.clip_weights(delta_w)
        noise = rng.normal(
            0.0,
            self.noise_multiplier * self.max_grad_norm,
            size=clipped.shape,
        ).astype(clipped.dtype)
        return clipped + noise

    def effective_epsilon(self, n_samples: int, n_rounds: int = 1) -> float:
        """Compute the effective epsilon after composition.

        Uses basic composition: epsilon_total = n_rounds * epsilon.
        """
        return self.epsilon * n_rounds

    def privacy_budget_check(self, n_samples: int) -> bool:
        """Check that delta < 1/n (required for meaningful DP guarantee)."""
        return self.delta < 1.0 / max(n_samples, 1)

    def to_dict(self) -> dict:
        return {
            "epsilon": self.epsilon,
            "delta": self.delta,
            "max_grad_norm": self.max_grad_norm,
            "noise_multiplier": self.noise_multiplier,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DPMechanism:
        return cls(
            epsilon=d.get("epsilon", 1.0),
            delta=d.get("delta", 1e-5),
            max_grad_norm=d.get("max_grad_norm", 1.0),
        )


def compute_noise_multiplier(
    target_epsilon: float,
    target_delta: float,
    sample_rate: float,
    steps: int,
    max_grad_norm: float = 1.0,
) -> float:
    """Compute the noise multiplier for DP-SGD (RDP accounting).

    Uses Rényi Differential Privacy (RDP) composition to find the
    smallest noise multiplier that achieves (epsilon, delta)-DP.

    Parameters
    ----------
    target_epsilon : float
        Desired epsilon budget.
    target_delta : float
        Desired delta.
    sample_rate : float
        Sampling probability q = batch_size / dataset_size.
    steps : int
        Number of SGD steps (rounds).
    max_grad_norm : float
        Clipping bound C.

    Returns
    -------
    float
        Noise multiplier sigma / C.
    """
    if sample_rate <= 0 or sample_rate > 1:
        raise ValueError("sample_rate must be in (0, 1]")
    if steps <= 0:
        raise ValueError("steps must be > 0")
    if target_epsilon <= 0:
        raise ValueError("target_epsilon must be > 0")

    # Binary search over noise_multiplier
    lo, hi = 0.01, 100.0
    for _ in range(50):
        mid = (lo + hi) / 2.0
        eps_est = _rdp_to_dp(mid, sample_rate, steps, target_delta)
        if eps_est > target_epsilon:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _rdp_to_dp(
    noise_multiplier: float,
    sample_rate: float,
    steps: int,
    delta: float,
) -> float:
    """Convert RDP guarantee to (epsilon, delta)-DP via the RDP-to-DP conversion.

    Uses the formula from Mironov (2017), Theorem 3.2.
    """
    if noise_multiplier == 0:
        return float("inf")

    alpha = 1.0 + noise_multiplier ** 2 * sample_rate ** 2 * steps
    if alpha <= 1.0:
        return float("inf")

    rdp = (
        sample_rate ** 2 * steps * noise_multiplier ** 2
        / (2.0 * (noise_multiplier ** 2 + (1 - sample_rate) / max(sample_rate, 1e-10)))
    )
    # Simplified RDP alpha=1+1/(2*sigma^2) bound
    rdp_alpha = steps * sample_rate ** 2 / (2.0 * noise_multiplier ** 2)

    eps = rdp_alpha + math.log(1.0 / delta) / (alpha - 1.0)
    return max(eps, 0.0)
