"""Password hashing with scrypt; plaintext is never stored."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading

_N, _R, _P = 2 ** 14, 8, 1
_SLOTS = threading.BoundedSemaphore(4)     # scrypt needs 16 MiB each; bound concurrent hashing


def _derive(password: str, salt: bytes) -> bytes:
    with _SLOTS:
        return hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${salt.hex()}${_derive(password, salt).hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        return hmac.compare_digest(_derive(password, bytes.fromhex(salt)).hex(), expected)
    except (ValueError, TypeError):
        return False
