"""Tests for PBKDF2 sidebar authentication helpers."""

from smartvoice import auth


def test_hash_password_verifies_round_trip():
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")

    assert auth.verify_password("secret-password", encoded)
    assert not auth.verify_password("wrong-password", encoded)


def test_parse_users_ignores_malformed_entries():
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")
    users = auth.parse_users(f"bad-entry;admin|Admin|{encoded}")

    assert "admin" in users
    assert users["admin"].role == "Admin"
    assert "bad-entry" not in users


def test_authenticate_uses_constant_hash_format(monkeypatch):
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")
    monkeypatch.setenv("SMARTVOICE_USERS", f"admin|Admin|{encoded}")

    assert auth.authenticate("admin", "secret-password") is not None
    assert auth.authenticate("admin", "wrong-password") is None
