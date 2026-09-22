"""One-shot repair: strip leading '/' from annotation image_path and thumbnail_path."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session
from app.models.annotation import Annotation


async def repair():
    count = 0
    async with async_session() as db:
        result = await db.execute(
            select(Annotation).where(Annotation.image_path.startswith("/") | Annotation.thumbnail_path.startswith("/"))
        )
        rows = result.scalars().all()
        for ann in rows:
            old_img = ann.image_path
            old_thumb = ann.thumbnail_path
            ann.image_path = old_img.lstrip("/")
            ann.thumbnail_path = old_thumb.lstrip("/")
            count += 1
        await db.commit()
    print(f"Repaired {count} annotations")


if __name__ == "__main__":
    asyncio.run(repair())
