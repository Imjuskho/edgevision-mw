from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger("clip_dedup.index")

try:
    import faiss

    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss not available; using brute-force numpy fallback")


def build_index(embeddings: np.ndarray, use_ivf: bool = False, nlist: int = 100):
    if not FAISS_AVAILABLE:
        return None

    dim = embeddings.shape[1]
    if use_ivf and embeddings.shape[0] > nlist * 10:
        quantizer = faiss.IndexFlatIP(dim)
        index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = 10
        logger.info(
            "Built IVF index: %d vectors, dim=%d, nlist=%d",
            embeddings.shape[0],
            dim,
            nlist,
        )
    else:
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        logger.info("Built Flat index: %d vectors, dim=%d", embeddings.shape[0], dim)

    return index


def save_index(index, path: str):
    if not FAISS_AVAILABLE:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    faiss.write_index(index, path)
    logger.info("Index saved to %s", path)


def load_index(path: str):
    if not FAISS_AVAILABLE:
        return None
    if not os.path.isfile(path):
        logger.warning("Index not found: %s", path)
        return None
    index = faiss.read_index(path)
    logger.info("Index loaded from %s (%d vectors)", path, index.ntotal)
    return index


def query_index(
    index,
    embeddings: np.ndarray,
    threshold: float = 0.95,
    max_k: int | None = None,
) -> list[tuple[int, int, float]]:
    if index is None:
        return _brute_force_query(embeddings, threshold)

    n = embeddings.shape[0]
    k = min(max_k or n, n)
    similarities, neighbors = index.search(embeddings, k)

    pairs: list[tuple[int, float, int]] = []
    for i in range(n):
        for j in range(k):
            nid = int(neighbors[i][j])
            sim = float(similarities[i][j])
            if nid == i:
                continue
            if sim >= threshold:
                pairs.append((i, sim, nid))

    seen: set[tuple[int, int]] = set()
    results: list[tuple[int, int, float]] = []
    for i, sim, j in pairs:
        key = (min(i, j), max(i, j))
        if key not in seen:
            seen.add(key)
            results.append((i, j, sim))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def _brute_force_query(
    embeddings: np.ndarray, threshold: float
) -> list[tuple[int, int, float]]:
    n = embeddings.shape[0]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.where(norms > 0, norms, 1.0)
    sim_matrix = normalized @ normalized.T

    pairs: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i][j])
            if sim >= threshold:
                pairs.append((i, j, sim))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs
