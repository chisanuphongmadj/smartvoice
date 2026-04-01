import sqlite3
import os
from datetime import datetime


def get_db_path() -> str:
    return os.getenv("DB_PATH", "data/smartvoice.db")


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                filename          TEXT NOT NULL,
                file_hash         TEXT NOT NULL UNIQUE,
                file_path         TEXT NOT NULL,
                transcript        TEXT,
                summary           TEXT,
                sentiment         TEXT CHECK(sentiment IN ('positive','neutral','negative')),
                topic             TEXT,
                speaker_mapping   TEXT,
                agent_performance TEXT,
                keywords          TEXT,
                anomaly_detected  INTEGER DEFAULT 0,
                anomaly_reason    TEXT,
                status            TEXT NOT NULL DEFAULT 'uploaded'
                                    CHECK(status IN ('uploaded','processing','done','error')),
                error_msg         TEXT,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name     TEXT NOT NULL,
                last_name      TEXT NOT NULL,
                phone          TEXT UNIQUE,
                email          TEXT,
                gender         TEXT,
                date_of_birth  TEXT,
                address        TEXT,
                subdistrict    TEXT,
                district       TEXT,
                city_province  TEXT,
                country        TEXT DEFAULT 'Thailand',
                postcode       TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warranty_registrations (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_no         TEXT UNIQUE NOT NULL,
                customer_id             INTEGER REFERENCES customers(id),
                channel                 TEXT,
                certificate_no          TEXT,
                category                TEXT,
                brand                   TEXT,
                model                   TEXT,
                size                    TEXT,
                sku                     TEXT,
                serial_no               TEXT,
                label_no                TEXT,
                warranty_period_months  INTEGER DEFAULT 120,
                date_of_purchase        TEXT,
                date_of_delivery        TEXT,
                purchase_channel        TEXT,
                order_number            TEXT,
                expiry_date             TEXT,
                remark                  TEXT,
                created_at              TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS call_customer_links (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id      INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
                customer_id  INTEGER NOT NULL REFERENCES customers(id),
                warranty_id  INTEGER REFERENCES warranty_registrations(id),
                matched_by   TEXT DEFAULT 'manual',
                created_at   TEXT NOT NULL
            )
        """)
        _migrate(conn)
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(calls)").fetchall()}
    new_cols = [
        ("speaker_mapping",   "TEXT"),
        ("agent_performance", "TEXT"),
        ("keywords",          "TEXT"),
        ("brand_mentions",    "TEXT"),
        ("platform_mentions", "TEXT"),
        ("anomaly_detected",  "INTEGER DEFAULT 0"),
        ("anomaly_reason",    "TEXT"),
        ("processing_step",   "TEXT"),
    ]
    for col, col_type in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE calls ADD COLUMN {col} {col_type}")


def insert_call(filename: str, file_hash: str, file_path: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO calls (filename, file_hash, file_path, status, created_at, updated_at)
            VALUES (?, ?, ?, 'uploaded', ?, ?)
            """,
            (filename, file_hash, file_path, now, now),
        )
        return cur.lastrowid


def hash_exists(file_hash: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM calls WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    conn.close()
    return row is not None


def get_call_by_hash(file_hash: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM calls WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_call_status(call_id: int, status: str, error_msg: str = None) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE calls SET status = ?, error_msg = ?, updated_at = ? WHERE id = ?",
            (status, error_msg, now, call_id),
        )
    conn.close()


def update_processing_step(call_id: int, step: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE calls SET processing_step = ?, updated_at = ? WHERE id = ?",
            (step, now, call_id),
        )
    conn.close()


def update_call_results(
    call_id: int,
    transcript: str,
    summary: str,
    sentiment: str,
    topic: str,
    speaker_mapping: str = "",
    agent_performance: str = "",
    keywords: str = "",
    brand_mentions: str = "",
    platform_mentions: str = "",
    anomaly_detected: bool = False,
    anomaly_reason: str = "",
) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        conn.execute(
            """
            UPDATE calls
            SET transcript = ?, summary = ?, sentiment = ?, topic = ?,
                speaker_mapping = ?, agent_performance = ?, keywords = ?,
                brand_mentions = ?, platform_mentions = ?,
                anomaly_detected = ?, anomaly_reason = ?,
                status = 'done', updated_at = ?
            WHERE id = ?
            """,
            (
                transcript, summary, sentiment, topic,
                speaker_mapping, agent_performance, keywords,
                brand_mentions, platform_mentions,
                int(anomaly_detected), anomaly_reason,
                now, call_id,
            ),
        )
    conn.close()


def get_all_calls() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM calls ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_call_by_id(call_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_call(call_id: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM calls WHERE id = ?", (call_id,))
    conn.close()


def delete_calls_bulk(call_ids: list[int]) -> None:
    if not call_ids:
        return
    placeholders = ",".join("?" * len(call_ids))
    conn = get_connection()
    with conn:
        conn.execute(f"DELETE FROM calls WHERE id IN ({placeholders})", call_ids)
    conn.close()


def get_done_calls() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM calls WHERE status = 'done' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Customers ────────────────────────────────────────────────────────────────

def insert_customer(
    first_name: str, last_name: str, phone: str = None, email: str = None,
    gender: str = None, date_of_birth: str = None, address: str = None,
    subdistrict: str = None, district: str = None, city_province: str = None,
    country: str = "Thailand", postcode: str = None,
) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO customers
               (first_name, last_name, phone, email, gender, date_of_birth,
                address, subdistrict, district, city_province, country, postcode, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (first_name, last_name, phone, email, gender, date_of_birth,
             address, subdistrict, district, city_province, country, postcode, now),
        )
    conn.close()
    return cur.lastrowid


def get_all_customers() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM customers ORDER BY last_name, first_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_by_phone(phone: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_by_id(customer_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Warranty Registrations ───────────────────────────────────────────────────

def insert_warranty(
    registration_no: str, customer_id: int, channel: str = None,
    certificate_no: str = None, category: str = None, brand: str = None,
    model: str = None, size: str = None, sku: str = None,
    serial_no: str = None, label_no: str = None,
    warranty_period_months: int = 120, date_of_purchase: str = None,
    date_of_delivery: str = None, purchase_channel: str = None,
    order_number: str = None, expiry_date: str = None, remark: str = None,
) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO warranty_registrations
               (registration_no, customer_id, channel, certificate_no, category, brand,
                model, size, sku, serial_no, label_no, warranty_period_months,
                date_of_purchase, date_of_delivery, purchase_channel, order_number,
                expiry_date, remark, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (registration_no, customer_id, channel, certificate_no, category, brand,
             model, size, sku, serial_no, label_no, warranty_period_months,
             date_of_purchase, date_of_delivery, purchase_channel, order_number,
             expiry_date, remark, now),
        )
    conn.close()
    return cur.lastrowid


def get_warranties_by_customer(customer_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM warranty_registrations WHERE customer_id = ? ORDER BY date_of_purchase DESC",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_warranties() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT w.*, c.first_name, c.last_name, c.phone
           FROM warranty_registrations w
           LEFT JOIN customers c ON c.id = w.customer_id
           ORDER BY w.date_of_purchase DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Call–Customer Links ──────────────────────────────────────────────────────

def link_call_customer(
    call_id: int, customer_id: int,
    warranty_id: int = None, matched_by: str = "manual",
) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT OR REPLACE INTO call_customer_links
               (call_id, customer_id, warranty_id, matched_by, created_at)
               VALUES (?,?,?,?,?)""",
            (call_id, customer_id, warranty_id, matched_by, now),
        )
    conn.close()
    return cur.lastrowid


def get_call_customer_link(call_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT l.*, c.first_name, c.last_name, c.phone, c.email,
                  w.registration_no, w.brand, w.model, w.size,
                  w.purchase_channel, w.date_of_purchase, w.warranty_period_months
           FROM call_customer_links l
           JOIN customers c ON c.id = l.customer_id
           LEFT JOIN warranty_registrations w ON w.id = l.warranty_id
           WHERE l.call_id = ?""",
        (call_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
