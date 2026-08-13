from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import AppendOnlyMixin, Base


class SubjectAnnotation(AppendOnlyMixin, Base):
    __tablename__ = "subject_annotations"

    subject_hash: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
