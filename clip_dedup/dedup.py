from __future__ import annotations

import json
import logging
import os
import shutil
from collections import defaultdict

import numpy as np

from clip_dedup.index import build_index, query_index

logger = logging.getLogger("clip_dedup.dedup")


def _resolve_groups(pairs: list[tuple[int, int, float]], n: int) -> list[list[int]]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j, _sim in pairs:
        union(i, j)

    group_map: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        group_map[find(i)].append(i)

    groups = [members for members in group_map.values() if len(members) > 1]
    return groups


def _resolution(path: str) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def _pick_canonical(members: list[int], image_paths: list[str]) -> int:
    resolutions = [(i, _resolution(image_paths[i])) for i in members]
    resolutions.sort(key=lambda x: x[1][0] * x[1][1], reverse=True)
    return resolutions[0][0]


def run_dedup(
    embeddings: np.ndarray,
    image_paths: list[str],
    valid_indices: list[int],
    threshold: float = 0.95,
    output_dir: str = "./cleaned",
    quarantine_subdir: str = "duplicates",
    audit_path: str = "dedup_audit.json",
    use_ivf: bool = False,
) -> list[dict]:
    valid_mask = np.zeros(len(image_paths), dtype=bool)
    valid_mask[valid_indices] = True

    index = build_index(embeddings, use_ivf=use_ivf)
    pairs = query_index(index, embeddings, threshold)
    pairs = [(i, j, sim) for i, j, sim in pairs if valid_mask[i] and valid_mask[j]]

    groups = _resolve_groups(pairs, len(image_paths))
    groups = [[m for m in g if valid_mask[m]] for g in groups]
    groups = [g for g in groups if len(g) > 1]

    logger.info(
        "Total: %d images | Valid: %d | Groups: %d | To remove: %d",
        len(image_paths),
        len(valid_indices),
        len(groups),
        sum(len(g) - 1 for g in groups),
    )

    os.makedirs(output_dir, exist_ok=True)
    dup_dir = os.path.join(output_dir, quarantine_subdir)
    os.makedirs(dup_dir, exist_ok=True)

    audit_entries: list[dict] = []

    for group in groups:
        canonical_idx = _pick_canonical(group, image_paths)
        canonical_path = image_paths[canonical_idx]

        removed: list[str] = []
        similarities: list[float] = []

        group_sims = defaultdict(list)
        for i, j, sim in pairs:
            if i in group and j in group:
                group_sims[(i, j)] = sim
                group_sims[(j, i)] = sim

        for member_idx in group:
            member_path = image_paths[member_idx]
            if member_idx == canonical_idx:
                continue

            dup_dest = os.path.join(dup_dir, os.path.basename(member_path))
            if os.path.isfile(member_path):
                shutil.move(member_path, dup_dest)

            removed.append(member_path)

            best_sim = 0.0
            for other_idx in group:
                if other_idx != member_idx:
                    sim = group_sims.get((member_idx, other_idx), 0.0)
                    if sim > best_sim:
                        best_sim = sim
            similarities.append(round(best_sim, 4))

        entry = {
            "group_id": f"dedup_{canonical_idx:06d}",
            "kept": canonical_path,
            "removed": removed,
            "similarities": similarities,
            "group_size": len(group),
        }
        audit_entries.append(entry)

    with open(audit_path, "w") as f:
        json.dump(audit_entries, f, indent=2)

    logger.info("Audit saved to %s (%d groups)", audit_path, len(audit_entries))
    return audit_entries
