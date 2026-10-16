"""Dashboard export: CSV contents, the PDF, and the Thai line wrapper."""

import io
import json
import re
import time
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import pytest

from smartvoice import dashboard_report as dr

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
NO_SPACE = "ลูกค้าแจ้งว่าที่นอนมีกลิ่นเหม็นและมีผื่นคันหลังจากนอนไปสองคืนต้องการให้บริษัทตรวจสอบโดยเร็ว" * 3


def _call(i, **over):
    call = {
        "id": i,
        "filename": f"20260301{10 + i % 10:02d}0000-1.{i}-104-08123456{i % 100:02d}-Inbound.wav",
        "created_at": pd.Timestamp("2026-03-02 03:00:00"),
        "customer_phone": f"08123456{i % 100:02d}",
        "topic": "แจ้งปัญหาสินค้า" if i % 2 else "สอบถามการจัดส่ง",
        "topic_detail": "สปริง/ฟองน้ำยุบ" if i % 2 else None,
        "sentiment": ["positive", "neutral", "negative"][i % 3],
        "sentiment_reason": "ลูกค้าบอกว่าไม่พอใจ",
        "anomaly_detected": 0,
        "anomaly_severity": None,
        "anomaly_reason": None,
        "keywords": json.dumps(["ที่นอน", "จัดส่ง"], ensure_ascii=False),
        "brand_mentions": json.dumps(["โลตัส", "Lotus"], ensure_ascii=False),
        "platform_mentions": json.dumps(["Shopee", "โทรศัพท์"], ensure_ascii=False),
        "agent_performance": json.dumps({
            "overall_score": 7, "politeness": 4, "problem_solving": 3,
            "politeness_evidence": "", "problem_solving_evidence": "",
            "next_action": "โทรกลับลูกค้า | แจ้งวันส่ง", "next_action_owner": "ฝ่ายจัดส่ง",
        }, ensure_ascii=False),
        "transcript": "",
        "summary": "ลูกค้าโทรมาสอบถามวันส่งที่นอน",
        "case_id": None,
    }
    call.update(over)
    return call


# ── Thai line wrapping ───────────────────────────────────────────────────

def _measure(s):
    return float(len(s))      # one unit per code point is enough to test the rules


def test_wrap_prefers_spaces():
    # "ที่นอน ส่งช้า" is 13 wide, "ส่งช้า มาก" is 10: break at the space.
    assert dr.wrap_text("ที่นอน ส่งช้า มาก", 10, _measure) == ["ที่นอน", "ส่งช้า มาก"]


def test_wrap_never_starts_a_line_with_a_mark_or_following_vowel():
    lines = dr.wrap_text(NO_SPACE, 20, _measure)
    assert "".join(lines) == NO_SPACE                      # nothing lost or added
    for line in lines[1:]:
        assert unicodedata.category(line[0]) != "Mn", line
        assert line[0] not in "ะาำ", line
    for line in lines[:-1]:
        assert line[-1] not in "เแโใไ", line
    assert all(_measure(line) <= 20 for line in lines)


def test_wrap_terminates_when_one_cluster_is_wider_than_the_line():
    assert dr.wrap_text("ที่", 0.5, _measure) == ["ที่"]


def test_wrap_keeps_blank_text_as_one_line():
    assert dr.wrap_text("", 10, _measure) == [""]


# ── Numbers ──────────────────────────────────────────────────────────────

def test_report_counts_match_the_dashboard_rules():
    calls = [_call(i) for i in range(6)]
    calls[0].update(anomaly_detected=1, anomaly_severity="high", anomaly_reason="ลูกค้าขู่ฟ้อง")
    report = dr.build_report(calls, "ทุกหัวข้อ", NOW)
    assert report.total == 6
    assert dict(report.sentiment) == {"เชิงบวก": 2, "เป็นกลาง": 2, "เชิงลบ": 2}
    assert dict(report.topics) == {"แจ้งปัญหาสินค้า": 3, "สอบถามการจัดส่ง": 3}
    assert report.product_issues == [("สปริง/ฟองน้ำยุบ", 3)]
    # Brand spellings fold into one name; "phone" is never a sales channel.
    assert report.brands == [("Lotus (โลตัส)", 6)]
    assert report.platforms == [("Shopee", 6)]
    assert report.severity_counts == {"high": 1, "medium": 0, "low": 0}
    assert report.team_average == pytest.approx(7.0)
    assert list(report.agents["รหัสพนักงาน"]) == ["104"]


def test_anomalies_are_sorted_most_severe_first():
    calls = [
        _call(1, anomaly_detected=1, anomaly_severity="low"),
        _call(2, anomaly_detected=1, anomaly_severity="high"),
        _call(3, anomaly_detected=1, anomaly_severity="medium"),
    ]
    assert [c["anomaly_severity"] for c in dr.anomaly_calls(calls)] == ["high", "medium", "low"]


def test_agent_summary_of_no_calls_is_an_empty_table():
    assert dr.agent_summary([]).empty


# ── CSV ──────────────────────────────────────────────────────────────────

def test_calls_csv_opens_in_excel_with_thai_and_one_row_per_call():
    data = dr.calls_csv([_call(i) for i in range(3)])
    assert data.startswith(b"\xef\xbb\xbf")               # BOM: Excel reads Thai only with it
    frame = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", dtype=str)
    assert len(frame) == 3
    assert {"วันที่โทร", "เบอร์ลูกค้า", "อารมณ์ลูกค้า", "คะแนนพนักงาน (เต็ม 10)", "สรุปสาย"} <= set(frame.columns)
    assert frame.loc[0, "สิ่งที่ต้องทำต่อ"] == "โทรกลับลูกค้า / แจ้งวันส่ง"
    assert frame.loc[0, "ช่องทางที่พูดถึง"] == "Shopee"


def test_csv_cells_cannot_become_excel_formulas():
    data = dr.calls_csv([_call(1, summary="=HYPERLINK(\"x\")", topic="-ลบ", sentiment_reason="-")])
    frame = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert frame.loc[0, "สรุปสาย"].startswith("'=")
    assert frame.loc[0, "หัวข้อ"] == "'-ลบ"
    assert frame.loc[0, "เหตุผลของอารมณ์"] == "-"              # a lone dash is just a dash


def test_summary_csv_holds_every_section_and_the_filter():
    report = dr.build_report([_call(i) for i in range(4)], "01/03/2026 – 31/03/2026", NOW)
    frame = pd.read_csv(io.BytesIO(dr.summary_csv(report)), encoding="utf-8-sig", dtype=str)
    sections = set(frame["หมวด"])
    for name in ("ข้อมูลรายงาน", "ภาพรวม", "อารมณ์ลูกค้า", "ลูกค้าโทรมาเรื่องอะไร",
                 "แบรนด์ที่ถูกพูดถึง", "ความผิดปกติตามระดับ", "ผลงานพนักงาน"):
        assert name in sections, name
    assert "01/03/2026 – 31/03/2026" in set(frame["หมายเหตุ"].dropna())


# ── PDF ──────────────────────────────────────────────────────────────────

needs_font = pytest.mark.skipif(dr.find_thai_font() is None, reason="no Thai font on this machine")


@needs_font
def test_pdf_report_is_a_pdf_and_paginates_long_anomaly_lists():
    calls = [
        _call(i, anomaly_detected=1, anomaly_severity="high", anomaly_reason=NO_SPACE)
        for i in range(60)
    ]
    data = dr.pdf_report(dr.build_report(calls, "ทุกหัวข้อ", NOW))
    assert data.startswith(b"%PDF")
    pages = int(re.search(rb"/Count (\d+)", data).group(1))
    assert pages >= 3            # 40 rows of long Thai reasons cannot fit on 2 pages


@needs_font
def test_pdf_of_an_empty_selection_still_renders():
    assert dr.pdf_report(dr.build_report([], "", NOW)).startswith(b"%PDF")


@needs_font
def test_pdf_for_thousands_of_calls_is_quick():
    calls = [_call(i, summary=NO_SPACE) for i in range(2000)]
    start = time.perf_counter()
    dr.pdf_report(dr.build_report(calls, "", NOW))
    assert time.perf_counter() - start < 15


def test_pdf_without_a_thai_font_says_how_to_fix_it(monkeypatch):
    monkeypatch.setattr(dr, "find_thai_font", lambda: None)
    with pytest.raises(dr.ReportFontMissing, match="REPORT_FONT_PATH"):
        dr.pdf_report(dr.build_report([], "", NOW))


def test_report_font_setting_wins_and_a_bad_path_is_not_ignored(monkeypatch, tmp_path):
    font = tmp_path / "thai.ttf"
    font.write_bytes(b"x")
    monkeypatch.setattr(dr.config, "REPORT_FONT_PATH", str(font))
    assert dr.find_thai_font() == (str(font), None)
    monkeypatch.setattr(dr.config, "REPORT_FONT_PATH", str(tmp_path / "missing.ttf"))
    assert dr.find_thai_font() is None
