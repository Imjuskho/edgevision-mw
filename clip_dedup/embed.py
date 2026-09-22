from __future__ import annotations

import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import torch
from PIL import Image

import open_clip

logger = logging.getLogger("clip_dedup.embed")

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def _image_hash(filepath: str) -> str:
    return hashlib.sha256(filepath.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: str, filepath: str) -> str:
    h = _image_hash(filepath)
    return os.path.join(cache_dir, f"{h}.npy")


def load_model(model_name: str = "ViT-B-32", device: str | None = None):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained="openai"
    )
    model = model.to(device)
    model.eval()
    tokenizer = open_clip.get_tokenizer(model_name)
    logger.info("Model loaded: %s on %s", model_name, device)
    return model, preprocess, tokenizer, device


def compute_embeddings(
    image_paths: list[str],
    model,
    preprocess,
    device: str,
    batch_size: int = 64,
    num_workers: int = 4,
    cache_dir: str | None = None,
    show_progress: bool = True,
) -> tuple[np.ndarray, list[str], list[int]]:
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    to_compute: list[tuple[int, str]] = []
    if cache_dir:
        for i, fp in enumerate(image_paths):
            cp = _cache_path(cache_dir, fp)
            if not os.path.isfile(cp):
                to_compute.append((i, fp))
        logger.info(
            "Cache: %d total, %d cached, %d to compute",
            len(image_paths),
            len(image_paths) - len(to_compute),
            len(to_compute),
        )
    else:
        to_compute = list(enumerate(image_paths))

    if not to_compute and cache_dir:
        all_embs = []
        for fp in image_paths:
            cp = _cache_path(cache_dir, fp)
            arr = np.load(cp)
            all_embs.append(arr.squeeze(0) if arr.ndim == 2 else arr)
        return np.stack(all_embs, axis=0), image_paths, list(range(len(image_paths)))

    def load_image(path: str):
        try:
            img = Image.open(path).convert("RGB")
            return preprocess(img)
        except Exception as exc:
            logger.warning("Failed to load image %s: %s", path, exc)
            return None

    pbar = None
    if show_progress and len(to_compute) > 1000:
        try:
            from tqdm import tqdm
            pbar = tqdm(total=len(to_compute), desc="Loading", unit="img")
        except ImportError:
            pass

    tensors: list[tuple[int, torch.Tensor]] = []
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        fut_map = {pool.submit(load_image, fp): (i, fp) for i, fp in to_compute}
        for fut in as_completed(fut_map):
            idx, fp = fut_map[fut]
            result = fut.result()
            if result is not None:
                tensors.append((idx, result))
            if pbar:
                pbar.update(1)

    if pbar:
        pbar.close()

    tensors.sort(key=lambda x: x[0])
    valid_indices = [idx for idx, _ in tensors]
    valid_paths = [image_paths[idx] for idx in valid_indices]

    if not tensors:
        logger.error("No valid images found")
        return np.empty((0, 512)), [], []

    all_tensors = torch.stack([t for _, t in tensors], dim=0)
    all_embeddings: list[np.ndarray] = []

    if show_progress:
        try:
            from tqdm import tqdm
            pbar = tqdm(total=len(tensors), desc="Embedding", unit="img")
        except ImportError:
            pbar = None
    else:
        pbar = None

    with torch.no_grad():
        for start in range(0, len(all_tensors), batch_size):
            end = min(start + batch_size, len(all_tensors))
            batch = all_tensors[start:end].to(device)
            emb = model.encode_image(batch)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            all_embeddings.append(emb.cpu().numpy())
            if pbar:
                pbar.update(end - start)

    if pbar:
        pbar.close()

    embeddings = np.concatenate(all_embeddings, axis=0)

    if cache_dir:
        for idx, fp in zip(valid_indices, valid_paths):
            cp = _cache_path(cache_dir, fp)
            if not os.path.isfile(cp):
                pos = valid_indices.index(idx)
                np.save(cp, embeddings[pos])

    full_embeddings = np.zeros((len(image_paths), embeddings.shape[1]), dtype=np.float32)
    for i in range(len(image_paths)):
        if i in valid_indices:
            pos = valid_indices.index(i)
            full_embeddings[i] = embeddings[pos]
        else:
            full_embeddings[i] = np.zeros(embeddings.shape[1], dtype=np.float32)

    return full_embeddings, image_paths, valid_indices


def collect_images(input_dir: str, recursive: bool = True) -> list[str]:
    results: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(input_dir):
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext in _SUPPORTED_EXTS:
                    results.append(os.path.join(root, fname))
    else:
        for fname in sorted(os.listdir(input_dir)):
            fp = os.path.join(input_dir, fname)
            if os.path.isfile(fp):
                ext = os.path.splitext(fname)[1].lower()
                if ext in _SUPPORTED_EXTS:
                    results.append(fp)
    return results
