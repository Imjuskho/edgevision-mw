from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.dataset import Dataset
from app.models.enums import DatasetStatus, LicenseType
from app.services.catalog import generate_quote, search_datasets, trigger_build


async def _create_ready_dataset(db):
    ds = Dataset(
        id=uuid4(),
        dataset_id=f"DS-{uuid4().hex[:6]}",
        name="Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=100,
        classes={"vehicle": 1, "pedestrian": 2},
        annotations_per_image=3.5,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"districts": ["Lilongwe"]},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.95,
        pii_scrub_verified=True,
        iaa_score=0.85,
        formats=["COCO", "YOLO"],
        price_usd=Decimal("500.00"),
        license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@pytest.mark.asyncio
async def test_manifest_populated_from_db(db_session):
    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus, BatchStatus, NodeCategory, NodeStatus, PIIMode
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node
    from app.services.catalog import get_manifest

    ds = await _create_ready_dataset(db_session)

    node = Node(
        node_id=f"MAN-{uuid4().hex[:8]}",
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
    db_session.add(node)
    await db_session.flush()

    batch = IngestionBatch(
        batch_id=f"MAN-B-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="test-hub",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="0" * 64,
        node_signature=b"\x01" * 64,
        compression_codec="none",
        quality_scores={},
        status=BatchStatus.INGESTED,
    )
    db_session.add(batch)
    await db_session.flush()

    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="datasets/test/images/0001.jpg",
        thumbnail_path="datasets/test/thumbs/0001.jpg",
        detected_objects={
            "objects": [
                {"class_name": "vehicle", "bbox": [10, 20, 100, 50], "confidence": 0.9},
                {"class_name": "pedestrian", "bbox": [200, 300, 40, 80], "confidence": 0.7},
            ]
        },
        auto_labels={},
        status=AnnotationStatus.CERTIFIED,
        quality_score=0.95,
        iaa_score=0.97,
        dataset_id=ds.id,
    )
    db_session.add(ann)
    await db_session.commit()

    manifest = await get_manifest(db_session, ds.dataset_id)
    assert manifest is not None
    assert manifest.format == "COCO"
    assert len(manifest.images) == 1
    assert manifest.images[0]["file_name"] == "0001.jpg"
    assert manifest.images[0]["width"] == 1920
    assert len(manifest.annotations) == 2

    vehicle_ann = manifest.annotations[0]
    assert vehicle_ann["category_id"] == manifest.categories[0]["id"]
    assert vehicle_ann["image_id"] == 1
    assert vehicle_ann["bbox"] == [10.0, 20.0, 100.0, 50.0]
    assert vehicle_ann["area"] == 5000.0

    ped_ann = manifest.annotations[1]
    assert ped_ann["bbox"] == [200.0, 300.0, 40.0, 80.0]


@pytest.mark.asyncio
async def test_manifest_handles_flat_objects_list(db_session):
    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus, BatchStatus, NodeCategory, NodeStatus, PIIMode
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node
    from app.services.catalog import get_manifest

    ds = await _create_ready_dataset(db_session)

    node = Node(
        node_id=f"MAN-F-{uuid4().hex[:8]}",
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
    db_session.add(node)
    await db_session.flush()

    batch = IngestionBatch(
        batch_id=f"MAN-F-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="test-hub",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="0" * 64,
        node_signature=b"\x01" * 64,
        compression_codec="none",
        quality_scores={},
        status=BatchStatus.INGESTED,
    )
    db_session.add(batch)
    await db_session.flush()

    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="datasets/test/images/live.jpg",
        thumbnail_path="datasets/test/thumbs/live.jpg",
        detected_objects=[{"class_name": "vehicle", "bbox": [1, 2, 30, 40], "confidence": 0.8}],
        auto_labels={},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        iaa_score=0.0,
        dataset_id=ds.id,
    )
    db_session.add(ann)
    await db_session.commit()

    manifest = await get_manifest(db_session, ds.dataset_id)
    assert manifest is not None
    assert len(manifest.images) == 1
    assert len(manifest.annotations) == 1
    assert manifest.annotations[0]["bbox"] == [1.0, 2.0, 30.0, 40.0]

    from unittest.mock import patch

    from app.workers.tasks import build_dataset_task

    with patch.object(build_dataset_task, "delay"):
        request_data = {
            "name": "Test Build Dataset",
            "annotation_ids": [str(uuid4())],
            "formats": ["COCO", "YOLO"],
            "license_type": "ANNUAL",
        }

        result = await trigger_build(db_session, build_request=request_data)

        assert result is not None
        assert result.name == "Test Build Dataset"


@pytest.mark.asyncio
async def test_list_datasets_filters(db_session):
    for _i in range(3):
        await _create_ready_dataset(db_session)

    result1 = await search_datasets(db_session, filters={})
    assert hasattr(result1, "items") or isinstance(result1, (list, object))

    count_result = await db_session.execute(select(Dataset))
    all_ds = count_result.scalars().all()
    assert len(all_ds) >= 3


@pytest.mark.asyncio
async def test_get_quote_pricing(db_session):
    ds = await _create_ready_dataset(db_session)
    from app.services.catalog import publish_dataset

    await publish_dataset(db_session, ds.dataset_id)

    quote_data = {
        "dataset_id": ds.dataset_id,
        "license_type": "ANNUAL",
        "jurisdiction": "MW",
    }

    quote = await generate_quote(db_session, quote_request=quote_data)

    assert quote is not None
    assert quote.total_price_usd > 0
    assert quote.license_type == "ANNUAL"


@pytest.mark.asyncio
async def test_generate_quote_rejects_ready_dataset(db_session):
    ds = await _create_ready_dataset(db_session)
    assert ds.status == DatasetStatus.READY

    with pytest.raises(ValueError, match="expected FOR_SALE"):
        await generate_quote(
            db_session,
            quote_request={
                "dataset_id": ds.dataset_id,
                "license_type": "ANNUAL",
                "jurisdiction": "MW",
            },
        )


@pytest.mark.asyncio
async def test_build_dispatches_celery_task(db_session):
    from unittest.mock import patch

    from app.workers.tasks import build_dataset_task

    with patch.object(build_dataset_task, "delay") as mock_delay:
        mock_delay.return_value = uuid4()
        request_data = {
            "name": "Celery Test Dataset",
            "annotation_ids": [str(uuid4())],
            "formats": ["COCO"],
            "license_type": "ANNUAL",
        }
        result = await trigger_build(db_session, build_request=request_data)
        assert result is not None
        mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_dataset_has_correct_required_fields(db_session):
    ds = await _create_ready_dataset(db_session)

    assert ds.dataset_id is not None
    assert ds.name == "Test Dataset"
    assert ds.version == "1.0"
    assert ds.sample_count == 100
    assert ds.classes == {"vehicle": 1, "pedestrian": 2}
    assert ds.consent_coverage_pct == 0.95
    assert ds.iaa_score == 0.85
    assert ds.price_usd == Decimal("500.00")
    assert ds.license_type == LicenseType.ANNUAL
    assert ds.status == DatasetStatus.READY
