"""Encryption at rest for secret values, and hashing for session tokens."""

import hashlib
import os
import secrets as pysecrets
from functools import lru_cache

from cryptography.fernet import Fernet

from . import config  # noqa: F401  (loads .env)


@lru_cache
def _fernet() -> Fernet:
    key = os.environ.get("SM_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("SM_ENCRYPTION_KEY is not set (see .env.example)")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def new_token(prefix: str = "sm") -> str:
    """A long random token for the CLI or an agent. Shown once, never stored."""
    return f"{prefix}_{pysecrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """What we store instead of the token. A DB leak doesn't leak usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
