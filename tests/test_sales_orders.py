"""Sales orders: Excel/CSV import, manual save, hiding, and warranty extras."""

import io
import os
import sqlite3
from datetime import date, datetime

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from smartvoice import audit, customer_entry, db, file_manager, labels, sales_orders as so


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "so.db"))
    db.init_db()
    return tmp_path


def _audit_rows():
    conn = db.get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()]
    conn.close()
    return rows


# ── Column matching ──────────────────────────────────────────────────────

def test_template_headers_map_back_to_every_field():
    df = pd.read_excel(io.BytesIO(so.template_bytes()), sheet_name="SO")
    mapping, unknown = so.map_columns(df.columns)
    assert unknown == []
    assert set(mapping.values()) == {f.key for f in so.FIELDS}


def test_template_has_no_data_rows():
    df = pd.read_excel(io.BytesIO(so.template_bytes()), sheet_name="SO")
    assert df.empty
    guide = pd.read_excel(io.BytesIO(so.template_bytes()), sheet_name="คำอธิบาย")
    assert len(guide) == len(so.FIELDS)


def test_nav_english_headers_are_recognised():
    cols = ["Document No.", "Order Date", "Sell-to Customer Name", "Ship-to Phone No.",
            "No.", "Description", "Quantity", "Unit Price Excl. VAT", "Line Amount Excl. VAT"]
    mapping, unknown = so.map_columns(cols)
    assert unknown == []
    assert mapping["Document No."] == "so_number"
    assert mapping["No."] == "item_no"          # with Document No. present, No. is the item
    assert mapping["Line Amount Excl. VAT"] == "amount"


def test_bare_no_is_the_so_number_when_there_is_no_document_no():
    mapping, _ = so.map_columns(["No.", "Order Date"])
    assert mapping["No."] == "so_number"


def test_unknown_columns_are_reported_not_fatal():
    mapping, unknown = so.map_columns(["เลขที่ SO", "สีโปรด"])
    assert mapping == {"เลขที่ SO": "so_number"}
    assert unknown == ["สีโปรด"]


# ── Value parsing ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("05/03/2026", "2026-03-05"),
    ("5/3/2569", "2026-03-05"),          # พ.ศ.
    ("2026-03-05", "2026-03-05"),
    ("๐๕/๐๓/๒๕๖๙", "2026-03-05"),
    ("05/03/69", "2026-03-05"),          # 2-digit พ.ศ.
    ("05/03/26", "2026-03-05"),          # 2-digit ค.ศ.
    (datetime(2026, 3, 5, 10, 0), "2026-03-05"),
    (date(2569, 3, 5), "2026-03-05"),    # Excel cell typed with a พ.ศ. year
    (pd.Timestamp("2026-03-05"), "2026-03-05"),
    (None, None),
    ("", None),
])
def test_parse_date(raw, expected):
    assert so.parse_date(raw) == expected


def test_parse_date_rejects_text():
    with pytest.raises(ValueError):
        so.parse_date("พรุ่งนี้")


@pytest.mark.parametrize("raw, expected", [
    ("1,234.50", 1234.5), ("฿ 990", 990.0), ("(100)", -100.0), (12, 12.0),
    ("990 บาท", 990.0), ("", None), ("-", None), (float("nan"), None),
])
def test_parse_number(raw, expected):
    assert so.parse_number(raw) == expected


def test_parse_phone_restores_the_leading_zero_excel_drops():
    assert so.parse_phone(812345678.0) == "0812345678"
    assert so.parse_phone("081-234-5678") == "0812345678"


def test_parse_text_turns_excel_floats_back_into_codes():
    assert so.parse_text(10.0) == "10"
    assert so.parse_text("  ABC ") == "ABC"


# ── Grouping rows into orders ────────────────────────────────────────────

def _frame(rows):
    return pd.DataFrame(rows)


def test_rows_with_the_same_so_number_become_one_order():
    result = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "ชื่อผู้ซื้อ": "ร้าน ก", "รายละเอียดสินค้า": "ที่นอน", "จำนวน": 1, "ราคาต่อหน่วย": 1000},
        {"เลขที่ SO": "SO-1", "ชื่อผู้ซื้อ": "ร้าน ก", "รายละเอียดสินค้า": "หมอน", "จำนวน": 2, "ราคาต่อหน่วย": 250},
        {"เลขที่ SO": "SO-2", "ชื่อผู้ซื้อ": "ร้าน ข", "รายละเอียดสินค้า": "ท็อปเปอร์", "จำนวน": 1, "ราคาต่อหน่วย": 500},
    ]))
    assert result.errors == []
    assert [h["so_number"] for h, _ in result.orders] == ["SO-1", "SO-2"]
    header, lines = result.orders[0]
    assert len(lines) == 2 and result.line_count == 3
    assert [ln["amount"] for ln in lines] == [1000, 500]
    assert header["total"] == 1500 and header["net_amount"] == 1500 and header["grand_total"] == 1500


def test_given_totals_win_over_computed_ones():
    result = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "จำนวน": 1, "ราคาต่อหน่วย": 1000, "ยอดรวม": 999,
         "ส่วนลดท้ายบิล": 99, "VAT": 63, "ยอดรวมสุทธิ": 963},
    ]))
    header, _ = result.orders[0]
    assert header["total"] == 999 and header["net_amount"] == 900
    assert header["grand_total"] == 963


def test_line_discount_is_subtracted_and_stored_as_discount():
    result = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "จำนวน": 2, "ราคาต่อหน่วย": 100, "ส่วนลด (รายการ)": 20},
    ]))
    _, lines = result.orders[0]
    assert lines[0]["discount"] == 20 and lines[0]["amount"] == 180


def test_rows_without_so_number_and_bad_values_are_reported_with_row_numbers():
    result = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "วันที่สั่งซื้อ": "ไม่รู้", "จำนวน": 1},
        {"เลขที่ SO": None, "วันที่สั่งซื้อ": None, "จำนวน": 3},
        {"เลขที่ SO": None, "วันที่สั่งซื้อ": None, "จำนวน": None},     # blank → skipped
    ]))
    assert any(e.startswith("แถว 2:") and "วันที่สั่งซื้อ" in e for e in result.errors)
    assert "แถว 3: ไม่มีเลขที่ SO" in result.errors
    assert len(result.errors) == 2


def test_conflicting_header_values_keep_the_first_and_warn():
    result = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "ชื่อผู้ซื้อ": "ร้าน ก"},
        {"เลขที่ SO": "SO-1", "ชื่อผู้ซื้อ": "ร้าน ข"},
    ]))
    assert result.orders[0][0]["sell_to_name"] == "ร้าน ก"
    assert result.warnings


def test_missing_so_column_is_one_clear_error():
    result = so.parse_import(_frame([{"ชื่อผู้ซื้อ": "ร้าน ก"}]))
    assert result.orders == [] and len(result.errors) == 1


def test_read_upload_finds_the_header_below_a_title_row():
    raw = pd.DataFrame([["รายงานใบสั่งขาย", None], ["Document No.", "Description"], ["SO-9", "ที่นอน"]])
    buffer = io.BytesIO()
    raw.to_excel(buffer, header=False, index=False)
    df = so.read_upload("export.xlsx", buffer.getvalue())
    assert list(df.columns) == ["Document No.", "Description"]
    assert so.parse_import(df).orders[0][0]["so_number"] == "SO-9"


def test_read_upload_reads_thai_windows_csv():
    data = "เลขที่ SO,รายละเอียดสินค้า\nSO-1,ที่นอน\n".encode("cp874")
    df = so.read_upload("so.csv", data)
    assert df.iloc[0]["รายละเอียดสินค้า"] == "ที่นอน"


def test_read_upload_keeps_csv_leading_zeros():
    df = so.read_upload("so.csv", "เลขที่ SO,เบอร์ผู้รับ\nSO-1,0812345678\n".encode("utf-8"))
    assert so.parse_import(df).orders[0][0]["ship_to_phone"] == "0812345678"


def test_read_upload_rejects_other_files():
    with pytest.raises(ValueError):
        so.read_upload("so.pdf", b"%PDF")


# ── Saving ───────────────────────────────────────────────────────────────

def test_import_links_customer_by_phone_and_upserts(tmp_db):
    customer_id = db.insert_customer("สมชาย", "ใจดี", phone="0811111111")
    parsed = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "เบอร์ผู้รับ": "081-111-1111", "รายละเอียดสินค้า": "ที่นอน", "จำนวน": 1, "ราคาต่อหน่วย": 100},
        {"เลขที่ SO": "SO-2", "เบอร์ผู้รับ": "0899999999", "รายละเอียดสินค้า": "หมอน", "จำนวน": 1, "ราคาต่อหน่วย": 50},
    ]))
    summary = so.import_orders(parsed.orders, actor="admin", actor_role="Admin", source="a.xlsx")
    assert summary == {"created": 2, "updated": 0, "linked": 1, "lines": 2}
    assert db.get_sales_order(so_number="SO-1")["customer_id"] == customer_id
    assert db.get_sales_order(so_number="SO-2")["customer_id"] is None

    again = so.parse_import(_frame([
        {"เลขที่ SO": "SO-1", "เบอร์ผู้รับ": "0811111111", "รายละเอียดสินค้า": "ที่นอน 6 ฟุต", "จำนวน": 1, "ราคาต่อหน่วย": 100},
    ]))
    summary = so.import_orders(again.orders, actor="admin")
    assert summary["updated"] == 1 and summary["created"] == 0
    order = db.get_sales_order(so_number="SO-1")
    assert [ln["description"] for ln in order["lines"]] == ["ที่นอน 6 ฟุต"]   # lines replaced

    entries = [r for r in _audit_rows() if r["entity"] == audit.ENTITY_SALES_ORDER]
    assert [r["action"] for r in entries] == [audit.IMPORT, audit.IMPORT]


def test_reimport_keeps_a_manual_customer_link(tmp_db):
    customer_id = db.insert_customer("สมหญิง", "ใจงาม", phone="0822222222")
    so_id, _ = so.save_manual({"so_number": "SO-5", "customer_id": customer_id}, [], actor="admin")
    parsed = so.parse_import(_frame([{"เลขที่ SO": "SO-5", "เบอร์ผู้รับ": "0800000000"}]))
    so.import_orders(parsed.orders)
    assert db.get_sales_order(so_id=so_id)["customer_id"] == customer_id


def test_save_manual_validates_and_audits(tmp_db):
    _, error = so.save_manual({"so_number": ""}, [])
    assert error
    _, error = so.save_manual({"so_number": "SO-1", "order_date": "เมื่อวาน"}, [])
    assert "วันที่สั่งซื้อ" in error

    so_id, error = so.save_manual(
        {"so_number": "SO-1", "order_date": "01/02/2569"},
        [{"description": "ที่นอน", "quantity": 1, "unit_price": 9900}, {"description": None}],
        actor="admin", actor_role="Admin",
    )
    assert error is None
    order = db.get_sales_order(so_id=so_id)
    assert order["order_date"] == "2026-02-01" and len(order["lines"]) == 1
    assert order["grand_total"] == 9900

    _, error = so.save_manual({"so_number": "SO-1"}, [], actor="admin")
    assert "มีอยู่แล้ว" in error                 # creating a duplicate number

    _, error = so.save_manual({"so_number": "SO-1", "order_date": "2026-02-01", "remark": "ส่งช่วงเช้า"},
                              [{"description": "ที่นอน", "quantity": 1, "unit_price": 9900}],
                              actor="admin", so_id=so_id)
    assert error is None
    actions = [r["action"] for r in _audit_rows() if r["entity"] == audit.ENTITY_SALES_ORDER]
    assert actions == [audit.CREATE, audit.UPDATE]


def test_saving_unchanged_order_writes_no_audit_entry(tmp_db):
    lines = [{"description": "ที่นอน", "quantity": 1, "unit_price": 100}]
    so_id, _ = so.save_manual({"so_number": "SO-1"}, lines)
    so.save_manual({"so_number": "SO-1"}, lines, so_id=so_id)
    assert len([r for r in _audit_rows() if r["entity"] == audit.ENTITY_SALES_ORDER]) == 1


def test_so_number_cannot_be_renamed(tmp_db):
    so_id, _ = so.save_manual({"so_number": "SO-1"}, [])
    _, error = so.save_manual({"so_number": "SO-X"}, [], so_id=so_id)
    assert error


def test_hide_and_restore_keep_the_row(tmp_db):
    so_id, _ = so.save_manual({"so_number": "SO-1"}, [{"description": "หมอน"}])
    assert so.hide(so_id, actor="admin") is None
    assert db.get_sales_order(so_id=so_id) is None
    assert db.get_sales_order(so_id=so_id, include_deleted=True)["lines"]
    assert db.list_sales_orders() == []
    assert so.restore(so_id, actor="admin") is None
    assert db.count_sales_orders() == 1


def test_search_matches_item_lines_and_customer_lookup(tmp_db):
    customer_id = db.insert_customer("ก", "ข", phone="0833333333")
    so.save_manual({"so_number": "SO-1", "customer_id": customer_id}, [{"item_no": "8850000000001", "description": "Omazz Grand"}])
    so.save_manual({"so_number": "SO-2"}, [{"description": "หมอน"}])
    assert [o["so_number"] for o in db.list_sales_orders(search="omazz")] == ["SO-1"]
    assert db.count_sales_orders(search="8850000000001") == 1
    grouped = db.get_sales_orders_for_customers([customer_id])
    assert [o["so_number"] for o in grouped[customer_id]] == ["SO-1"]
    assert grouped[customer_id][0]["line_count"] == 1


def test_link_customer_by_hand(tmp_db):
    customer_id = db.insert_customer("ก", "ข", phone="0844444444")
    so_id, _ = so.save_manual({"so_number": "SO-1"}, [{"description": "หมอน"}])
    assert so.link_customer(so_id, customer_id, actor="admin") is None
    order = db.get_sales_order(so_id=so_id)
    assert order["customer_id"] == customer_id and len(order["lines"]) == 1


def test_deleting_an_so_header_row_cascades_lines_schema(tmp_db):
    conn = db.get_connection()
    fks = conn.execute("PRAGMA foreign_key_list(sales_order_lines)").fetchall()
    conn.close()
    assert any(dict(fk)["table"] == "sales_orders" for fk in fks)


# ── Migration + warranty extras ──────────────────────────────────────────

def test_migration_adds_columns_to_an_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
            phone TEXT UNIQUE, created_at TEXT);
        CREATE TABLE warranty_registrations (id INTEGER PRIMARY KEY, registration_no TEXT UNIQUE,
            customer_id INTEGER, created_at TEXT);
        INSERT INTO customers VALUES (1, 'เก่า', 'เดิม', '0855555555', '2025-01-01');
        INSERT INTO warranty_registrations VALUES (1, 'W-OLD', 1, '2025-01-01');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(path))
    db.init_db()
    warranty = db.get_warranty_by_registration("W-OLD")
    assert warranty["status"] == "active" and warranty["so_number"] is None
    assert "nick_name" in db.get_customer_by_phone("0855555555")
    assert db.count_sales_orders() == 0


def test_warranty_extra_fields_round_trip(tmp_db):
    customer_id, _ = customer_entry.create_customer(
        first_name="สมชาย", last_name="ใจดี", phone="0866666666", nick_name="ชาย", channel="Omazz")
    assert db.get_customer_by_id(customer_id)["nick_name"] == "ชาย"
    warranty_id, error = customer_entry.create_warranty(
        registration_no="W-1", customer_id=customer_id, ref_id="REF-1", so_number="SO-1",
        warranty_period_months=120, date_of_purchase=date(2026, 1, 1))
    assert error is None
    row = db.get_warranty_by_id(warranty_id)
    assert (row["ref_id"], row["so_number"], row["status"]) == ("REF-1", "SO-1", "active")
    assert [w["registration_no"] for w in db.get_warranties_by_so_number("SO-1")] == ["W-1"]


def test_cancel_and_reactivate_warranty_are_audited(tmp_db):
    customer_id = db.insert_customer("ก", "ข", phone="0877777777")
    warranty_id = db.insert_warranty("W-2", customer_id)
    assert customer_entry.set_warranty_status(warranty_id, "cancelled", actor="admin") is None
    row = db.get_warranty_by_id(warranty_id)
    assert row["status"] == "cancelled" and row["cancelled_by"] == "admin"
    assert customer_entry.set_warranty_status(warranty_id, "cancelled", actor="admin")  # already
    assert customer_entry.set_warranty_status(warranty_id, "active", actor="admin") is None
    row = db.get_warranty_by_id(warranty_id)
    assert row["status"] == "active" and row["cancelled_at"] is None
    actions = [r["action"] for r in _audit_rows() if r["entity"] == audit.ENTITY_WARRANTY]
    assert actions == [audit.CANCEL, audit.REACTIVATE]


def test_warranty_status_label():
    assert labels.warranty_status(None) == labels.WARRANTY_STATUS_TH["active"]
    assert "Cancel" in labels.warranty_status("cancelled")
    assert labels.baht(1234.5) == "1,234.50" and labels.baht(None) == "-"


# ── Proof of purchase files ──────────────────────────────────────────────

def test_save_proof_file_checks_content_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(file_manager, "PROOF_DIR", str(tmp_path / "proofs"))
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    path, error = file_manager.save_proof_file(png)
    assert error is None and path.endswith(".png") and os.path.exists(path)
    assert file_manager.save_proof_file(png)[0] == path
    assert file_manager.save_proof_file(b"MZ fake exe")[1]
    assert file_manager.save_proof_file(b"")[1]
    assert file_manager.sniff_proof_type(b"%PDF-1.7") == ".pdf"


# ── Pages ────────────────────────────────────────────────────────────────

def _signed_in(at: AppTest, role: str) -> AppTest:
    at.session_state["current_user"] = "ทดสอบ"
    at.session_state["current_user_role"] = role
    at.session_state["current_username"] = "tester"
    at.session_state["current_user_id"] = None
    return at


def _seed_order():
    customer_id = db.insert_customer("สมชาย", "ใจดี", phone="0811111111", nick_name="ชาย")
    so.save_manual(
        {"so_number": "SO-100", "order_date": "2026-03-01", "ship_to_phone": "0811111111",
         "sell_to_name": "สมชาย ใจดี"},
        [{"item_no": "8850000000001", "description": "ที่นอน", "quantity": 1, "unit_price": 9900}],
    )
    warranty_id = db.insert_warranty("W-SO", customer_id, so_number="SO-100")
    db.set_warranty_status(warranty_id, "cancelled", actor="admin")
    return customer_id


@pytest.mark.parametrize("role, tabs", [("Admin", 4), ("Agent", 1), ("QA", 1)])
def test_sales_order_page_renders_for_each_role(tmp_db, role, tabs):
    _seed_order()
    at = _signed_in(AppTest.from_file("pages/13_Sales_Orders.py", default_timeout=30), role)
    at.run()
    assert not at.exception
    assert len(at.tabs) == tabs
    assert any("พบ 1 SO" in c.value for c in at.caption)


def test_sales_order_page_edit_form_saves(tmp_db):
    _seed_order()
    at = _signed_in(AppTest.from_file("pages/13_Sales_Orders.py", default_timeout=30), "Admin")
    at.run()
    at.radio(key="_so_mode").set_value("แก้ไข SO ที่มีอยู่").run()
    assert not at.exception
    order_id = db.get_sales_order(so_number="SO-100")["id"]
    at.text_area(key=f"_so_remark_{order_id}").input("โทรก่อนส่ง").run()
    at.button(key=f"_so_save_{order_id}").click().run()
    assert not at.exception
    assert db.get_sales_order(so_id=order_id)["remark"] == "โทรก่อนส่ง"
    assert len(db.get_sales_order(so_id=order_id)["lines"]) == 1


def test_customer_page_tables_are_clickable(tmp_db):
    _seed_order()
    at = _signed_in(AppTest.from_file("pages/3_👥_Customers.py", default_timeout=30), "Agent")
    at.run()
    assert not at.exception
    assert any("คลิกแถว" in c.value for c in at.caption)
    # Details live in the dialog now — no second "pick a customer" box on the page.
    assert not [s for s in at.selectbox if s.label == "เลือกลูกค้า"]


def _customer_detail_script():
    from smartvoice.customer_view import render_customer_detail

    render_customer_detail(1)     # what the customer dialog draws


def test_customer_detail_shows_nick_name_orders_and_cancelled_warranty(tmp_db):
    _seed_order()
    at = AppTest.from_function(_customer_detail_script, default_timeout=30)
    at.run()
    assert not at.exception
    assert any("ชื่อเล่น" in m.value and "ชาย" in m.value for m in at.markdown)
    assert any("SO SO-100" in e.label for e in at.expander)
    warranty_table = at.dataframe[0].value
    assert list(warranty_table["สถานะประกัน"]) == ["ยกเลิกแล้ว"]


def _missing_customer_script():
    from smartvoice.customer_view import render_customer_detail

    render_customer_detail(999)


def test_customer_detail_of_a_hidden_or_missing_customer_says_so(tmp_db):
    at = AppTest.from_function(_missing_customer_script, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.warning


def test_data_entry_page_renders_with_new_fields(tmp_db):
    _seed_order()
    at = _signed_in(AppTest.from_file("pages/6_➕_Data_Entry.py", default_timeout=30), "Admin")
    at.run()
    assert not at.exception
    assert any(t.label == "เลขที่ SO" for t in at.text_input)
    assert any("ยกเลิก (Cancel)" in m.value for m in at.markdown)


def _orders_block_script():
    from smartvoice.so_view import render_customer_orders

    render_customer_orders(1, limit=5)     # what the case dialog draws


def test_case_dialog_orders_block_renders_full_order(tmp_db):
    _seed_order()
    at = AppTest.from_function(_orders_block_script, default_timeout=30)
    at.run()
    assert not at.exception
    assert any("SO SO-100" in e.label for e in at.expander)
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "W-SO" in text and "Cancel" in text        # linked warranty with its status
    assert any("ใบสั่งขาย SO-100" in m.value for m in at.markdown)


def test_totals_follow_lines_only_when_they_were_computed(tmp_db):
    so_id, _ = so.save_manual({"so_number": "SO-1", "vat": 70},
                              [{"description": "หมอน", "quantity": 2, "unit_price": 500}])
    order = db.get_sales_order(so_id=so_id)
    assert order["grand_total"] == 1070 and so.totals_follow_lines(order)

    # Edit with auto totals: header carries no totals, so they are recomputed.
    so.save_manual({"so_number": "SO-1", "vat": 70},
                   [{"description": "หมอน", "quantity": 3, "unit_price": 500}], so_id=so_id)
    assert db.get_sales_order(so_id=so_id)["grand_total"] == 1570

    typed_id, _ = so.save_manual({"so_number": "SO-2", "total": 999},
                                 [{"description": "หมอน", "quantity": 2, "unit_price": 500}])
    assert not so.totals_follow_lines(db.get_sales_order(so_id=typed_id))
