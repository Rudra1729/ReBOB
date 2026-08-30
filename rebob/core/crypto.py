"""Encrypt/decrypt tenant secrets at rest."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("REBOB_ENCRYPTION_KEY")
    if not key:
        raise EnvironmentError(
            "REBOB_ENCRYPTION_KEY is required for storing watsonx credentials"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("failed to decrypt secret") from exc
