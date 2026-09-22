from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    generate_api_key_pair,
    hash_api_key_bcrypt,
    hash_password,
    verify_api_key_bcrypt,
    verify_password,
)
from app.models.buyer import BuyerApiKey, User


async def create_user(db: AsyncSession, user_data: dict) -> User:
    existing = await db.execute(select(User).where(User.email == user_data["email"]))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Email already registered")

    user = User(
        id=uuid4(),
        email=user_data["email"],
        hashed_password=hash_password(user_data["password"]),
        full_name=user_data["full_name"],
        organization=user_data.get("organization"),
        role=user_data.get("role", "ANNOTATOR"),
        jurisdiction=user_data.get("jurisdiction"),
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


async def create_api_key(db: AsyncSession, user_id: UUID, key_data: dict) -> tuple[str, BuyerApiKey]:
    key_id, _secret, plaintext = generate_api_key_pair()
    key_hash = hash_api_key_bcrypt(plaintext)

    expires_at = None
    if key_data.get("expires_in_days"):
        expires_at = datetime.now(UTC) + timedelta(days=key_data["expires_in_days"])

    api_key = BuyerApiKey(
        id=uuid4(),
        user_id=user_id,
        key_id=key_id,
        key_hash=key_hash,
        name=key_data["name"],
        scopes=key_data.get("scopes", []),
        is_active=True,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return plaintext, api_key


async def verify_api_key(db: AsyncSession, plaintext: str) -> User | None:
    if "." not in plaintext:
        return None

    key_id = plaintext.split(".")[0]
    result = await db.execute(
        select(BuyerApiKey).where(
            BuyerApiKey.key_id == key_id,
            BuyerApiKey.is_active == True,  # noqa: E712
        )
    )
    api_key_obj = result.scalar_one_or_none()
    if api_key_obj is None:
        return None

    if not verify_api_key_bcrypt(plaintext, api_key_obj.key_hash):
        return None

    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(UTC):
        return None

    api_key_obj.last_used_at = datetime.now(UTC)
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == api_key_obj.user_id))
    return user_result.scalar_one_or_none()
