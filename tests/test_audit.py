"""The shared audit trail (smartvoice.audit)."""

import sqlite3
from unittest import mock

from smartvoice import audit, auth


def test_diff_fields_reports_only_real_changes():
    changed = audit.diff_fields(
        {"role": "Agent", "is_active": True, "display_name": "สมชาย"},
        {"role": "QA", "is_active": True, "display_name": "สมชาย"},
    )
    assert changed == {"role": ["Agent", "QA"]}


def test_redact_hides_secrets_but_keeps_the_field_name():
    redacted = audit.redact(
        {"password": "hunter2", "HF_TOKEN": "hf_abc123", "role": ["Agent", "QA"]}
    )
    assert redacted["password"] == "***"
    assert redacted["HF_TOKEN"] == "***"
    assert redacted["role"] == ["Agent", "QA"]


def test_redact_passes_through_empty_changes():
    assert audit.redact(None) is None
    assert audit.redact({}) == {}


def test_record_forwards_everything_to_the_db_with_secrets_removed():
    with mock.patch.object(audit.db, "log_action", return_value=5) as log_action:
        entry_id = audit.record(
            audit.UPDATE,
            audit.ENTITY_SETTINGS,
            entity_label="Save Settings",
            actor="admin",
            actor_role="Admin",
            changes={"HF_TOKEN": "hf_secret", "WHISPER_DEVICE": ["cpu", "cuda"]},
        )

    assert entry_id == 5
    kwargs = log_action.call_args.kwargs
    assert kwargs["action"] == "update"
    assert kwargs["actor"] == "admin"
    assert kwargs["changes"]["HF_TOKEN"] == "***"
    assert kwargs["changes"]["WHISPER_DEVICE"] == ["cpu", "cuda"]


def test_record_never_raises_when_the_database_is_unavailable():
    with mock.patch.object(audit.db, "log_action", side_effect=sqlite3.OperationalError("locked")):
        # A failed log must not take the user's action down with it.
        assert audit.record(audit.CREATE, audit.ENTITY_CALL, entity_id=1) is None


def test_every_action_and_entity_has_a_thai_label():
    actions = {
        audit.CREATE, audit.UPDATE, audit.DELETE, audit.RESTORE,
        audit.LOGIN, audit.LOGIN_FAILED, audit.LOGOUT,
        audit.CLAIM, audit.RELEASE,
    }
    entities = {
        audit.ENTITY_CUSTOMER, audit.ENTITY_WARRANTY, audit.ENTITY_USER,
        audit.ENTITY_CALL, audit.ENTITY_CASE, audit.ENTITY_SESSION,
        audit.ENTITY_SETTINGS,
    }
    assert actions <= set(audit.ACTION_LABELS_TH)
    assert entities <= set(audit.ENTITY_LABELS_TH)


def test_user_edit_widgets_are_keyed_per_account():
    """Streamlit keeps a keyed widget's value across reruns and ignores `value=`,
    so a fixed key would carry the previous account's name into the next edit."""
    from pathlib import Path

    page = Path("pages/5_👤_Users.py").read_text(encoding="utf-8")

    assert 'key="_edit_display"' not in page
    assert 'key="_edit_role"' not in page
    assert 'key="_edit_active"' not in page
    assert "key=f\"_edit_display_{selected['id']}\"" in page


def test_staff_actions_are_logged_from_every_page_that_changes_data():
    from pathlib import Path

    for path in (
        "pages/1_📤_Admin.py",       # uploads, call deletes, case edits, manual links
        "pages/4_Settings.py",       # .env changes
        "pages/5_👤_Users.py",       # account management
        "smartvoice/ui_helpers.py",  # login / logout / self-service password change
        "smartvoice/customer_entry.py",
        "smartvoice/case_workflow.py",  # claim / release / status of a case
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "audit" in source, f"{path} changes data without touching the audit trail"


def test_only_admin_and_supervisor_can_read_the_audit_log():
    assert auth.can_access("Admin", auth.PAGE_AUDIT)
    assert auth.can_access("Supervisor", auth.PAGE_AUDIT)
    for role in ("QA", "Agent"):
        assert not auth.can_access(role, auth.PAGE_AUDIT)
