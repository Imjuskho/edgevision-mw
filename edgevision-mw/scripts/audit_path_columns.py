#!/usr/bin/env python3
"""Audit every text/varchar column that might contain a MinIO key or filesystem path.

Usage:
    python scripts/audit_path_columns.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import async_session

SUSPECT_COLUMNS = [
    ("annotations", "image_path"),
    ("annotations", "thumbnail_path"),
    ("image_records", "storage_key"),
    ("image_records", "thumbnail_key"),
    ("training_jobs", "artifact_path"),
    ("deployed_models", "artifact_path"),
    ("ingestion_batches", "storage_path"),
    ("export_jobs", "output_path"),
    ("image_embeddings", "image_path"),
]


async def audit():
    async with async_session() as db:
        for table, column in SUSPECT_COLUMNS:
            result = await db.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE '/%' OR {column} LIKE ' /%'"
                )
            )
            count = result.scalar()
            if count and count > 0:
                print(f"CRITICAL: {table}.{column} has {count} rows with leading slash")
                samples = await db.execute(
                    text(
                        f"SELECT id, {column} FROM {table} WHERE {column} LIKE '/%' LIMIT 5"
                    )
                )
                for row in samples:
                    print(f"  {row.id}: {row._mapping[column]}")
            else:
                print(f"OK: {table}.{column}")


if __name__ == "__main__":
    asyncio.run(audit())
