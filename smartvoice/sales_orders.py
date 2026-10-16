"""Sales orders (SO) — import from Excel/CSV, manual save, hide/restore.

The company keeps its sales orders in Dynamics NAV; the printed "ใบสั่งขาย"
shows what one SO holds: a header (dates, sales type, salesperson, sell-to and
ship-to parties, totals) and item lines. SmartVoice stores a copy so staff on a
call can see what the customer bought and when it ships.

Import format: **one row per item line**; the header columns repeat on every
row of the same SO number. Columns are matched by name — our own Thai template
(`template_bytes()`) or the English field names of a NAV export — so the column
order does not matter and unknown columns are ignored (and reported).

Kept free of Streamlit imports so every rule stays unit-testable.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from smartvoice import audit, db
from smartvoice.customer_entry import normalize_phone

ENTITY = audit.ENTITY_SALES_ORDER

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_SO_NUMBER_RE = re.compile(r"^[A-Za-z0-9._/-]{2,}$")


@dataclass(frozen=True)
class Field:
    key: str            # column in sales_orders / sales_order_lines
    label: str          # Thai header in our template
    level: str          # "header" or "line"
    kind: str = "text"  # text | date | number | phone
    aliases: tuple = ()  # other accepted headers (NAV export names, short forms)
    note: str = ""      # shown on the template's instructions sheet


# Order = column order of the template. Line fields that clash with a header
# column name in the DB carry a "line_" prefix here.
FIELDS: tuple[Field, ...] = (
    Field("so_number", "เลขที่ SO", "header", aliases=("SO", "SO No.", "SO Number", "Sales Order No.", "Document No.", "Order No.", "เลขที่ใบสั่งขาย"), note="จำเป็น — แถวที่เลขเดียวกันคือ SO เดียวกัน"),
    Field("document_date", "วันที่เอกสาร", "header", "date", ("Date", "Document Date", "วันที่")),
    Field("order_date", "วันที่สั่งซื้อ", "header", "date", ("Order Date",)),
    Field("shipment_date", "วันที่จัดส่ง", "header", "date", ("Shipment Date",)),
    Field("promised_delivery_date", "วันที่สัญญาส่ง", "header", "date", ("Promised Delivery Date",)),
    Field("due_date", "วันครบกำหนด", "header", "date", ("Due Date",)),
    Field("currency", "สกุลเงิน", "header", aliases=("Currency", "Currency Code")),
    Field("sales_type", "ประเภทการขาย", "header", aliases=("Sales Type",)),
    Field("purchasing_type", "ประเภทการซื้อ", "header", aliases=("Purchasing Type", "Purchasing Code")),
    Field("salesperson", "พนักงานขาย", "header", aliases=("Salesperson", "Salesperson Code")),
    Field("external_doc", "เลขที่เอกสารภายนอก", "header", aliases=("External Doc", "External Document No.", "External Doc.")),
    Field("credit_term", "เครดิต", "header", aliases=("Credit Term", "Payment Terms Code", "Payment Terms")),
    Field("customer_po_no", "เลขที่ PO ลูกค้า", "header", aliases=("Customer PO No.", "Customer PO", "Your Reference")),
    Field("sell_to_no", "รหัสผู้ซื้อ", "header", aliases=("Sell-to Customer No.", "Sell-to No.", "Customer No.")),
    Field("sell_to_name", "ชื่อผู้ซื้อ", "header", aliases=("Sell-to Customer Name", "Sell-to Name", "Customer Name")),
    Field("sell_to_address", "ที่อยู่ผู้ซื้อ", "header", aliases=("Sell-to Address",)),
    Field("sell_to_contact", "ผู้ติดต่อ (ผู้ซื้อ)", "header", aliases=("Sell-to Contact",)),
    Field("sell_to_phone", "เบอร์ผู้ซื้อ", "header", "phone", ("Sell-to Phone No.", "Sell-to Phone")),
    Field("ship_to_name", "ชื่อผู้รับ", "header", aliases=("Ship-to Name",)),
    Field("ship_to_address", "ที่อยู่ผู้รับ", "header", aliases=("Ship-to Address",)),
    Field("ship_to_contact", "ผู้ติดต่อ (ผู้รับ)", "header", aliases=("Ship-to Contact",)),
    Field("ship_to_phone", "เบอร์ผู้รับ", "header", "phone", ("Ship-to Phone No.", "Ship-to Phone"), note="ใช้จับคู่กับลูกค้าในระบบ (ถ้าว่างจะใช้เบอร์ผู้ซื้อ)"),
    Field("ship_to_email", "อีเมลผู้รับ", "header", aliases=("Ship-to E-Mail", "Ship-to Email")),
    Field("line_no", "ลำดับ", "line", "number", ("Line No.", "No. (Line)")),
    Field("item_no", "รหัสสินค้า/บาร์โค้ด", "line", aliases=("Item No.", "Item", "Barcode", "บาร์โค้ด", "รหัสสินค้า")),
    Field("description", "รายละเอียดสินค้า", "line", aliases=("Description", "รายการ", "สินค้า")),
    Field("requested_delivery_date", "วันที่ต้องการรับ", "line", "date", ("Requested Delivery Date",)),
    Field("uom", "หน่วย", "line", aliases=("UOM", "Unit of Measure", "Unit of Measure Code")),
    Field("location", "คลัง/สถานที่", "line", aliases=("Location", "Location Code")),
    Field("quantity", "จำนวน", "line", "number", ("Quantity", "Qty", "Qty.")),
    Field("unit_price", "ราคาต่อหน่วย", "line", "number", ("Unit Price", "Unit Price Excl. VAT", "Unit Price Incl. VAT")),
    Field("line_discount", "ส่วนลด (รายการ)", "line", "number", ("Line Discount", "Line Discount Amount"), note="เป็นจำนวนเงิน ไม่ใช่ %"),
    Field("amount", "จำนวนเงิน", "line", "number", ("Amount", "Line Amount", "Line Amount Excl. VAT"), note="ถ้าว่างจะคำนวณ จำนวน × ราคา − ส่วนลด"),
    Field("total", "ยอดรวม", "header", "number", ("Total", "Total Amount", "Total Excl. VAT", "Subtotal"), note="ถ้าว่างจะรวมจากจำนวนเงินทุกรายการ"),
    Field("discount", "ส่วนลดท้ายบิล", "header", "number", ("Discount", "Invoice Discount Amount", "Invoice Discount")),
    Field("net_amount", "ยอดหลังหักส่วนลด", "header", "number", ("Net Amount", "Total Amount Excl. VAT")),
    Field("vat", "VAT", "header", "number", ("VAT Amount", "Total VAT", "ภาษีมูลค่าเพิ่ม")),
    Field("grand_total", "ยอดรวมสุทธิ", "header", "number", ("Grand Total", "Total Amount Incl. VAT", "Amount Including VAT")),
    Field("remark", "หมายเหตุ", "header", aliases=("Remark", "Remarks", "Note", "Comment")),
)
FIELDS_BY_KEY = {f.key: f for f in FIELDS}
HEADER_KEYS = tuple(f.key for f in FIELDS if f.level == "header")
LINE_KEYS = tuple(f.key for f in FIELDS if f.level == "line")


def _norm_header(text) -> str:
    """'Sell-to Customer No.' / 'sell to customer no' / 'ชื่อผู้ซื้อ *' → one key."""
    return re.sub(r"[\s._\-*:()/#]", "", str(text or "").strip().lower())


_ALIAS_TO_KEY: dict[str, str] = {}
for _f in FIELDS:
    for _name in (_f.label, _f.key, *_f.aliases):
        _ALIAS_TO_KEY.setdefault(_norm_header(_name), _f.key)
# NAV exports call both the SO number (header) and the item number (line) "No.";
# which one it is depends on whether "Document No." is also present.
_BARE_NO = _norm_header("No.")


def map_columns(columns) -> tuple[dict, list[str]]:
    """{original column: field key} plus the columns we don't know."""
    normalized = {col: _norm_header(col) for col in columns}
    has_document_no = any(_ALIAS_TO_KEY.get(n) == "so_number" for n in normalized.values())
    mapping, unknown, taken = {}, [], set()
    for col, norm in normalized.items():
        key = _ALIAS_TO_KEY.get(norm)
        if norm == _BARE_NO:
            key = "item_no" if has_document_no else "so_number"
        if key and key not in taken:
            mapping[col] = key
            taken.add(key)
        elif str(col).strip() and not str(col).startswith("Unnamed"):
            unknown.append(str(col))
    return mapping, unknown


# ── Value parsing ────────────────────────────────────────────────────────

def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def parse_text(value) -> str | None:
    if _is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))      # Excel turns codes like 10 into 10.0
    return str(value).strip()


def parse_phone(value) -> str | None:
    text = parse_text(value)
    if not text:
        return None
    phone = normalize_phone(text)
    # Excel stores 0812345678 as the number 812345678.
    if phone.isdigit() and len(phone) in (8, 9) and not phone.startswith("0"):
        phone = "0" + phone
    return phone


def parse_number(value) -> float | None:
    """'1,234.50' / '฿ 990' / '(100)' / 1234 → float. Raises ValueError otherwise."""
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).translate(_THAI_DIGITS).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[,\s฿()]|บาท|THB", "", text, flags=re.IGNORECASE)
    if text in ("", "-"):
        return None
    number = float(text)
    return -number if negative else number


def _fix_year(year: int) -> int:
    if year > 2400:             # Buddhist era (พ.ศ.)
        return year - 543
    if year < 100:              # two digits: 68 → พ.ศ. 2568, 25 → ค.ศ. 2025
        return year + 2500 - 543 if year > 40 else year + 2000
    return year


def parse_date(value) -> str | None:
    """Excel dates, 'dd/mm/yyyy' (also พ.ศ.), 'yyyy-mm-dd' → ISO date.

    Raises ValueError for text that is not a date.
    """
    if _is_blank(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        value = value.date() if not isinstance(value, pd.Timestamp) else value.to_pydatetime().date()
    if isinstance(value, date):
        return date(_fix_year(value.year), value.month, value.day).isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial day number (1900 date system) left as a plain number.
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(value))).date().isoformat()
    text = str(value).translate(_THAI_DIGITS).strip().split(" ")[0].split("T")[0]
    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        y, m, d = (int(g) for g in match.groups())
    else:
        match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", text)
        if not match:
            raise ValueError(text)
        d, m, y = (int(g) for g in match.groups())
    return date(_fix_year(y), m, d).isoformat()


_PARSERS = {"text": parse_text, "phone": parse_phone, "number": parse_number, "date": parse_date}
_KIND_HINT = {"number": "ตัวเลข", "date": "วันที่ (วว/ดด/ปปปป)"}


# ── Import ───────────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    orders: list[tuple[dict, list[dict]]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return sum(len(lines) for _, lines in self.orders)


def complete_totals(header: dict, lines: list[dict]) -> None:
    """Fill amounts the file left blank, the way the SO document adds them up.

    Values given in the file always win; only blanks are computed.
    """
    for line in lines:
        if line.get("amount") is None and line.get("quantity") is not None and line.get("unit_price") is not None:
            line["amount"] = round(line["quantity"] * line["unit_price"] - (line.get("discount") or 0), 2)
    amounts = [ln["amount"] for ln in lines if ln.get("amount") is not None]
    if header.get("total") is None and amounts:
        header["total"] = round(sum(amounts), 2)
    if header.get("net_amount") is None and header.get("total") is not None:
        header["net_amount"] = round(header["total"] - (header.get("discount") or 0), 2)
    if header.get("grand_total") is None and header.get("net_amount") is not None:
        header["grand_total"] = round(header["net_amount"] + (header.get("vat") or 0), 2)


_COMPUTED_TOTALS = ("total", "net_amount", "grand_total")


def totals_follow_lines(order: dict) -> bool:
    """True when the stored totals are exactly what the lines add up to.

    The edit form then keeps them computed, so changing a line updates them;
    totals typed in (or imported) that differ stay as they are.
    """
    header = {k: order.get(k) for k in ("discount", "vat")}
    lines = [dict(ln, amount=ln.get("amount")) for ln in order.get("lines") or []]
    complete_totals(header, lines)
    return all(
        (order.get(k) is None) == (header.get(k) is None)
        and (order.get(k) is None or abs(order[k] - header[k]) < 0.005)
        for k in _COMPUTED_TOTALS
    )


def parse_import(df: pd.DataFrame) -> ImportResult:
    """Group one-row-per-line data into (header, lines) per SO number."""
    result = ImportResult()
    mapping, result.unknown_columns = map_columns(df.columns)
    if "so_number" not in mapping.values():
        result.errors.append(
            "ไม่พบคอลัมน์ “เลขที่ SO” — ใช้ไฟล์แม่แบบ หรือไฟล์ที่ export จากระบบซึ่งมีคอลัมน์ Document No."
        )
        return result

    grouped: dict[str, tuple[dict, list[dict]]] = {}
    for position, (_, raw) in enumerate(df.iterrows()):
        excel_row = position + 2            # row 1 is the header
        values, bad = {}, []
        for col, key in mapping.items():
            spec = FIELDS_BY_KEY[key]
            try:
                values[key] = _PARSERS[spec.kind](raw[col])
            except (ValueError, OverflowError):
                bad.append(f"{spec.label} “{raw[col]}” ไม่ใช่{_KIND_HINT.get(spec.kind, 'ค่าที่ถูกต้อง')}")
                values[key] = None
        if all(v is None for v in values.values()) and not bad:
            continue                        # blank row
        so_number = values.get("so_number")
        if not so_number:
            result.errors.append(f"แถว {excel_row}: ไม่มีเลขที่ SO")
            continue
        if not _SO_NUMBER_RE.match(so_number):
            result.errors.append(f"แถว {excel_row}: เลขที่ SO “{so_number}” มีอักขระที่ใช้ไม่ได้")
            continue
        result.errors.extend(f"แถว {excel_row}: {msg}" for msg in bad)

        header, lines = grouped.setdefault(so_number, ({}, []))
        for key in HEADER_KEYS:
            new = values.get(key)
            if new is None:
                continue
            if header.get(key) is None:
                header[key] = new
            elif header[key] != new:
                result.warnings.append(
                    f"แถว {excel_row}: {so_number} มี{FIELDS_BY_KEY[key].label}ไม่ตรงกับแถวก่อนหน้า — ใช้ค่าแรก"
                )
        line = {
            ("discount" if key == "line_discount" else key): values.get(key)
            for key in LINE_KEYS
        }
        if any(v is not None for k, v in line.items() if k != "line_no"):
            if line["line_no"] is not None:
                line["line_no"] = int(line["line_no"])
            lines.append(line)

    for header, lines in grouped.values():
        complete_totals(header, lines)
        result.orders.append((header, lines))
    return result


def _best_header_row(raw: pd.DataFrame) -> int:
    """Index of the row that looks most like a header (exports often add a title)."""
    best, best_hits = 0, -1
    for idx in range(min(len(raw), 15)):
        hits = sum(1 for v in raw.iloc[idx] if _norm_header(v) in _ALIAS_TO_KEY)
        if hits > best_hits:
            best, best_hits = idx, hits
    return best


def read_upload(filename: str, data: bytes) -> pd.DataFrame:
    """Read an .xlsx or .csv into a DataFrame with the header row detected.

    Raises ValueError with a Thai message the page can show.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            raw = pd.read_excel(io.BytesIO(data), header=None, dtype=object, engine="openpyxl")
        except Exception as exc:
            raise ValueError(f"เปิดไฟล์ Excel ไม่ได้: {exc}") from exc
    elif name.endswith(".csv"):
        raw = None
        for encoding in ("utf-8-sig", "cp874"):   # cp874 = Thai Windows (Excel "CSV")
            try:
                raw = pd.read_csv(io.BytesIO(data), header=None, dtype=str, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
            except Exception as exc:
                raise ValueError(f"อ่านไฟล์ CSV ไม่ได้: {exc}") from exc
        if raw is None:
            raise ValueError("อ่านไฟล์ CSV ไม่ได้ — บันทึกเป็น UTF-8 แล้วลองใหม่")
    else:
        raise ValueError("รองรับเฉพาะไฟล์ .xlsx หรือ .csv")
    if raw.empty:
        raise ValueError("ไฟล์ว่างเปล่า")
    header_row = _best_header_row(raw)
    columns = [str(v).strip() if not _is_blank(v) else f"Unnamed: {i}" for i, v in enumerate(raw.iloc[header_row])]
    body = raw.iloc[header_row + 1:].reset_index(drop=True)
    body.columns = columns
    return body


def find_customer_id(header: dict) -> int | None:
    """Link an SO to a customer by the receiver's phone, then the buyer's."""
    for key in ("ship_to_phone", "sell_to_phone"):
        phone = normalize_phone(header.get(key))
        if phone:
            customer = db.get_customer_by_phone(phone)
            if customer:
                return customer["id"]
    return None


def import_orders(
    orders: list[tuple[dict, list[dict]]],
    actor: str | None = None,
    actor_role: str | None = None,
    source: str | None = None,
) -> dict:
    """Save parsed orders (upsert by SO number) and write one audit entry.

    An SO already linked to a customer keeps that link when the file's phone
    matches nobody — a manual link is not undone by a re-import.
    """
    summary = {"created": 0, "updated": 0, "linked": 0, "lines": 0}
    so_numbers = []
    for header, lines in orders:
        header = dict(header)
        customer_id = find_customer_id(header)
        if customer_id is None:
            existing = db.get_sales_order(so_number=header["so_number"], include_deleted=True)
            customer_id = existing.get("customer_id") if existing else None
        header["customer_id"] = customer_id
        _, created = db.save_sales_order(header, lines, actor=actor)
        summary["created" if created else "updated"] += 1
        summary["linked"] += 1 if customer_id else 0
        summary["lines"] += len(lines)
        so_numbers.append(header["so_number"])
    if so_numbers:
        audit.record(
            action=audit.IMPORT, entity=ENTITY, entity_id=None,
            entity_label=f"{len(so_numbers)} SO", actor=actor, actor_role=actor_role,
            changes={"file": source, **summary, "so_numbers": so_numbers[:200]},
        )
    return summary


# ── Manual entry ─────────────────────────────────────────────────────────

def clean_lines(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Rows from the page's line editor → DB lines, dropping empty rows."""
    lines, errors = [], []
    for position, row in enumerate(rows, 1):
        line = {}
        for key in LINE_KEYS:
            spec = FIELDS_BY_KEY[key]
            target = "discount" if key == "line_discount" else key
            raw = row.get(target, row.get(key))
            try:
                line[target] = _PARSERS[spec.kind](raw)
            except (ValueError, OverflowError):
                errors.append(f"รายการที่ {position}: {spec.label} “{raw}” ไม่ใช่{_KIND_HINT.get(spec.kind, 'ค่าที่ถูกต้อง')}")
                line[target] = None
        if all(v is None for k, v in line.items() if k != "line_no"):
            continue
        line["line_no"] = int(line["line_no"]) if line["line_no"] is not None else len(lines) + 1
        lines.append(line)
    return lines, errors


def save_manual(
    header: dict,
    lines: list[dict],
    actor: str | None = None,
    actor_role: str | None = None,
    so_id: int | None = None,
) -> tuple[int | None, str | None]:
    """Create (so_id None) or edit one SO from the form. Returns (id, error)."""
    values = {}
    for key in HEADER_KEYS:
        spec = FIELDS_BY_KEY[key]
        try:
            values[key] = _PARSERS[spec.kind](header.get(key))
        except (ValueError, OverflowError):
            return None, f"{spec.label} “{header.get(key)}” ไม่ใช่{_KIND_HINT.get(spec.kind, 'ค่าที่ถูกต้อง')}"
    so_number = values.get("so_number")
    if not so_number:
        return None, "กรุณากรอกเลขที่ SO"
    if not _SO_NUMBER_RE.match(so_number):
        return None, "เลขที่ SO ใช้ได้เฉพาะ A-Z 0-9 . _ - / และยาวอย่างน้อย 2 ตัวอักษร"
    line_rows, errors = clean_lines(lines)
    if errors:
        return None, errors[0]

    existing = db.get_sales_order(so_number=so_number, include_deleted=True)
    before = db.get_sales_order(so_id=so_id, include_deleted=True) if so_id else None
    if so_id and not before:
        return None, "ไม่พบ SO นี้แล้ว"
    if existing and (not before or existing["id"] != before["id"]):
        state = " (ถูกซ่อนไว้ — กู้คืนแทนการสร้างใหม่)" if existing.get("deleted_at") else ""
        return None, f"เลขที่ SO `{so_number}` มีอยู่แล้ว{state}"
    if before and before["so_number"] != so_number:
        return None, "เปลี่ยนเลขที่ SO ไม่ได้ — สร้าง SO ใหม่แทน"

    complete_totals(values, line_rows)
    customer_id = header.get("customer_id")
    if customer_id in (None, "", 0):
        customer_id = find_customer_id(values) or (before or {}).get("customer_id")
    values["customer_id"] = int(customer_id) if customer_id else None

    new_id, created = db.save_sales_order(values, line_rows, actor=actor)
    if created:
        changes = {k: v for k, v in values.items() if v not in (None, "")}
        changes["lines"] = len(line_rows)
        audit.record(action=audit.CREATE, entity=ENTITY, entity_id=new_id, entity_label=so_number,
                     actor=actor, actor_role=actor_role, changes=changes)
    else:
        changes = audit.diff_fields(before, values)
        old_lines = [{k: ln.get(k) for k in db.SO_LINE_COLUMNS} for ln in before["lines"]]
        new_lines = [{k: ln.get(k) for k in db.SO_LINE_COLUMNS} for ln in line_rows]
        if old_lines != new_lines:
            changes["lines"] = [len(old_lines), len(new_lines)]
        if changes:
            audit.record(action=audit.UPDATE, entity=ENTITY, entity_id=new_id, entity_label=so_number,
                         actor=actor, actor_role=actor_role, changes=changes)
    return new_id, None


def hide(so_id: int, actor: str | None = None, actor_role: str | None = None) -> str | None:
    order = db.get_sales_order(so_id=so_id)
    if not order:
        return "ไม่พบ SO นี้ — อาจถูกซ่อนไว้แล้ว"
    db.soft_delete_sales_order(so_id, actor=actor)
    audit.record(action=audit.DELETE, entity=ENTITY, entity_id=so_id, entity_label=order["so_number"],
                 actor=actor, actor_role=actor_role)
    return None


def restore(so_id: int, actor: str | None = None, actor_role: str | None = None) -> str | None:
    order = db.get_sales_order(so_id=so_id, include_deleted=True)
    if not order or not order.get("deleted_at"):
        return "SO นี้ไม่ได้ถูกซ่อนไว้"
    db.restore_sales_order(so_id)
    audit.record(action=audit.RESTORE, entity=ENTITY, entity_id=so_id, entity_label=order["so_number"],
                 actor=actor, actor_role=actor_role)
    return None


def link_customer(so_id: int, customer_id: int | None, actor: str | None = None,
                  actor_role: str | None = None) -> str | None:
    """Point an SO at a customer by hand (or clear the link)."""
    order = db.get_sales_order(so_id=so_id)
    if not order:
        return "ไม่พบ SO นี้"
    if (order.get("customer_id") or None) == (customer_id or None):
        return None
    header = {k: order.get(k) for k in db.SO_HEADER_COLUMNS}
    header["customer_id"] = customer_id
    db.save_sales_order(header, order["lines"], actor=actor)
    audit.record(action=audit.UPDATE, entity=ENTITY, entity_id=so_id, entity_label=order["so_number"],
                 actor=actor, actor_role=actor_role,
                 changes={"customer_id": [order.get("customer_id"), customer_id]})
    return None


# ── Template ─────────────────────────────────────────────────────────────

def template_bytes() -> bytes:
    """An empty .xlsx with our column headers and an instructions sheet.

    Deliberately no sample rows: the company asked that real SO data never be
    used as an example, and made-up rows tend to get imported by mistake.
    """
    buffer = io.BytesIO()
    columns = [f.label + (" *" if f.key == "so_number" else "") for f in FIELDS]
    guide = pd.DataFrame(
        [
            {
                "คอลัมน์": f.label,
                "ระดับ": "หัว SO (ซ้ำทุกแถวของ SO เดียวกัน)" if f.level == "header" else "รายการสินค้า (1 แถว = 1 รายการ)",
                "รูปแบบ": {"date": "วันที่ วว/ดด/ปปปป (พ.ศ. หรือ ค.ศ.)", "number": "ตัวเลข", "phone": "เบอร์โทร"}.get(f.kind, "ข้อความ"),
                "ชื่อคอลัมน์ที่ใช้แทนได้ (เช่นจาก NAV)": ", ".join(f.aliases),
                "หมายเหตุ": f.note,
            }
            for f in FIELDS
        ]
    )
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(columns=columns).to_excel(writer, sheet_name="SO", index=False)
        guide.to_excel(writer, sheet_name="คำอธิบาย", index=False)
        for sheet in writer.sheets.values():
            for cells in sheet.columns:
                width = max(len(str(c.value or "")) for c in cells)
                sheet.column_dimensions[cells[0].column_letter].width = min(max(12, width + 2), 60)
            sheet.freeze_panes = "A2"
    return buffer.getvalue()
