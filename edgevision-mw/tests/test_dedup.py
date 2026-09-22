from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from PIL import Image

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import (
    AnnotationStatus,
    BatchStatus,
    DatasetStatus,
    LicenseType,
    NodeCategory,
    NodeStatus,
    PIIMode,
)
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.services.dedup import _pass_phash_exact, _pass_phash_near


def _png_bytes(color: int) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(color, color, color)).save(buf, format="PNG")
    return buf.getvalue()


def _noise_png_bytes(seed: int) -> bytes:
    import io

    import numpy as np

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


async def _create_dataset(db):
    ds = Dataset(
        dataset_id=f"DEDUP-{uuid4().hex[:8]}",
        name="Dedup Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=2,
        classes={"vehicle": 1},
        annotations_per_image=1.0,
        image_width=64,
        image_height=64,
        geographic_coverage={},
        demographic_report={},
        consent_coverage_pct=1.0,
        pii_scrub_verified=True,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _create_annotations(db, ds, image_paths):
    node = Node(
        node_id=f"DEDUP-N-{uuid4().hex[:8]}",
        district="Lilongwe",
        latitude=-13.96,
        longitude=33.77,
        category=NodeCategory.ROAD,
        hardware_profile={},
        network_config={},
        capture_schedule="daily_1200",
        interest_classes=["vehicle"],
        pii_mode=PIIMode.NONE,
        firmware_version="1.0.0",
        public_key=b"\x00" * 32,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()

    batch = IngestionBatch(
        batch_id=f"DEDUP-B-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="test-hub",
        event_count=len(image_paths),
        file_size_bytes=1024,
        checksum_sha256="0" * 64,
        node_signature=b"\x01" * 64,
        compression_codec="none",
        quality_scores={},
        status=BatchStatus.INGESTED,
    )
    db.add(batch)
    await db.flush()

    anns = []
    for idx, path in enumerate(image_paths):
        ann = Annotation(
            batch_id=batch.id,
            image_index=idx,
            image_path=path,
            thumbnail_path=path,
            detected_objects={},
            auto_labels={},
            status=AnnotationStatus.PENDING,
            quality_score=0.8,
            iaa_score=0.8,
            dataset_id=ds.id,
        )
        db.add(ann)
        anns.append(ann)
    await db.commit()
    for ann in anns:
        await db.refresh(ann)
    return anns


@pytest.mark.asyncio
async def test_pass_phash_exact_groups_identical_images(db_session):
    ds = await _create_dataset(db_session)
    anns = await _create_annotations(db_session, ds, ["dedup/a.jpg", "dedup/b.jpg"])
    payload = _png_bytes(120)

    async def _fake_get(*_args, **_kwargs):
        return payload

    with patch("app.core.minio_helper.get_object_bytes", new=_fake_get):
        clusters = await _pass_phash_exact(db_session, ds.id)

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.method == "phash"
    assert cluster.similarity == 1.0
    assert {img["image_id"] for img in cluster.images} == {
        str(anns[0].id),
        str(anns[1].id),
    }


@pytest.mark.asyncio
async def test_pass_phash_exact_distinguishes_different_images(db_session):
    ds = await _create_dataset(db_session)
    await _create_annotations(db_session, ds, ["dedup/a.jpg", "dedup/b.jpg"])
    payload_a = _noise_png_bytes(1)
    payload_b = _noise_png_bytes(2)

    async def _fake_get(_bucket, key):
        return payload_b if key.endswith("b.jpg") else payload_a

    with patch("app.core.minio_helper.get_object_bytes", new=_fake_get):
        clusters = await _pass_phash_exact(db_session, ds.id)

    assert clusters == []


@pytest.mark.asyncio
async def test_pass_phash_near_groups_identical_images(db_session):
    ds = await _create_dataset(db_session)
    anns = await _create_annotations(db_session, ds, ["dedup/a.jpg", "dedup/b.jpg"])
    payload = _png_bytes(120)

    async def _fake_get(*_args, **_kwargs):
        return payload

    with patch("app.core.minio_helper.get_object_bytes", new=_fake_get):
        clusters = await _pass_phash_near(db_session, ds.id)

    assert len(clusters) == 1
    assert {img["image_id"] for img in clusters[0].images} == {
        str(anns[0].id),
        str(anns[1].id),
    }


@pytest.mark.asyncio
async def test_phash_cluster_orientation_mixed_flag(db_session):
    ds = await _create_dataset(db_session)
    await _create_annotations(db_session, ds, ["dedup/a.jpg", "dedup/b.jpg"])
    payload = _png_bytes(120)

    async def _fake_get(*_args, **_kwargs):
        return payload

    with patch("app.core.minio_helper.get_object_bytes", new=_fake_get):
        clusters = await _pass_phash_exact(db_session, ds.id)

    assert len(clusters) == 1
    assert hasattr(clusters[0], "orientation_mixed")


def test_mirror_phash_is_bit_reversal():
    from app.services.dedup import _mirror_phash

    original = 0b1010
    mirrored = _mirror_phash(original)
    assert mirrored != original
    assert _mirror_phash(mirrored) == original


def test_min_hamming_pair_considers_mirror():
    from app.services.dedup import _min_hamming_pair, _mirror_phash

    a_orig, a_mirror = 0, _mirror_phash(0)
    b_orig, b_mirror = 1, _mirror_phash(1)
    dist = _min_hamming_pair(a_orig, a_mirror, b_orig, b_mirror)
    assert dist >= 0


@pytest.mark.asyncio
async def test_phash_skips_missing_objects(db_session):
    ds = await _create_dataset(db_session)
    await _create_annotations(db_session, ds, ["dedup/a.jpg", "dedup/b.jpg"])

    def _raise(*_args, **_kwargs):
        raise OSError("object not found")

    with patch("app.core.minio_helper.get_object_bytes", new=_raise):
        clusters = await _pass_phash_exact(db_session, ds.id)

    assert clusters == []
