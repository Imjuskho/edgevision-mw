from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Plaintext password")
    full_name: str = Field(..., max_length=200, description="Full name")
    organization: str | None = Field(default=None, description="Organization name")
    role: str = Field(default="ANNOTATOR", description="User role")
    jurisdiction: str | None = Field(default=None, description="ISO country code")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="Email address")
    full_name: str = Field(..., description="Full name")
    organization: str | None = Field(default=None, description="Organization")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the account is active")
    created_at: datetime = Field(..., description="Registration timestamp")


class LoginRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password")


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token TTL in seconds")


class APIKeyCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., max_length=100, description="Human-readable key name")
    scopes: list[str] = Field(default_factory=list, description="Permission scopes")
    expires_in_days: int | None = Field(default=None, description="Expiry in days (null = no expiry)")


class APIKeyCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="API key UUID")
    key_id: str = Field(..., description="Non-secret key identifier")
    name: str = Field(..., description="Key name")
    key: str = Field(..., description="Plaintext key (shown only on creation)")
    scopes: list[str] = Field(default_factory=list, description="Permission scopes")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiry timestamp")


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="API key UUID")
    key_id: str = Field(..., description="Non-secret key identifier")
    name: str = Field(..., description="Key name")
    key: str = Field(default="****(redacted)", description="Redacted key")
    scopes: list[str] = Field(default_factory=list, description="Permission scopes")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiry timestamp")
    last_used_at: datetime | None = Field(default=None, description="Last usage timestamp")
