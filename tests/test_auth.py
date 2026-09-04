"""Tests for staff authentication, role permissions, and account management."""

import os
import tempfile

import pytest

from smartvoice import auth, db


@pytest.fixture
def temp_db(monkeypatch):
    """Fresh SQLite file per test so account state never leaks between tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)
    monkeypatch.setenv("SMARTVOICE_USERS", "")
    db.init_db()
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


# ── Password hashing ─────────────────────────────────────────────────────

def test_hash_password_verifies_round_trip():
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")

    assert auth.verify_password("secret-password", encoded)
    assert not auth.verify_password("wrong-password", encoded)


def test_verify_password_rejects_garbage_hash():
    assert not auth.verify_password("secret-password", "not-a-hash")
    assert not auth.verify_password("secret-password", None)


# ── .env fallback source ─────────────────────────────────────────────────

def test_parse_users_ignores_malformed_entries():
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")
    users = auth.parse_users(f"bad-entry;admin|Admin|{encoded}")

    assert "admin" in users
    assert users["admin"].role == "Admin"
    assert "bad-entry" not in users


def test_authenticate_falls_back_to_env_users(temp_db, monkeypatch):
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")
    monkeypatch.setenv("SMARTVOICE_USERS", f"admin|Admin|{encoded}")

    record = auth.authenticate("admin", "secret-password")
    assert record is not None
    assert record.source == "env"
    assert auth.authenticate("admin", "wrong-password") is None


# ── Role permissions ─────────────────────────────────────────────────────

def test_agent_role_cannot_reach_admin_settings_or_users():
    assert not auth.can_access("Agent", auth.PAGE_ADMIN)
    assert not auth.can_access("Agent", auth.PAGE_SETTINGS)
    assert not auth.can_access("Agent", auth.PAGE_USERS)
    assert auth.can_access("Agent", auth.PAGE_DASHBOARD)
    assert auth.can_access("Agent", auth.PAGE_CUSTOMERS)


def test_qa_role_matches_agent_visibility():
    assert auth.visible_pages("QA") == auth.visible_pages("Agent")
    assert auth.PAGE_ADMIN not in auth.visible_pages("QA")


def test_admin_and_supervisor_can_reach_admin_page():
    assert auth.can_access("Admin", auth.PAGE_ADMIN)
    assert auth.can_access("Supervisor", auth.PAGE_ADMIN)
    assert auth.can_access("Admin", auth.PAGE_USERS)
    # User management is Admin-only.
    assert not auth.can_access("Supervisor", auth.PAGE_USERS)


def test_unknown_role_falls_back_to_least_privilege():
    assert auth.normalize_role("root") == "Agent"
    assert auth.normalize_role(None) == "Agent"
    assert not auth.can_access("root", auth.PAGE_ADMIN)
    # Role matching is case-insensitive so DB/.env casing cannot escalate.
    assert auth.normalize_role("admin") == "Admin"


def test_visible_pages_follows_sidebar_order():
    pages = auth.visible_pages("Admin")
    assert pages == list(auth.PAGE_ORDER)


# ── DB-backed accounts ───────────────────────────────────────────────────

def test_create_user_then_authenticate(temp_db):
    user_id, error = auth.create_user(
        "somchai.p", "staff-password", "Agent", display_name="สมชาย", confirm="staff-password"
    )
    assert error is None
    assert user_id

    record = auth.authenticate("somchai.p", "staff-password")
    assert record is not None
    assert record.role == "Agent"
    assert record.source == "db"
    assert record.user_id == user_id
    assert record.label == "สมชาย"
    assert auth.authenticate("somchai.p", "nope") is None


def test_authenticate_is_case_insensitive_on_username(temp_db):
    auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")

    assert auth.authenticate("SomChai.P", "staff-password") is not None


def test_authenticate_records_last_login(temp_db):
    user_id, _ = auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")

    assert db.get_user_by_id(user_id)["last_login_at"] is None
    auth.authenticate("somchai.p", "staff-password")
    assert db.get_user_by_id(user_id)["last_login_at"] is not None


def test_disabled_account_cannot_log_in(temp_db):
    user_id, _ = auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")
    db.update_user(user_id, is_active=False)

    assert auth.authenticate("somchai.p", "staff-password") is None


def test_db_account_takes_priority_over_env_entry(temp_db, monkeypatch):
    auth.create_user("somchai.p", "db-password", "Agent", confirm="db-password")
    encoded = auth.hash_password("env-password", salt=b"0123456789abcdef")
    monkeypatch.setenv("SMARTVOICE_USERS", f"somchai.p|Admin|{encoded}")

    assert auth.authenticate("somchai.p", "db-password").role == "Agent"
    assert auth.authenticate("somchai.p", "env-password") is None


def test_create_user_rejects_short_password_and_duplicates(temp_db):
    _, error = auth.create_user("somchai.p", "short", "Agent", confirm="short")
    assert "อย่างน้อย" in error

    _, error = auth.create_user("somchai.p", "staff-password", "Agent", confirm="mismatch")
    assert "ไม่ตรงกัน" in error

    auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")
    _, error = auth.create_user("SOMCHAI.P", "staff-password", "Agent", confirm="staff-password")
    assert error is not None


def test_create_user_rejects_invalid_username(temp_db):
    assert auth.validate_username("ab") is not None
    assert auth.validate_username("has space") is not None
    assert auth.validate_username("ok.user-1_2") is None


# ── Bootstrap admin ──────────────────────────────────────────────────────

def test_ensure_default_admin_seeds_once(temp_db):
    assert auth.ensure_default_admin() is True
    assert auth.ensure_default_admin() is False
    assert db.count_users() == 1

    record = auth.authenticate(auth.DEFAULT_ADMIN_USERNAME, auth.DEFAULT_ADMIN_PASSWORD)
    assert record is not None
    assert record.role == "Admin"
    assert auth.default_admin_password_unchanged() is True


def test_ensure_default_admin_skipped_when_env_users_configured(temp_db, monkeypatch):
    encoded = auth.hash_password("secret-password", salt=b"0123456789abcdef")
    monkeypatch.setenv("SMARTVOICE_USERS", f"admin|Admin|{encoded}")

    assert auth.ensure_default_admin() is False
    assert db.count_users() == 0


def test_default_admin_warning_clears_after_password_change(temp_db):
    auth.ensure_default_admin()
    admin = db.get_user_by_username(auth.DEFAULT_ADMIN_USERNAME)

    error = auth.change_password(
        admin["id"], auth.DEFAULT_ADMIN_PASSWORD, "brand-new-password", "brand-new-password"
    )
    assert error is None
    assert auth.default_admin_password_unchanged() is False
    assert auth.authenticate(auth.DEFAULT_ADMIN_USERNAME, "brand-new-password") is not None


# ── Password change / reset ──────────────────────────────────────────────

def test_change_password_requires_current_password(temp_db):
    user_id, _ = auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")

    assert auth.change_password(user_id, "wrong", "new-password", "new-password") is not None
    assert auth.change_password(user_id, "staff-password", "new-password", "different") is not None
    assert auth.change_password(user_id, "staff-password", "staff-password", "staff-password") is not None
    assert auth.change_password(user_id, "staff-password", "new-password", "new-password") is None


def test_change_password_unavailable_for_env_accounts(temp_db):
    error = auth.change_password(None, "whatever", "new-password", "new-password")
    assert error is not None and ".env" in error


def test_no_admin_initiated_password_reset_exists(temp_db):
    """A password belongs to its owner — an Admin can disable an account, never
    set someone else's password. The Users page has no reset form either."""
    from pathlib import Path

    assert not hasattr(auth, "reset_password")

    page = Path("pages/5_👤_Users.py").read_text(encoding="utf-8")
    assert "reset_password" not in page
    assert "_reset_password_form" not in page


def test_users_page_disables_accounts_instead_of_deleting_them(temp_db):
    """An account referenced by the audit trail must not vanish — the Admin
    lever is the enable/disable toggle, not a hard delete."""
    from pathlib import Path

    page = Path("pages/5_👤_Users.py").read_text(encoding="utf-8")
    assert "db.delete_user(" not in page
    assert "เปิดใช้งานบัญชี" in page


def test_changing_a_password_always_requires_the_current_one(temp_db):
    user_id, _ = auth.create_user("somchai.p", "staff-password", "Agent", confirm="staff-password")

    assert auth.change_password(user_id, "", "fresh-password", "fresh-password") is not None
    assert auth.change_password(user_id, "wrong", "fresh-password", "fresh-password") is not None
    assert auth.change_password(user_id, "staff-password", "fresh-password", "fresh-password") is None
    assert auth.authenticate("somchai.p", "fresh-password") is not None


# ── Last-admin protection ────────────────────────────────────────────────

def test_would_remove_last_admin_blocks_demoting_the_only_admin(temp_db):
    auth.ensure_default_admin()
    admin = db.get_user_by_username(auth.DEFAULT_ADMIN_USERNAME)

    assert auth.would_remove_last_admin(admin["id"], new_role="Agent") is True
    assert auth.would_remove_last_admin(admin["id"], new_active=False) is True
    assert auth.would_remove_last_admin(admin["id"], new_role="Admin") is False


def test_would_remove_last_admin_allows_demotion_when_another_admin_exists(temp_db):
    auth.ensure_default_admin()
    admin = db.get_user_by_username(auth.DEFAULT_ADMIN_USERNAME)
    auth.create_user("second.admin", "admin-password", "Admin", confirm="admin-password")

    assert auth.would_remove_last_admin(admin["id"], new_role="Agent") is False


def test_would_remove_last_admin_ignores_disabled_admins(temp_db):
    auth.ensure_default_admin()
    admin = db.get_user_by_username(auth.DEFAULT_ADMIN_USERNAME)
    other_id, _ = auth.create_user("second.admin", "admin-password", "Admin", confirm="admin-password")
    db.update_user(other_id, is_active=False)

    assert auth.would_remove_last_admin(admin["id"], new_active=False) is True
