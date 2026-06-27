"""Symmetric encryption for credentials stored at rest (D2).

Fernet key is derived from APP_SECRET_KEY so we don't introduce a second secret to
manage. If APP_SECRET_KEY changes, previously-encrypted values become undecryptable
(decrypt() returns "") — which is the safe failure: the resolver then falls back to
the global .env credential rather than using a wrong value.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = hashlib.sha256((settings.app_secret_key or "change-me").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str | None) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ""
