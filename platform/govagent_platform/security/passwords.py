"""Password hashing for platform identities. bcrypt only; no default token."""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
