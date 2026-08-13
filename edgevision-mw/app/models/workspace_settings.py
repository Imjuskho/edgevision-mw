from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr

from app.core.database import Base, TimestampMixin

WORKSPACE_SETTINGS_KEY = "default"


class _SingletonDeclarative(DeclarativeBase):
    metadata = Base.metadata

    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"


class WorkspaceSettings(TimestampMixin, _SingletonDeclarative):
    """Singleton workspace operational config (feature flags, dedup defaults)."""

    singleton_key: Mapped[str] = mapped_column(String(32), primary_key=True, default=WORKSPACE_SETTINGS_KEY)
    operational_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
