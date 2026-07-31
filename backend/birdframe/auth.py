"""Password hashing and API key helpers for BirdFrame accounts."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets


def hash_password(password: str, *, n: int = 2**14, r: int = 8, p: int = 1) -> str:
    """Hash a password with scrypt and a random per-user salt."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${base64.b64encode(salt).decode('ascii')}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a scrypt password hash."""
    try:
        _scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def generate_api_key() -> str:
    """Return a new opaque API key; only the hash is persisted."""
    return "bf_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def api_key_prefix(key: str) -> str:
    """Short stable identifier for displaying a key without exposing it."""
    return key[:12]
