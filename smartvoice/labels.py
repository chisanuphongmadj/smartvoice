"""Thai wording and Thai-time formatting shared by every page.

The database stores codes (`done`, `follow_up`, `negative`) and UTC ISO
timestamps. Staff read Thai and live in UTC+7, so everything shown on screen
goes through here — one word per code, the same on every page. Kept free of
Streamlit imports so it stays unit-testable.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

CALL_STATUS_TH = {
    "uploaded": "รอประมวลผล",
    "processing": "กำลังประมวลผล",
    "done": "เสร็จแล้ว",
    "error": "ผิดพลาด",
}

CASE_STATUS_TH = {"open": "เปิด", "follow_up": "ติดตาม", "closed": "ปิด"}

SENTIMENT_TH = {"positive": "เชิงบวก", "neutral": "เป็นกลาง", "negative": "เชิงลบ"}

SEVERITY_TH = {"high": "รุนแรง", "medium": "ปานกลาง", "low": "เล็กน้อย"}

# Field names that show up in audit-log "changes" and would otherwise be
# printed as raw column names.
FIELD_TH = {
    "status": "สถานะ",
    "subject": "หัวข้อ",
    "assignee": "ผู้รับเคส",
    "role": "บทบาท",
    "is_active": "เปิดใช้งาน",
    "display_name": "ชื่อที่แสดง",
    "password": "รหัสผ่าน",
    "first_name": "ชื่อ",
    "last_name": "นามสกุล",
    "phone": "เบอร์โทร",
    "email": "อีเมล",
    "gender": "เพศ",
    "date_of_birth": "วันเกิด",
    "address": "ที่อยู่",
    "subdistrict": "แขวง/ตำบล",
    "district": "เขต/อำเภอ",
    "city_province": "จังหวัด",
    "postcode": "รหัสไปรษณีย์",
    "registration_no": "เลขทะเบียน",
    "certificate_no": "เลขใบรับประกัน",
    "brand": "แบรนด์",
    "model": "รุ่น",
    "size": "ขนาด",
    "serial_no": "Serial",
    "date_of_purchase": "วันที่ซื้อ",
    "expiry_date": "วันหมดประกัน",
    "warranty_period_months": "ระยะประกัน (เดือน)",
    "customer_id": "ลูกค้า",
    "file_hash": "รหัสไฟล์",
    "size_mb": "ขนาดไฟล์ (MB)",
    "linked_customer_id": "เชื่อมลูกค้า",
    "linked_warranty_id": "เชื่อมทะเบียน",
    "merged_into_case_id": "รวมเข้าเคส",
    "moved_calls": "ย้ายสาย",
    "bulk": "ลบหลายไฟล์พร้อมกัน",
    "source": "ที่มาของบัญชี",
    "locked": "ถูกล็อก",
    "nick_name": "ชื่อเล่น",
    "channel": "ช่องทาง",
    "ref_id": "Ref Id",
    "so_number": "เลขที่ SO",
    "proof_path": "หลักฐานการซื้อ",
    "order_number": "เลขที่คำสั่งซื้อ",
    "purchase_channel": "ช่องทางที่ซื้อ",
    "date_of_delivery": "วันที่ส่งมอบ",
    "label_no": "Label No.",
    "sku": "SKU",
    "category": "ประเภทสินค้า",
    "remark": "หมายเหตุ",
    "country": "ประเทศ",
    "order_date": "วันที่สั่งซื้อ",
    "document_date": "วันที่เอกสาร",
    "shipment_date": "วันที่จัดส่ง",
    "promised_delivery_date": "วันที่สัญญาส่ง",
    "due_date": "วันครบกำหนด",
    "sell_to_name": "ชื่อผู้ซื้อ",
    "ship_to_name": "ชื่อผู้รับ",
    "ship_to_phone": "เบอร์ผู้รับ",
    "grand_total": "ยอดรวมสุทธิ",
    "lines": "รายการสินค้า",
    "created": "เพิ่มใหม่",
    "updated": "อัปเดต",
    "skipped": "ข้าม",
    "file": "ไฟล์",
}

WARRANTY_STATUS_TH = {"active": "ใช้งาน (Active)", "cancelled": "ยกเลิก (Cancel)"}

_BANGKOK = timezone(timedelta(hours=7))


def _parse(ts) -> datetime | None:
    if isinstance(ts, datetime):
        parsed = ts
    elif isinstance(ts, date):
        return datetime(ts.year, ts.month, ts.day)
    else:
        text = str(ts or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        # Every timestamp the app writes is UTC (db._now()).
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_BANGKOK)


def thai_time(ts, with_time: bool = True, empty: str = "-") -> str:
    """'2026-05-20T05:27:59+00:00' → '20/05/2026 12:27 น.' in Thai time (UTC+7).

    Text that isn't a timestamp is returned unchanged rather than raising, so
    an odd legacy value never takes a page down.
    """
    if ts is None or (isinstance(ts, str) and not ts.strip()):
        return empty
    parsed = _parse(ts)
    if parsed is None:
        return str(ts)
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return parsed.strftime("%d/%m/%Y")
    return parsed.strftime("%d/%m/%Y %H:%M น." if with_time else "%d/%m/%Y")


def call_status(code: str | None) -> str:
    return CALL_STATUS_TH.get(code or "", code or "-")


def case_status(code: str | None) -> str:
    return CASE_STATUS_TH.get(code or "", code or "-")


def sentiment(code: str | None) -> str:
    return SENTIMENT_TH.get(code or "", "-")


def severity(code: str | None) -> str:
    return SEVERITY_TH.get(code or "", "ไม่ระบุ")


def warranty_status(code: str | None) -> str:
    """Rows from before the status column existed are active."""
    return WARRANTY_STATUS_TH.get(code or "active", code or "-")


def baht(amount, empty: str = "-") -> str:
    """1234.5 → '1,234.50' (amounts are shown like the SO document)."""
    if amount is None or amount == "":
        return empty
    try:
        return f"{float(amount):,.2f}"
    except (TypeError, ValueError):
        return str(amount)


def field(name: str) -> str:
    return FIELD_TH.get(name, name)
