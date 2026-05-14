"""Small authentication helpers for the Streamlit sidebar login.

`SMARTVOICE_USERS` format:
    username|role|pbkdf2_sha256$260000$salt_hex$hash_hex

Multiple users are separated by semicolons. Keep this value in `.env`, never
in source control.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass


HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000


@dataclass(frozen=True)
class UserRecord:
    username: str
    role: str
    password_hash: str


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Return a PBKDF2-SHA256 password hash suitable for SMARTVOICE_USERS."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        DEFAULT_ITERATIONS,
    )
    return f"{HASH_ALGORITHM}${DEFAULT_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a plain password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations_raw, salt_hex, expected_hex = encoded_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def parse_users(raw: str | None = None) -> dict[str, UserRecord]:
    """Parse SMARTVOICE_USERS into a username -> UserRecord map."""
    raw = os.getenv("SMARTVOICE_USERS", "") if raw is None else raw
    users: dict[str, UserRecord] = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|", 2)]
        if len(parts) != 3:
            continue
        username, role, password_hash = parts
        if username and role and password_hash:
            users[username.lower()] = UserRecord(username, role, password_hash)
    return users


def is_auth_configured() -> bool:
    return bool(parse_users())


def authenticate(username: str, password: str) -> UserRecord | None:
    users = parse_users()
    record = users.get((username or "").strip().lower())
    if not record:
        return None
    if not verify_password(password or "", record.password_hash):
        return None
    return record
