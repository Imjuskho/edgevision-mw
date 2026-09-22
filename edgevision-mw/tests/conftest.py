import os
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Force localhost for local test runs (overrides .env file's Docker hostnames)
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!!"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "edgevision")
os.environ.setdefault("POSTGRES_PASSWORD", "edgevision_secret")
os.environ.setdefault("POSTGRES_DB", "edgevision_mw")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.enums import NodeCategory, NodeStatus, PIIMode
from app.models.node import Node


async def _create_node(db: AsyncSession, status: NodeStatus = NodeStatus.ONLINE, *, node_id: str | None = None, district: str = "Blantyre") -> Node:
    node = Node(
        id=uuid4(),
        node_id=node_id or f"NODE-{uuid4().hex[:8]}",
        district=district,
        latitude=-15.7861,
        longitude=35.0058,
        category=NodeCategory.ROAD,
        hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"},
        capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"],
        pii_mode=PIIMode.STRICT,
        firmware_version="1.0.0",
        public_key=b"\x01" * 32,
        status=status,
        is_enabled=True,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


def _make_test_engine():
    return create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test DB session wrapped in an outer transaction that always rolls back."""
    engine = _make_test_engine()
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory():
    engine = _make_test_engine()
    factory = async_sessionmaker(class_=AsyncSession, bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _build_test_client(
    db_session: AsyncSession,
    *,
    bypass_rate_limits: bool = True,
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    class _AlwaysAllowed:
        async def is_allowed(self, key: str) -> tuple[bool, int]:
            return True, 0

    from app.main import app as _app

    app = _app
    app.dependency_overrides[get_db] = override_get_db

    if bypass_rate_limits:
        from app.core.rate_limiter import get_login_rate_limit, get_register_rate_limit

        app.dependency_overrides[get_login_rate_limit] = _override_login_rate_limit
        app.dependency_overrides[get_register_rate_limit] = _override_register_rate_limit

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _override_login_rate_limit():
    class _AlwaysAllowed:
        async def is_allowed(self, key: str) -> tuple[bool, int]:
            return True, 0

    return _AlwaysAllowed()


async def _override_register_rate_limit():
    class _AlwaysAllowed:
        async def is_allowed(self, key: str) -> tuple[bool, int]:
            return True, 0

    return _AlwaysAllowed()


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async for client in _build_test_client(db_session, bypass_rate_limits=True):
        yield client


@pytest_asyncio.fixture
async def rate_limit_client(db_session: AsyncSession, _flush_rate_limit_redis) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with real Redis-backed rate limits (for rate-limit tests only)."""
    async for client in _build_test_client(db_session, bypass_rate_limits=False):
        yield client


@pytest.fixture
def mock_minio():
    client = MagicMock()
    client.bucket_exists.return_value = True
    client.put_object.return_value = None
    return client


@pytest.fixture
def jwt_token_factory():
    """Mint JWT tokens. Tests that hit FK-protected endpoints must create a User row first."""

    def _factory(
        role: str = "ANNOTATOR",
        user_id: str | None = None,
        email: str | None = None,
    ) -> str:
        uid = user_id or str(uuid4())
        mail = email or f"test-{uid[:8]}@example.com"
        return create_access_token(data={"sub": uid, "role": role, "email": mail})

    return _factory


@pytest.fixture
def api_key_factory():
    from app.core.security import generate_api_key, hash_api_key

    def _factory() -> tuple[str, str]:
        raw = generate_api_key()
        hashed = hash_api_key(raw)
        return raw, hashed

    return _factory


async def _flush_rate_limit_redis_keys() -> None:
    try:
        from app.core.dependencies import _redis_client

        if _redis_client is None:
            return
        async for key in _redis_client.scan_iter(match="register:*"):
            await _redis_client.delete(key)
        async for key in _redis_client.scan_iter(match="login:*"):
            await _redis_client.delete(key)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Reset in-memory rate limiter state between tests."""
    from app.core.rate_limit import _mem_store

    _mem_store.clear()
    yield
    _mem_store.clear()


@pytest_asyncio.fixture(autouse=True)
async def _reset_app_db_engine():
    """Drop pooled asyncpg connections so the next test's event loop gets a fresh pool."""
    yield
    from app.core.database import engine

    await engine.dispose()


@pytest_asyncio.fixture
async def _flush_rate_limit_redis():
    """Optional: flush Redis rate-limit keys (used by rate_limit_client tests)."""
    await _flush_rate_limit_redis_keys()
    yield
    await _flush_rate_limit_redis_keys()


@pytest.fixture
def node_keypair_factory():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    def _factory():
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return private_key, public_key

    return _factory
