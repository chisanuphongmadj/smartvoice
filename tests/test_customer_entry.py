"""Rules behind the Admin data-entry page (pages/6_➕_Data_Entry.py)."""

from datetime import date
from unittest import mock

import pytest

from smartvoice import auth, customer_entry


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    """Capture audit rows instead of writing them to the real database."""
    entries: list[dict] = []

    def _capture(**kwargs):
        entries.append(kwargs)
        return len(entries)

    monkeypatch.setattr(customer_entry.db, "log_action", _capture)
    return entries


# ── Phone normalisation ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("081-234-5678", "0812345678"),
        (" 081 234 5678 ", "0812345678"),
        ("(02) 123-4567", "021234567"),
        ("๐๘๑๒๓๔๕๖๗๘", "0812345678"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_phone_strips_formatting_and_thai_digits(raw, expected):
    assert customer_entry.normalize_phone(raw) == expected


# ── Customer validation ──────────────────────────────────────────────────

def test_validate_customer_requires_first_and_last_name():
    assert customer_entry.validate_customer("", "ใจดี", None)
    assert customer_entry.validate_customer("สมชาย", "   ", None)


def test_validate_customer_accepts_a_blank_phone():
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=None):
        assert customer_entry.validate_customer("สมชาย", "ใจดี", "") is None


def test_validate_customer_rejects_a_malformed_phone():
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=None):
        error = customer_entry.validate_customer("สมชาย", "ใจดี", "12345")
    assert error and "0" in error


def test_validate_customer_rejects_a_duplicate_phone():
    existing = {"id": 7, "first_name": "มาลี", "last_name": "ดอกไม้"}
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=existing):
        error = customer_entry.validate_customer("สมชาย", "ใจดี", "081-234-5678")
    assert error and "มาลี" in error


def test_create_customer_saves_the_normalized_phone():
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=None):
        with mock.patch.object(customer_entry.db, "insert_customer", return_value=42) as insert:
            new_id, error = customer_entry.create_customer(
                first_name=" สมชาย ",
                last_name="ใจดี",
                phone="081-234-5678",
                email="",
                date_of_birth=date(1990, 5, 4),
            )

    assert (new_id, error) == (42, None)
    kwargs = insert.call_args.kwargs
    assert kwargs["first_name"] == "สมชาย"
    assert kwargs["phone"] == "0812345678"
    assert kwargs["email"] is None  # blanks become NULL, not ""
    assert kwargs["date_of_birth"] == "1990-05-04"
    assert kwargs["country"] == "Thailand"


# ── Warranty expiry maths ────────────────────────────────────────────────

def test_add_months_clamps_to_the_last_day_of_the_target_month():
    assert customer_entry.add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert customer_entry.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_compute_expiry_date_matches_the_seeded_10_year_convention():
    assert customer_entry.compute_expiry_date("2024-06-15", 120) == "2034-06-15"
    assert customer_entry.compute_expiry_date(date(2025, 3, 1), 24) == "2027-03-01"


def test_compute_expiry_date_needs_both_a_date_and_a_period():
    assert customer_entry.compute_expiry_date(None, 120) is None
    assert customer_entry.compute_expiry_date("2024-06-15", 0) is None
    assert customer_entry.compute_expiry_date("not-a-date", 12) is None


# ── Warranty validation ──────────────────────────────────────────────────

def test_validate_warranty_requires_registration_no_and_customer():
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=None):
        assert customer_entry.validate_warranty("", 1)
        assert customer_entry.validate_warranty("W011OZ25011", None)
        assert customer_entry.validate_warranty("W011OZ25011", 1) is None


def test_validate_warranty_rejects_a_duplicate_registration_no():
    with mock.patch.object(
        customer_entry.db, "get_warranty_by_registration", return_value={"id": 3}
    ):
        error = customer_entry.validate_warranty("W001OZ25001", 1)
    assert error and "W001OZ25001" in error


def test_create_warranty_fills_in_the_expiry_date_when_left_blank():
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=None):
        with mock.patch.object(customer_entry.db, "insert_warranty", return_value=11) as insert:
            new_id, error = customer_entry.create_warranty(
                registration_no="W011OZ25011",
                customer_id=5,
                brand="Omazz",
                warranty_period_months=120,
                date_of_purchase=date(2025, 6, 15),
                expiry_date=None,
                remark="",
            )

    assert (new_id, error) == (11, None)
    kwargs = insert.call_args.kwargs
    assert kwargs["customer_id"] == 5
    assert kwargs["date_of_purchase"] == "2025-06-15"
    assert kwargs["expiry_date"] == "2035-06-15"
    assert kwargs["remark"] is None


def test_create_warranty_keeps_a_manually_entered_expiry_date():
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=None):
        with mock.patch.object(customer_entry.db, "insert_warranty", return_value=12) as insert:
            customer_entry.create_warranty(
                registration_no="W012OZ25012",
                customer_id=5,
                warranty_period_months=120,
                date_of_purchase=date(2025, 6, 15),
                expiry_date=date(2030, 1, 1),
            )

    assert insert.call_args.kwargs["expiry_date"] == "2030-01-01"


def test_create_warranty_refuses_to_insert_when_validation_fails():
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=None):
        with mock.patch.object(customer_entry.db, "insert_warranty") as insert:
            new_id, error = customer_entry.create_warranty(
                registration_no="W013OZ25013", customer_id=None
            )

    assert new_id is None and error
    insert.assert_not_called()


# ── Editing ──────────────────────────────────────────────────────────────

def test_validate_customer_allows_a_row_to_keep_its_own_phone():
    itself = {"id": 7, "first_name": "มาลี", "last_name": "ดอกไม้"}
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=itself):
        assert customer_entry.validate_customer("มาลี", "ดอกไม้", "0812345600", exclude_id=7) is None
        # …but another customer's phone is still a duplicate.
        assert customer_entry.validate_customer("มาลี", "ดอกไม้", "0812345600", exclude_id=9)


def test_validate_warranty_allows_a_row_to_keep_its_own_registration_no():
    itself = {"id": 3}
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=itself):
        assert customer_entry.validate_warranty("W001OZ25001", 1, exclude_id=3) is None
        assert customer_entry.validate_warranty("W001OZ25001", 1, exclude_id=4)


def test_update_customer_normalizes_before_saving():
    row = {"id": 7, "first_name": "มาลี", "last_name": "ดอกไม้"}
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=row):
        with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=row):
            with mock.patch.object(customer_entry.db, "update_customer") as update:
                error = customer_entry.update_customer(
                    7, first_name="มาลี", last_name="ดอกไม้", phone="081-234-5600", email=""
                )

    assert error is None
    assert update.call_args.kwargs["phone"] == "0812345600"
    assert update.call_args.kwargs["email"] is None


def test_update_customer_reports_a_row_that_disappeared():
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=None):
        with mock.patch.object(customer_entry.db, "update_customer") as update:
            error = customer_entry.update_customer(7, first_name="ก", last_name="ข")

    assert error
    update.assert_not_called()


def test_update_warranty_recomputes_expiry_when_asked():
    with mock.patch.object(customer_entry.db, "get_warranty_by_id", return_value={"id": 3}):
        with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value={"id": 3}):
            with mock.patch.object(customer_entry.db, "update_warranty") as update:
                error = customer_entry.update_warranty(
                    3,
                    registration_no="W001OZ25001",
                    customer_id=5,
                    warranty_period_months=24,
                    date_of_purchase=date(2025, 3, 1),
                    expiry_date=None,
                )

    assert error is None
    assert update.call_args.kwargs["expiry_date"] == "2027-03-01"


# ── Hiding & restoring ───────────────────────────────────────────────────

def test_hide_customer_soft_deletes_and_records_who_did_it(audit):
    hidden = {"customer": 1, "warranties": 2, "deleted_at": "2026-09-04T10:00:00+00:00"}
    row = {"id": 7, "first_name": "มาลี", "last_name": "ดอกไม้"}
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=row):
        with mock.patch.object(customer_entry.db, "count_customer_dependencies",
                               return_value={"warranties": 2, "calls": 3, "cases": 1}):
            with mock.patch.object(customer_entry.db, "soft_delete_customer",
                                   return_value=hidden) as soft_delete:
                result, error = customer_entry.hide_customer(7, actor="admin", actor_role="Admin")

    assert (result, error) == (hidden, None)
    assert soft_delete.call_args.kwargs["actor"] == "admin"
    assert audit[-1]["action"] == "delete"
    assert audit[-1]["actor"] == "admin"
    assert audit[-1]["entity_label"] == "มาลี ดอกไม้"


def test_hide_customer_reports_a_row_already_hidden():
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=None):
        with mock.patch.object(customer_entry.db, "soft_delete_customer") as soft_delete:
            result, error = customer_entry.hide_customer(7)

    assert error
    soft_delete.assert_not_called()


def test_restore_customer_logs_the_restore(audit):
    row = {"id": 7, "first_name": "มาลี", "last_name": "ดอกไม้", "deleted_at": "..."}
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=row):
        with mock.patch.object(customer_entry.db, "restore_customer",
                               return_value={"customer": 1, "warranties": 2}):
            result, error = customer_entry.restore_customer(7, actor="admin", actor_role="Admin")

    assert error is None and result["warranties"] == 2
    assert audit[-1]["action"] == "restore"
    assert audit[-1]["changes"] == {"restored_warranties": 2}


def test_restore_warranty_refuses_while_its_customer_is_still_hidden():
    row = {"id": 3, "registration_no": "W001OZ25001", "customer_id": 7}
    with mock.patch.object(customer_entry.db, "get_warranty_by_id", return_value=row):
        with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=None):
            with mock.patch.object(customer_entry.db, "restore_warranty") as restore:
                error = customer_entry.restore_warranty(3)

    assert error and "ลูกค้า" in error
    restore.assert_not_called()


def test_hide_warranty_reports_a_row_that_disappeared():
    with mock.patch.object(customer_entry.db, "get_warranty_by_id", return_value=None):
        with mock.patch.object(customer_entry.db, "soft_delete_warranty") as soft_delete:
            error = customer_entry.hide_warranty(3)

    assert error
    soft_delete.assert_not_called()


def test_a_hidden_phone_points_the_user_at_restore_instead_of_a_duplicate_error():
    hidden = {
        "id": 7, "first_name": "มาลี", "last_name": "ดอกไม้",
        "deleted_at": "2026-09-04T10:00:00+00:00",
    }
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=hidden):
        error = customer_entry.validate_customer("สมชาย", "ใจดี", "0812345600")

    assert error and "ซ่อน" in error and "กู้คืน" in error


def test_a_hidden_registration_no_points_the_user_at_restore():
    hidden = {"id": 3, "deleted_at": "2026-09-04T10:00:00+00:00"}
    with mock.patch.object(customer_entry.db, "get_warranty_by_registration", return_value=hidden):
        error = customer_entry.validate_warranty("W001OZ25001", 5)

    assert error and "ซ่อน" in error and "กู้คืน" in error


def test_describe_dependencies_lists_only_what_exists():
    assert customer_entry.describe_dependencies({"warranties": 0, "calls": 0, "cases": 0}) == ""
    text = customer_entry.describe_dependencies({"warranties": 1, "calls": 0, "cases": 2})
    assert "1" in text and "2" in text and "การเชื่อมสาย" not in text


# ── Audit trail ──────────────────────────────────────────────────────────

def test_create_customer_writes_an_audit_entry(audit):
    with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=None):
        with mock.patch.object(customer_entry.db, "insert_customer", return_value=42):
            customer_entry.create_customer(
                actor="admin", actor_role="Admin",
                first_name="สมชาย", last_name="ใจดี", phone="0812345678",
            )

    entry = audit[-1]
    assert entry["action"] == "create"
    assert entry["entity"] == customer_entry.ENTITY_CUSTOMER
    assert entry["entity_id"] == 42
    assert entry["changes"]["phone"] == "0812345678"


def test_update_customer_logs_only_the_fields_that_changed(audit):
    before = {
        "id": 7, "first_name": "มาลี", "last_name": "ดอกไม้", "phone": "0812345600",
        "email": None, "country": "Thailand",
    }
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=before):
        with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=before):
            with mock.patch.object(customer_entry.db, "update_customer"):
                customer_entry.update_customer(
                    7, actor="admin", actor_role="Admin",
                    first_name="มาลี", last_name="ทองดี", phone="0812345600",
                )

    assert audit[-1]["changes"] == {"last_name": ["ดอกไม้", "ทองดี"]}


def test_an_update_that_changes_nothing_is_not_logged(audit):
    before = {
        "id": 7, "first_name": "มาลี", "last_name": "ดอกไม้", "phone": "0812345600",
        "country": "Thailand",
    }
    with mock.patch.object(customer_entry.db, "get_customer_by_id", return_value=before):
        with mock.patch.object(customer_entry.db, "get_customer_by_phone", return_value=before):
            with mock.patch.object(customer_entry.db, "update_customer") as update:
                error = customer_entry.update_customer(
                    7, first_name="มาลี", last_name="ดอกไม้", phone="0812345600",
                )

    assert error is None
    update.assert_not_called()
    assert audit == []


def test_diff_fields_reports_only_real_changes():
    changed = customer_entry.diff_fields(
        {"a": 1, "b": "x", "c": None},
        {"a": 1, "b": "y", "c": None, "d": "new"},
    )
    assert changed == {"b": ["x", "y"], "d": [None, "new"]}


# ── Permissions ──────────────────────────────────────────────────────────

def test_only_admin_can_open_the_data_entry_page():
    assert auth.can_access("Admin", auth.PAGE_DATA_ENTRY)
    for role in ("Supervisor", "QA", "Agent"):
        assert not auth.can_access(role, auth.PAGE_DATA_ENTRY)
