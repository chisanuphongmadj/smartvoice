"""Regressions from the usability pass: Thai wording, Thai time, and the pages
that used to crash or misbehave in front of a user."""

import os
import types
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from smartvoice import dashboard_common as dc
from smartvoice import db, file_manager, labels


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smartvoice.db"))
    db.init_db()
    return tmp_path


def _signed_in(at: AppTest, role: str = "Admin") -> AppTest:
    at.session_state["current_user"] = "ทดสอบ"
    at.session_state["current_user_role"] = role
    at.session_state["current_username"] = "tester"
    at.session_state["current_user_id"] = None
    return at


# ── Thai wording and time ────────────────────────────────────────────────

def test_utc_timestamps_are_shown_in_thai_time():
    assert labels.thai_time("2026-05-20T05:27:59+00:00") == "20/05/2026 12:27 น."
    # Rows written without an offset are UTC too (db._now()).
    assert labels.thai_time("2026-05-20T20:00:00") == "21/05/2026 03:00 น."
    assert labels.thai_time("2026-05-20T05:27:59+00:00", with_time=False) == "20/05/2026"
    assert labels.thai_time(datetime(2026, 5, 20, 5, 0, tzinfo=timezone.utc)) == "20/05/2026 12:00 น."


def test_plain_dates_keep_their_day():
    assert labels.thai_time("2024-06-15", with_time=False) == "15/06/2024"
    assert labels.thai_time(date(2024, 6, 15)) == "15/06/2024"


def test_odd_or_empty_timestamps_never_raise():
    assert labels.thai_time(None) == "-"
    assert labels.thai_time("", empty="ยังไม่เคยเข้า") == "ยังไม่เคยเข้า"
    assert labels.thai_time("ไม่ทราบ") == "ไม่ทราบ"


def test_codes_have_thai_words():
    assert labels.call_status("done") == "เสร็จแล้ว"
    assert labels.case_status("follow_up") == "ติดตาม"
    assert labels.sentiment("negative") == "เชิงลบ"
    assert labels.field("assignee") == "ผู้รับเคส"
    # Unknown codes fall through instead of raising.
    assert labels.call_status("weird") == "weird"


# ── Navigation ───────────────────────────────────────────────────────────

def test_sidebar_never_hides_pages_behind_view_more():
    """Streamlit folds a menu past 10 links behind "View more" — that hid
    ประวัติการใช้งาน / ตั้งค่าระบบ / จัดการผู้ใช้ from Admins."""
    home = Path("Home.py").read_text(encoding="utf-8")
    assert "expanded=True" in home


def test_every_menu_entry_has_a_matching_icon():
    import re

    home = Path("Home.py").read_text(encoding="utf-8")
    specs = re.findall(r"PAGE_\w+: dict\((.*?)\),\n", home)
    assert specs, "no page specs found"
    for spec in specs:
        assert 'icon=":material/' in spec, f"page without an icon: {spec[:60]}"


# ── Dashboard filters across pages ───────────────────────────────────────

def test_saved_filters_overwrite_what_the_previous_page_left_behind():
    """Switching Dashboard pages left the old widget value in session state;
    the restore skipped keys that were present, and the new page's dropdown
    fell back to "100 สายล่าสุด"."""
    state = {
        dc.KEY_LIMIT: "100 สายล่าสุด",                     # stale, from the old widget
        "_keep_" + dc.KEY_LIMIT: "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)",  # what the user picked
    }
    with mock.patch.object(dc, "st", types.SimpleNamespace(session_state=state)):
        dc.restore_filters()
    assert state[dc.KEY_LIMIT] == "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)"


def test_every_filter_widget_saves_on_change():
    source = Path("smartvoice/dashboard_common.py").read_text(encoding="utf-8")
    assert source.count("on_change=remember_filters") == len(dc.FILTER_KEYS)


# ── Deleting audio ───────────────────────────────────────────────────────

def test_removing_a_missing_file_is_fine(tmp_path):
    assert file_manager.remove_audio_file(str(tmp_path / "gone.wav")) is True
    assert file_manager.remove_audio_file(None) is True


def test_removing_a_locked_file_reports_instead_of_raising(tmp_path):
    audio = tmp_path / "call.wav"
    audio.write_bytes(b"RIFF")
    with mock.patch.object(file_manager.os, "remove", side_effect=PermissionError("in use")):
        assert file_manager.remove_audio_file(str(audio)) is False
    assert file_manager.remove_audio_file(str(audio)) is True
    assert not audio.exists()


def test_admin_deletes_only_after_confirmation():
    page = Path("pages/1_📤_Admin.py").read_text(encoding="utf-8")
    assert "@st.dialog(" in page
    assert "os.remove(" not in page  # goes through file_manager.remove_audio_file
    # Both delete buttons and the merge button open a dialog instead of acting.
    assert page.count("_confirm_delete_dialog(") == 3  # definition + 2 callers
    assert "_confirm_merge_dialog(case" in page


# ── Pages that used to crash ─────────────────────────────────────────────

def test_customer_search_with_no_match_shows_a_message(temp_db):
    db.insert_customer(first_name="สมชาย", last_name="ใจดี", phone="0812345678")
    at = _signed_in(AppTest.from_file("pages/3_👥_Customers.py", default_timeout=30), "Agent")
    at.run()
    at.text_input[0].input("ไม่มีชื่อนี้แน่นอน").run()

    assert not at.exception
    assert any("ไม่พบลูกค้า" in w.value for w in at.warning)


def test_customer_search_matches_first_and_last_name_together(temp_db):
    db.insert_customer(first_name="สมชาย", last_name="ใจดี", phone="0812345678")
    at = _signed_in(AppTest.from_file("pages/3_👥_Customers.py", default_timeout=30), "Agent")
    at.run()
    at.text_input[0].input("สมชาย ใจดี").run()

    assert not at.exception
    assert any("พบ 1 ราย" in c.value for c in at.caption)


def test_admin_page_survives_a_warranty_without_a_period(temp_db):
    customer_id = db.insert_customer(first_name="มาลี", last_name="ดอกไม้", phone="0899999999")
    warranty_id = db.insert_warranty("W-1", customer_id, warranty_period_months=None)
    call_id = db.insert_call("x-0899999999-Inbound.wav", "hash-x", "data/none.wav")
    db.link_call_customer(call_id, customer_id, warranty_id)

    with mock.patch("smartvoice.preflight.get_ollama_readiness", return_value=(True, "ok")):
        at = _signed_in(AppTest.from_file("pages/1_📤_Admin.py", default_timeout=30))
        at.run()

    assert not at.exception


def test_settings_page_caches_the_network_readiness_checks():
    page = Path("pages/4_Settings.py").read_text(encoding="utf-8")
    assert "@st.cache_data" in page
    assert "for check in _cached_preflight_checks():" in page
    assert "for check in run_preflight_checks():" not in page


def test_anomaly_counts_come_from_sql(temp_db):
    for i, severity in enumerate(("high", "low", "")):
        call_id = db.insert_call(f"c{i}.wav", f"h{i}", f"data/c{i}.wav")
        db.update_call_results(
            call_id=call_id, transcript="t", summary="s", sentiment="neutral", topic="อื่นๆ",
            anomaly_detected=bool(severity), anomaly_severity=severity,
        )
        db.update_call_status(call_id, "done")
    assert db.count_anomaly_calls() == {"total": 2, "high": 1}


def test_home_page_for_an_agent_shows_their_work_and_no_admin_tools(temp_db):
    at = _signed_in(AppTest.from_file("Home.py", default_timeout=30), "Agent")
    at.run()

    assert not at.exception
    assert any("งานที่รอคุณ" in h.value for h in at.subheader)
    assert not any("ตรวจความพร้อม" in e.label for e in at.expander)
    # Model names in the sidebar are for the Admin only.
    assert not any("LLM" in c.value for c in at.sidebar.caption)


def test_call_time_comes_from_the_file_name():
    name = "20251104173706-1762252614.105999-104-0819979336-Outbound.wav"
    assert file_manager.extract_call_time_from_filename(name) == datetime(2025, 11, 4, 17, 37, 6)
    assert file_manager.extract_call_time_from_filename("upload.wav") is None
    assert file_manager.extract_call_time_from_filename("20251399999999-x.wav") is None


def _scored_call(i: int, agent: str, politeness: int, problem: int) -> None:
    import json

    call_id = db.insert_call(
        f"2025110417370{i}-1.1-{agent}-081234567{i}-Outbound.wav", f"h{i}", f"data/{i}.wav"
    )
    db.update_call_results(
        call_id=call_id, transcript="t", summary="s", sentiment="neutral", topic="สอบถามการจัดส่ง",
        agent_performance=json.dumps({
            "politeness": politeness, "problem_solving": problem,
            "overall_score": politeness + problem,
            "politeness_evidence": "ทักทายเปิดสาย", "problem_solving_evidence": "ตอบคำถามครบ",
            "next_action": "โทรแจ้งลูกค้า | ภายใน 3 วัน", "next_action_owner": "Agent คนเดิม",
        }, ensure_ascii=False),
    )
    db.update_call_status(call_id, "done")


def test_agent_page_summarises_per_agent_and_keeps_quotes_out_of_the_table(temp_db):
    _scored_call(1, "104", 5, 5)
    _scored_call(2, "102", 2, 3)

    at = _signed_in(AppTest.from_file("pages/10_Agent_Performance.py", default_timeout=30), "Supervisor")
    at.run()

    assert not at.exception
    summary, calls = at.dataframe[0].value, at.dataframe[1].value
    assert list(summary["รหัสพนักงาน"]) == ["104", "102"]  # best first
    assert list(summary["สายต่ำกว่า 6"]) == [0, 1]
    # Long evidence lives in the detail panel, not in the list.
    assert "หลักฐานความสุภาพ" not in calls.columns
    assert calls.loc[0, "วันที่โทร"].startswith("04/11/2025")
    assert calls.loc[0, "สิ่งที่ต้องทำต่อ"] == "โทรแจ้งลูกค้า"
    assert any("ควรช่วยดู" in m.value for m in at.markdown)


def _click(rows=(), cells=()):
    return types.SimpleNamespace(selection={"rows": list(rows), "cells": [list(c) for c in cells]})


def test_a_click_on_any_cell_picks_its_row_and_opens_once():
    from smartvoice import ui_helpers

    state: dict = {}
    with mock.patch.object(ui_helpers, "st", types.SimpleNamespace(session_state=state)):
        # Clicking the text of a cell — not just the checkbox — picks the row.
        assert ui_helpers.picked_row(_click(cells=[(2, "สรุปสาย")]), "k") == (2, True)
        # The rerun after it must not pop the dialog open again.
        assert ui_helpers.picked_row(_click(cells=[(2, "สรุปสาย")]), "k") == (2, False)
        # Another cell (or a row, should a table select rows) is a new click.
        assert ui_helpers.picked_row(_click(cells=[(2, "หัวข้อ")]), "k") == (2, True)
        assert ui_helpers.picked_row(_click(rows=[0]), "k") == (0, True)
        # Clearing the selection resets, so the same cell opens again later.
        assert ui_helpers.picked_row(_click(), "k") == (None, False)
        assert ui_helpers.picked_row(_click(rows=[0]), "k") == (0, True)


def test_deselecting_never_reopens_the_dialog():
    """Un-ticking a row while its clicked cell stayed selected used to count as
    a new click and pop the dialog open again."""
    from smartvoice import ui_helpers

    state: dict = {}
    with mock.patch.object(ui_helpers, "st", types.SimpleNamespace(session_state=state)):
        assert ui_helpers.picked_row(_click(rows=[1], cells=[(1, "ชื่อ")]), "k") == (1, True)
        # Box un-ticked, cell still selected: a removal, not a click.
        assert ui_helpers.picked_row(_click(cells=[(1, "ชื่อ")]), "k") == (1, False)


def test_tables_have_no_checkbox_column():
    from smartvoice import ui_helpers

    # Row selection draws a checkbox per row; a click on any cell is enough.
    assert ui_helpers.TABLE_CLICK_MODES == ["single-cell"]


def test_tables_with_long_text_open_a_dialog_on_click():
    """Long summaries / evidence used to sit in narrow cells that had to be
    opened one by one; these pages show them in a dialog instead."""
    for name in ("11_Cases.py", "12_Call_Summaries.py", "10_Agent_Performance.py", "7_📜_Audit_Log.py"):
        page = (Path("pages") / name).read_text(encoding="utf-8")
        assert "selection_mode=TABLE_CLICK_MODES" in page, name
        assert "@st.dialog(" in page, name
        assert "picked_row(" in page, name


def test_transcript_text_is_escaped(monkeypatch):
    from smartvoice import ui_helpers

    shown: list[str] = []
    monkeypatch.setattr(ui_helpers.st, "markdown", lambda text, **_: shown.append(text))
    ui_helpers.render_transcript({
        "transcript": "SPEAKER_00: <b>สวัสดีค่ะ</b>",
        "speaker_mapping": '{"SPEAKER_00": "Agent"}',
    })
    assert shown and "[พนักงาน]" in shown[0]
    assert "<b>" not in shown[0] and "&lt;b&gt;" in shown[0]


def test_transcript_already_labelled_by_role_is_shown_in_thai(monkeypatch):
    from smartvoice import ui_helpers

    shown: list[str] = []
    monkeypatch.setattr(ui_helpers.st, "markdown", lambda text, **_: shown.append(text))
    ui_helpers.render_transcript({"transcript": "Agent: สวัสดีค่ะ\nCustomer: ครับ", "speaker_mapping": ""})
    assert "[พนักงาน]" in shown[0] and "[ลูกค้า]" in shown[1]


def test_temp_db_fixture_is_isolated(temp_db):
    assert os.environ["DB_PATH"].startswith(str(temp_db))
