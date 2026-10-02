"""Case ownership: claim, release, status — and the Discord message it sends."""

import sqlite3
from unittest import mock

import pytest
import requests

from smartvoice import audit, case_workflow, db, discord_notify
from smartvoice.case_workflow import Actor

PLOY = Actor(username="ploy", name="พลอย", role="Agent")
MINT = Actor(username="mint", name="มิ้นท์", role="Agent")
BOSS = Actor(username="boss", name="หัวหน้า", role="Supervisor")
QA = Actor(username="qa1", name="คิวเอ", role="QA")


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smartvoice.db"))
    db.init_db()


@pytest.fixture
def sent(monkeypatch):
    """Capture Discord payloads instead of posting them."""
    payloads: list[dict] = []
    monkeypatch.setattr(
        case_workflow.discord_notify, "send", lambda payload, background=True: payloads.append(payload)
    )
    return payloads


@pytest.fixture
def case_id(temp_db):
    customer_id = db.insert_customer(first_name="สุภาพร", last_name="จันทร์แก้ว", phone="0819979336")
    return db.create_case(customer_id, "แจ้งปัญหาสินค้า")


def _audit_rows():
    return db.get_audit_log(entity=audit.ENTITY_CASE, limit=50)


# ── Database layer ───────────────────────────────────────────────────────

def test_migration_adds_owner_columns_to_an_old_cases_table(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE cases (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
           subject TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
           created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    conn.execute("INSERT INTO cases (subject, created_at, updated_at) VALUES ('เดิม', 'x', 'x')")
    conn.commit()
    conn.close()

    monkeypatch.setenv("DB_PATH", str(path))
    db.init_db()

    row = db.get_case_by_id(1)
    assert row["subject"] == "เดิม"
    for col in ("assignee_username", "assignee_name", "assigned_at", "closed_by", "closed_at"):
        assert col in row and row[col] is None


def test_only_the_first_claim_wins(case_id):
    assert db.claim_case(case_id, "ploy", "พลอย") is True
    assert db.claim_case(case_id, "mint", "มิ้นท์") is False
    assert db.get_case_by_id(case_id)["assignee_username"] == "ploy"


def test_a_closed_case_cannot_be_claimed(case_id):
    db.update_case_status(case_id, "closed")
    assert db.claim_case(case_id, "ploy", "พลอย") is False


def test_status_update_is_refused_for_anyone_but_the_owner(case_id):
    db.claim_case(case_id, "ploy", "พลอย")
    assert db.set_case_status_as_assignee(case_id, "closed", "mint", "มิ้นท์") is False
    assert db.get_case_by_id(case_id)["status"] == "open"

    # Usernames are case-insensitive, like the users table.
    assert db.set_case_status_as_assignee(case_id, "closed", "PLOY", "พลอย") is True
    row = db.get_case_by_id(case_id)
    assert (row["status"], row["closed_by"]) == ("closed", "พลอย")
    assert row["closed_at"]


def test_reopening_clears_closed_by(case_id):
    db.claim_case(case_id, "ploy", "พลอย")
    db.set_case_status_as_assignee(case_id, "closed", "ploy", "พลอย")
    db.set_case_status_as_assignee(case_id, "open", "ploy", "พลอย")
    row = db.get_case_by_id(case_id)
    assert (row["status"], row["closed_by"], row["closed_at"]) == ("open", None, None)


def test_release_only_clears_the_expected_owner(case_id):
    db.claim_case(case_id, "ploy", "พลอย")
    assert db.release_case(case_id, "mint") is False
    assert db.release_case(case_id, "ploy") is True
    assert db.get_case_by_id(case_id)["assignee_username"] is None


def test_case_filters_by_owner_and_unassigned_counts(case_id):
    other = db.create_case(db.get_case_by_id(case_id)["customer_id"], "สอบถามการจัดส่ง")
    closed = db.create_case(db.get_case_by_id(case_id)["customer_id"], "ปิดแล้ว", status="closed")
    db.claim_case(case_id, "ploy", "พลอย")

    assert [c["id"] for c in db.get_all_cases(assignee="PLOY")] == [case_id]
    assert {c["id"] for c in db.get_all_cases(unassigned=True)} == {other, closed}
    assert db.count_cases(assignee="ploy") == 1
    assert db.count_cases(search="พลอย") == 1
    # A closed case is not waiting for anyone.
    assert db.get_case_counts()["unassigned"] == 1


# ── Rules ────────────────────────────────────────────────────────────────

def test_claim_records_audit_and_notifies_discord(case_id, sent):
    ok, _ = case_workflow.claim(case_id, PLOY)

    assert ok
    assert db.get_case_by_id(case_id)["assignee_name"] == "พลอย"
    entry = _audit_rows()[0]
    assert (entry["action"], entry["actor"], entry["entity_id"]) == (audit.CLAIM, "พลอย", case_id)
    assert len(sent) == 1
    embed = sent[0]["embeds"][0]
    assert "รับเคส" in embed["title"] and f"#{case_id}" in embed["title"]
    assert "พลอย" in embed["description"]


def test_nobody_can_take_a_claimed_case(case_id, sent):
    case_workflow.claim(case_id, PLOY)

    ok, message = case_workflow.claim(case_id, MINT)
    assert not ok and "พลอย" in message
    ok, message = case_workflow.claim(case_id, BOSS)
    assert not ok
    assert db.get_case_by_id(case_id)["assignee_username"] == "ploy"
    assert len(sent) == 1


def test_claim_lost_to_a_race_reports_the_winner(case_id, sent):
    # The page read the case as free, but someone else got there first.
    stale = db.get_case_detail(case_id)
    db.claim_case(case_id, "mint", "มิ้นท์")
    with mock.patch.object(case_workflow.db, "get_case_detail", side_effect=[stale, db.get_case_detail(case_id)]):
        ok, message = case_workflow.claim(case_id, PLOY)
    assert not ok and "มิ้นท์" in message
    assert sent == []


def test_qa_cannot_claim(case_id, sent):
    ok, _ = case_workflow.claim(case_id, QA)
    assert not ok
    assert db.get_case_by_id(case_id)["assignee_username"] is None


def test_status_needs_a_claim_and_the_owner(case_id, sent):
    ok, message = case_workflow.change_status(case_id, "closed", PLOY)
    assert not ok and "รับเคสก่อน" in message

    case_workflow.claim(case_id, PLOY)
    for outsider in (MINT, BOSS):
        ok, _ = case_workflow.change_status(case_id, "closed", outsider)
        assert not ok
    assert db.get_case_by_id(case_id)["status"] == "open"


def test_owner_closes_and_discord_hears_about_it(case_id, sent):
    case_workflow.claim(case_id, PLOY)
    ok, _ = case_workflow.change_status(case_id, "closed", PLOY)

    assert ok
    assert "ปิดเคส" in sent[-1]["embeds"][0]["title"]
    entry = _audit_rows()[0]
    assert entry["action"] == audit.UPDATE
    assert entry["changes"] == {"status": ["open", "closed"]}


def test_reopen_is_announced_as_reopen(case_id, sent):
    case_workflow.claim(case_id, PLOY)
    case_workflow.change_status(case_id, "closed", PLOY)
    case_workflow.change_status(case_id, "open", PLOY)
    assert "เปิดเคสอีกครั้ง" in sent[-1]["embeds"][0]["title"]


def test_owner_or_supervisor_can_release_but_not_another_agent(case_id, sent):
    case_workflow.claim(case_id, PLOY)

    ok, _ = case_workflow.release(case_id, MINT)
    assert not ok

    ok, _ = case_workflow.release(case_id, BOSS)
    assert ok
    assert db.get_case_by_id(case_id)["assignee_username"] is None
    assert "พลอย" in sent[-1]["embeds"][0]["description"]
    assert _audit_rows()[0]["action"] == audit.RELEASE

    # Releasing frees the case — it does not hand it to the supervisor.
    ok, _ = case_workflow.claim(case_id, MINT)
    assert ok


def test_a_closed_case_cannot_be_released(case_id, sent):
    case_workflow.claim(case_id, PLOY)
    case_workflow.change_status(case_id, "closed", PLOY)
    ok, _ = case_workflow.release(case_id, BOSS)
    assert not ok
    assert db.get_case_by_id(case_id)["closed_by"] == "พลอย"


# ── Discord ──────────────────────────────────────────────────────────────

def test_payload_never_pings_and_hides_most_of_the_phone():
    case = {
        "id": 63, "subject": "@everyone แจ้งปัญหา", "status": "open",
        "first_name": "สุภาพร", "last_name": "จันทร์แก้ว", "phone": "0819979336",
        "assignee_name": "พลอย", "call_count": 2,
    }
    payload = discord_notify.build_case_payload(discord_notify.EVENT_CLAIM, case, "พลอย", "Agent")

    assert payload["allowed_mentions"] == {"parse": []}
    text = str(payload)
    assert "0819979336" not in text
    assert "xxxxxx9336" in text


@pytest.mark.parametrize(
    "url, valid",
    [
        ("https://discord.com/api/webhooks/123/abc", True),
        ("https://discordapp.com/api/webhooks/123/abc", True),
        ("https://discord.com/api/webhooks/", False),
        ("http://discord.com/api/webhooks/123/abc", False),
        ("https://evil.example/api/webhooks/123/abc", False),
        ("", False),
    ],
)
def test_webhook_url_validation(url, valid):
    assert discord_notify.is_valid_webhook_url(url) is valid


def test_send_does_nothing_without_a_webhook(monkeypatch):
    monkeypatch.delenv(discord_notify.ENV_KEY, raising=False)
    with mock.patch.object(discord_notify.requests, "post") as post:
        assert discord_notify.send({"content": "x"}, background=False) is False
    post.assert_not_called()


def test_send_posts_to_the_saved_webhook(monkeypatch):
    url = "https://discord.com/api/webhooks/1/token"
    monkeypatch.setenv(discord_notify.ENV_KEY, url)
    with mock.patch.object(discord_notify.requests, "post", return_value=mock.Mock(status_code=204)) as post:
        assert discord_notify.send({"content": "x"}, background=False) is True
    assert post.call_args.args[0] == url
    assert post.call_args.kwargs["timeout"] == discord_notify.TIMEOUT_SECONDS


def test_post_never_raises_when_discord_is_down():
    with mock.patch.object(discord_notify.requests, "post", side_effect=requests.ConnectionError()):
        ok, detail = discord_notify.post({"content": "x"}, url="https://discord.com/api/webhooks/1/t")
    assert not ok and "ConnectionError" in detail


def test_post_reports_http_errors():
    with mock.patch.object(discord_notify.requests, "post", return_value=mock.Mock(status_code=404)):
        ok, detail = discord_notify.post({"content": "x"}, url="https://discord.com/api/webhooks/1/t")
    assert not ok and "404" in detail


def test_webhook_url_never_reaches_the_audit_log():
    redacted = audit.redact({"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/t"})
    assert redacted == {"DISCORD_WEBHOOK_URL": "***"}
