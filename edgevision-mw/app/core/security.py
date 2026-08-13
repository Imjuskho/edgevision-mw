import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


API_KEY_BCRYPT_ROUNDS = 12


def generate_api_key_pair() -> tuple[str, str, str]:
    """Generate an API key pair.

    Returns:
        (key_id, secret, plaintext) where plaintext = f"{key_id}.{secret}"
        and key_id is a non-secret lookup identifier.
    """
    key_id = "ak_" + secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    plaintext = f"{key_id}.{secret}"
    return key_id, secret, plaintext


def hash_api_key_bcrypt(plaintext: str) -> str:
    return _pwd_context.hash(plaintext)


def verify_api_key_bcrypt(plaintext: str, hashed: str) -> bool:
    return _pwd_context.verify(plaintext, hashed)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(48)


def verify_node_signature(
    public_key: bytes, message: bytes, signature: bytes
) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(signature, message)
        return True
    except Exception:
        return False
