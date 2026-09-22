import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, declared_attr

from app.core.circuit_breaker import db_circuit_breaker
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    **(
        {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_pre_ping": True,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
        if settings.DATABASE_URL.startswith("postgresql")
        else {}
    ),
)

async_session = async_sessionmaker(class_=AsyncSession, bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Adds created_at and updated_at columns. Used by all tables except append-only tables."""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class AppendOnlyMixin:
    """Adds created_at only. For immutable/append-only tables (audit_logs, consent_ledger)."""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
        nullable=False,
    )


async def get_db():
    if not db_circuit_breaker.is_available():
        raise HTTPException(
            status_code=503,
            detail="Database circuit breaker is OPEN — too many failures",
        )
    async with async_session() as session:
        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:
            db_circuit_breaker._record_failure()
            raise HTTPException(
                status_code=503,
                detail=f"Database connection failed: {exc}",
            ) from exc
        db_circuit_breaker._record_success()
        yield session


async def init_db():
    """Schema is managed exclusively by Alembic migrations."""
    return
