from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Annotation,
    Dataset,
    DuplicateGroup,
    DuplicateGroupMember,
    ImageEmbedding,
    IngestionBatch,
)


@dataclass
class DuplicateCluster:
    group_id: str
    similarity: float
    method: str
    images: list[dict] = field(default_factory=list)
    orientation_mixed: bool = False


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _resolve_dataset_pk(db: AsyncSession, dataset_id: str) -> uuid.UUID:
    result = await db.execute(
        select(Dataset.id).where(Dataset.dataset_id == dataset_id)
    )
    pk = result.scalar_one_or_none()
    if pk is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")
    return pk


async def _annotation_info(
    db: AsyncSession, ann: Annotation
) -> dict:
    """Build the per-image dict required by DuplicateCluster.images."""
    batch = (
        await db.execute(
            select(IngestionBatch).where(IngestionBatch.id == ann.batch_id)
        )
    ).scalar_one_or_none()
    node_id = str(batch.node_id) if batch else "unknown"
    capture_time = batch.created_at.isoformat() if batch else None
    return {
        "image_id": str(ann.id),
        "image_path": ann.image_path,
        "node_id": node_id,
        "capture_time": capture_time,
        "thumbnail_url": f"/api/v1/annotations/{ann.id}/thumbnail",
    }


# ---------------------------------------------------------------------------
# Pass helpers
# ---------------------------------------------------------------------------

def _image_phash(data: bytes) -> int | None:
    """Perceptual hash (64-bit, DCT-based) of an image's bytes."""
    try:
        import cv2

        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        img = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
        dct = cv2.dct(np.float32(img))
        low = dct[:8, :8]
        median = np.median(low)
        bits = (low >= median).astype(np.uint8)
        return int.from_bytes(np.packbits(bits).tobytes(), "big")
    except Exception:
        return None


def _mirror_phash(phash: int) -> int:
    """Approximate horizontal-flip invariant hash by reversing bit order."""
    return int(format(phash, "064b")[::-1], 2)


def _phash_variants(data: bytes) -> tuple[int, int] | None:
    """Return ``(original_phash, mirror_phash)`` for mirror-invariant clustering."""
    original = _image_phash(data)
    if original is None:
        return None
    return original, _mirror_phash(original)


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


async def _load_phash_map(
    db: AsyncSession, dataset_pk: uuid.UUID
) -> dict[uuid.UUID, tuple[str, int, int]]:
    """Fetch images and compute original + mirror pHash variants."""
    from app.core.config import settings
    from app.core.minio_helper import get_object_bytes

    result = await db.execute(
        select(Annotation.id, Annotation.image_path).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    rows = result.all()

    phash_map: dict[uuid.UUID, tuple[str, int, int]] = {}
    for ann_id, image_path in rows:
        try:
            data = await get_object_bytes(settings.MINIO_BUCKET, image_path)
            variants = _phash_variants(data)
        except Exception:
            variants = None
        if variants is not None:
            ph_orig, ph_mirror = variants
            phash_map[ann_id] = (image_path, ph_orig, ph_mirror)
    return phash_map


def _min_hamming_pair(a_orig: int, a_mirror: int, b_orig: int, b_mirror: int) -> int:
    """Minimum Hamming distance across orientation variants."""
    return min(
        _hamming(a_orig, b_orig),
        _hamming(a_orig, b_mirror),
        _hamming(a_mirror, b_orig),
        _hamming(a_mirror, b_mirror),
    )


def _orientation_mixed(a_orig: int, a_mirror: int, b_orig: int, b_mirror: int) -> bool:
    """True when best match requires a mirror flip between images."""
    pairs = [
        (_hamming(a_orig, b_orig), False),
        (_hamming(a_orig, b_mirror), True),
        (_hamming(a_mirror, b_orig), True),
        (_hamming(a_mirror, b_mirror), False),
    ]
    best = min(pairs, key=lambda p: p[0])
    return best[1]


async def _phash_clusters(
    db: AsyncSession,
    dataset_pk: uuid.UUID,
    max_distance: int,
) -> list[DuplicateCluster]:
    """Greedy-cluster dataset images by pHash Hamming distance.

    ``max_distance=0`` groups exact duplicates; larger values also catch
    near-duplicates (e.g. re-encoded crops).
    """
    phash_map = await _load_phash_map(db, dataset_pk)
    if len(phash_map) < 2:
        return []

    items = list(phash_map.items())
    clusters: list[DuplicateCluster] = []
    used: set[uuid.UUID] = set()

    for i, (ann_id, (_, ph_i_orig, ph_i_mirror)) in enumerate(items):
        if ann_id in used:
            continue
        members = [ann_id]
        used.add(ann_id)
        min_sim = 1.0
        mixed = False

        for j in range(i + 1, len(items)):
            other_id, (_, ph_j_orig, ph_j_mirror) = items[j]
            if other_id in used:
                continue
            dist = _min_hamming_pair(ph_i_orig, ph_i_mirror, ph_j_orig, ph_j_mirror)
            if dist <= max_distance:
                members.append(other_id)
                used.add(other_id)
                min_sim = min(min_sim, 1.0 - dist / 64.0)
                if _orientation_mixed(ph_i_orig, ph_i_mirror, ph_j_orig, ph_j_mirror):
                    mixed = True

        if len(members) < 2:
            continue

        ann_result = await db.execute(
            select(Annotation).where(Annotation.id.in_(members))
        )
        annotations_by_id = {a.id: a for a in ann_result.scalars().all()}

        images: list[dict] = []
        for m in members:
            images.append(await _annotation_info(db, annotations_by_id[m]))

        clusters.append(
            DuplicateCluster(
                group_id=f"phash-{uuid.uuid4().hex[:12]}",
                similarity=round(min_sim, 4),
                method="phash",
                images=images,
                orientation_mixed=mixed,
            )
        )

    return clusters


async def _pass_phash_exact(
    db: AsyncSession,
    dataset_pk: uuid.UUID,
) -> list[DuplicateCluster]:
    """Exact pHash duplicates (Hamming distance = 0).

    Images are pulled from MinIO and hashed with a 64-bit DCT perceptual
    hash; identical hashes form a group.
    """
    return await _phash_clusters(db, dataset_pk, max_distance=0)


async def _pass_phash_near(
    db: AsyncSession,
    dataset_pk: uuid.UUID,
    max_distance: int = 8,
) -> list[DuplicateCluster]:
    """Near-duplicate pHash (Hamming ≤ 8).

    Same hashing pipeline as the exact pass, but pairs within
    ``max_distance`` bits are clustered together.
    """
    return await _phash_clusters(db, dataset_pk, max_distance=max_distance)


async def _pass_clip_semantic(
    db: AsyncSession,
    dataset_pk: uuid.UUID,
    threshold: float = 0.92,
) -> list[DuplicateCluster]:
    """Semantic dedup via CLIP embedding cosine similarity.

    Loads all embeddings for the dataset, builds a pairwise cosine matrix
    with numpy, and greedy-clusters with *threshold*.
    """
    result = await db.execute(
        select(
            ImageEmbedding.annotation_id,
            ImageEmbedding.embedding,
        )
        .join(Annotation, ImageEmbedding.annotation_id == Annotation.id)
        .where(Annotation.dataset_id == dataset_pk)
        .where(ImageEmbedding.embedding.isnot(None))
    )
    rows = result.all()

    if len(rows) < 2:
        return []

    annotation_ids = [row[0] for row in rows]
    vectors = np.array([row[1] for row in rows], dtype=np.float32)

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    vectors = vectors / norms

    sim_matrix = vectors @ vectors.T

    clusters: list[DuplicateCluster] = []
    used: set[int] = set()

    for i in range(len(annotation_ids)):
        if i in used:
            continue
        members = [i]
        used.add(i)

        for j in range(i + 1, len(annotation_ids)):
            if j in used:
                continue
            if sim_matrix[i, j] >= threshold:
                members.append(j)
                used.add(j)

        if len(members) < 2:
            continue

        ann_ids = [annotation_ids[m] for m in members]

        ann_result = await db.execute(
            select(Annotation).where(Annotation.id.in_(ann_ids))
        )
        annotations_by_id = {a.id: a for a in ann_result.scalars().all()}

        images: list[dict] = []
        min_sim = 1.0
        for m in members:
            ann = annotations_by_id[annotation_ids[m]]
            images.append(await _annotation_info(db, ann))
            if m != members[0]:
                min_sim = min(min_sim, float(sim_matrix[i, m]))

        clusters.append(
            DuplicateCluster(
                group_id=f"clip-{uuid.uuid4().hex[:12]}",
                similarity=round(min_sim, 4),
                method="clip_semantic",
                images=images,
            )
        )

    return clusters


async def _pass_gps_temporal(
    db: AsyncSession,
    dataset_pk: uuid.UUID,
    max_distance_m: float = 50.0,
    max_hours: float = 1.0,
) -> list[DuplicateCluster]:
    """GPS-temporal fusion: within *max_distance_m* meters and *max_hours* hours.

    Uses haversine for distance and ``IngestionBatch.created_at`` for the
    temporal component.
    """
    ann_result = await db.execute(
        select(
            Annotation.id,
            Annotation.image_path,
            Annotation.batch_id,
            Annotation.gps_lat,
            Annotation.gps_lon,
        ).where(Annotation.dataset_id == dataset_pk)
    )
    rows = ann_result.all()

    if len(rows) < 2:
        return []

    batch_ids = {r[2] for r in rows if r[2] is not None}
    batch_map: dict[uuid.UUID, IngestionBatch] = {}
    if batch_ids:
        batch_result = await db.execute(
            select(IngestionBatch).where(IngestionBatch.id.in_(batch_ids))
        )
        for b in batch_result.scalars().all():
            batch_map[b.id] = b

    entries = []
    for ann_id, image_path, batch_id, lat, lon in rows:
        batch = batch_map.get(batch_id)
        node_id = str(batch.node_id) if batch else "unknown"
        capture_dt = batch.created_at if batch else None
        entries.append(
            {
                "ann_id": ann_id,
                "image_path": image_path,
                "node_id": node_id,
                "capture_dt": capture_dt,
                "lat": lat,
                "lon": lon,
            }
        )

    clusters: list[DuplicateCluster] = []
    visited: set[uuid.UUID] = set()

    for i, e in enumerate(entries):
        if e["ann_id"] in visited:
            continue
        if e["lat"] is None or e["lon"] is None or e["capture_dt"] is None:
            continue

        group: list[dict] = [e]
        visited.add(e["ann_id"])

        for j in range(i + 1, len(entries)):
            o = entries[j]
            if o["ann_id"] in visited:
                continue
            if o["lat"] is None or o["lon"] is None or o["capture_dt"] is None:
                continue

            dist = haversine(e["lat"], e["lon"], o["lat"], o["lon"])
            time_diff = abs((e["capture_dt"] - o["capture_dt"]).total_seconds()) / 3600

            if dist <= max_distance_m and time_diff <= max_hours:
                group.append(o)
                visited.add(o["ann_id"])

        if len(group) < 2:
            continue

        images: list[dict] = []
        for g in group:
            images.append(
                {
                    "image_id": str(g["ann_id"]),
                    "image_path": g["image_path"],
                    "node_id": g["node_id"],
                    "capture_time": g["capture_dt"].isoformat() if g["capture_dt"] else None,
                    "thumbnail_url": f"/api/v1/annotations/{g['ann_id']}/thumbnail",
                }
            )

        clusters.append(
            DuplicateCluster(
                group_id=f"gps-{uuid.uuid4().hex[:12]}",
                similarity=0.85,
                method="gps_temporal",
                images=images,
            )
        )

    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PASS_MAP = {
    "phash": (_pass_phash_exact, _pass_phash_near),
    "clip": (_pass_clip_semantic,),
    "gps_temporal": (_pass_gps_temporal,),
}


async def analyze(
    db: AsyncSession,
    dataset_id: str,
    methods: list[str] | None = None,
    threshold: float = 0.92,
) -> list[DuplicateCluster]:
    """Run the 4-pass deduplication pipeline.

    Parameters
    ----------
    db : AsyncSession
        Active database session.
    dataset_id : str
        Public dataset identifier (``Dataset.dataset_id``).
    methods : list[str] | None
        Subset of ``["phash", "clip", "gps_temporal"]`` to execute.
        Defaults to all three.
    threshold : float
        Cosine-similarity threshold for the CLIP semantic pass.

    Returns
    -------
    list[DuplicateCluster]
        Clusters sorted by similarity descending.
    """
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)

    methods = methods or ["phash", "clip", "gps_temporal"]

    all_clusters: list[DuplicateCluster] = []

    for method in methods:
        pass_fns = PASS_MAP.get(method, [])
        for fn in pass_fns:
            clusters = await fn(db, dataset_pk, threshold) if fn.__code__.co_argcount == 4 else await fn(db, dataset_pk)
            all_clusters.extend(clusters)

    all_clusters.sort(key=lambda c: c.similarity, reverse=True)
    return all_clusters


async def save_groups(
    db: AsyncSession,
    dataset_id: str,
    clusters: list[DuplicateCluster],
) -> int:
    """Persist duplicate clusters as ``DuplicateGroup`` + member rows.

    Returns the number of groups saved.
    """
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    count = 0

    for cluster in clusters:
        group = DuplicateGroup(
            dataset_id=dataset_pk,
            detection_method=cluster.method,
            similarity_score=cluster.similarity,
            strategy="auto",
            status="open",
        )
        db.add(group)
        await db.flush()

        for idx, img_data in enumerate(cluster.images):
            member = DuplicateGroupMember(
                group_id=group.id,
                annotation_id=uuid.UUID(img_data["image_id"]),
                role="reference" if idx == 0 else "duplicate",
                is_kept=None,
            )
            db.add(member)

        count += 1

    await db.commit()
    return count


async def resolve_groups(
    db: AsyncSession,
    dataset_id: str,
    resolutions: dict[str, str],
) -> int:
    """Apply resolution actions to duplicate groups.

    Parameters
    ----------
    resolutions : dict[str, str]
        Mapping of ``DuplicateGroup.id`` (as string) → action.
        Supported actions:

        - ``keep_first`` – keep the first member, discard the rest.
        - ``keep_best``  – keep the member with the highest
          ``Annotation.quality_score``, discard the rest.
        - ``keep_all``   – mark every member as kept.
        - ``remove_all`` – mark every member as discarded.

    Returns the number of groups resolved.
    """
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    resolved = 0

    for group_id_str, action in resolutions.items():
        group_id = uuid.UUID(group_id_str)

        grp_result = await db.execute(
            select(DuplicateGroup).where(
                DuplicateGroup.id == group_id,
                DuplicateGroup.dataset_id == dataset_pk,
            )
        )
        group = grp_result.scalar_one_or_none()
        if group is None:
            continue

        members_result = await db.execute(
            select(DuplicateGroupMember)
            .where(DuplicateGroupMember.group_id == group_id)
            .order_by(DuplicateGroupMember.created_at.asc())
        )
        members = list(members_result.scalars().all())
        if not members:
            continue

        if action == "keep_first":
            members[0].is_kept = True
            for m in members[1:]:
                m.is_kept = False

        elif action == "keep_best":
            ann_ids = [m.annotation_id for m in members]
            score_result = await db.execute(
                select(
                    Annotation.id,
                    Annotation.quality_score,
                ).where(Annotation.id.in_(ann_ids))
            )
            score_map = {row[0]: row[1] for row in score_result.all()}
            best_id = max(
                ann_ids,
                key=lambda aid: score_map.get(aid, 0.0),
            )
            for m in members:
                m.is_kept = m.annotation_id == best_id

        elif action == "keep_all":
            for m in members:
                m.is_kept = True

        elif action == "remove_all":
            for m in members:
                m.is_kept = False

        else:
            continue

        group.status = "resolved"
        group.resolution_action = action
        resolved += 1

    await db.commit()
    return resolved
