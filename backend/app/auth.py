import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt_b64, digest_b64 = password_hash.split("$", maxsplit=1)
    salt = base64.b64decode(salt_b64.encode())
    expected_digest = base64.b64decode(digest_b64.encode())

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 120_000
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(subject: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    username = payload.get("sub")
    if not username:
        raise jwt.PyJWTError("Invalid token payload")
    return username

