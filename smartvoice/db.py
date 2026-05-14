import sqlite3
import os
from datetime import datetime, timezone


def _now() -> str:
    """Return current UTC timestamp as ISO 8601 string (timezone-aware)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id   INTEGER REFERENCES customers(id),
                subject       TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'open'
                                CHECK(status IN ('open','closed','follow_up')),
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
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
        ("sentiment_reason",  "TEXT"),
        ("anomaly_severity",  "TEXT"),
        ("customer_phone",    "TEXT"),
        ("case_id",            "INTEGER"),
        ("uploaded_by",       "TEXT"),
        ("uploaded_by_role",  "TEXT"),
    ]
    for col, col_type in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE calls ADD COLUMN {col} {col_type}")


def insert_call(
    filename: str,
    file_hash: str,
    file_path: str,
    uploaded_by: str | None = None,
    uploaded_by_role: str | None = None,
) -> int:
    """Insert a new call record. `uploaded_by` + `uploaded_by_role` are the
    staff name / role captured from the Streamlit login widget (optional for
    backward-compat; NULL when no user is logged in)."""
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO calls (
                filename, file_hash, file_path, status,
                uploaded_by, uploaded_by_role,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)
            """,
            (filename, file_hash, file_path,
             uploaded_by, uploaded_by_role,
             now, now),
        )
        return cur.lastrowid


def get_call_by_hash(file_hash: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM calls WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_call_status(call_id: int, status: str, error_msg: str = None) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE calls SET status = ?, error_msg = ?, updated_at = ? WHERE id = ?",
            (status, error_msg, now, call_id),
        )
    conn.close()


def update_processing_step(call_id: int, step: str) -> None:
    now = _now()
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
    sentiment_reason: str = "",
    anomaly_severity: str = "",
) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            """
            UPDATE calls
            SET transcript = ?, summary = ?, sentiment = ?, topic = ?,
                speaker_mapping = ?, agent_performance = ?, keywords = ?,
                brand_mentions = ?, platform_mentions = ?,
                anomaly_detected = ?, anomaly_reason = ?,
                sentiment_reason = ?, anomaly_severity = ?,
                status = 'done', updated_at = ?
            WHERE id = ?
            """,
            (
                transcript, summary, sentiment, topic,
                speaker_mapping, agent_performance, keywords,
                brand_mentions, platform_mentions,
                int(anomaly_detected), anomaly_reason,
                sentiment_reason, anomaly_severity,
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


def delete_call(call_id: int) -> int:
    """Delete a call and clean up orphan cases. Returns orphan case count removed."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM calls WHERE id = ?", (call_id,))
        conn.execute("DELETE FROM call_customer_links WHERE call_id = ?", (call_id,))
    removed = _cleanup_orphan_cases(conn)
    conn.close()
    return removed


def delete_calls_bulk(call_ids: list[int]) -> int:
    """Delete multiple calls and clean up orphan cases. Returns orphan case count removed."""
    if not call_ids:
        return 0
    placeholders = ",".join("?" * len(call_ids))
    conn = get_connection()
    with conn:
        conn.execute(f"DELETE FROM calls WHERE id IN ({placeholders})", call_ids)
        conn.execute(f"DELETE FROM call_customer_links WHERE call_id IN ({placeholders})", call_ids)
    removed = _cleanup_orphan_cases(conn)
    conn.close()
    return removed


def _cleanup_orphan_cases(conn: sqlite3.Connection) -> int:
    """Remove cases that have no calls referencing them. Returns count removed."""
    with conn:
        cur = conn.execute(
            """DELETE FROM cases
               WHERE id NOT IN (
                   SELECT DISTINCT case_id FROM calls
                   WHERE case_id IS NOT NULL
               )"""
        )
        return cur.rowcount or 0


def delete_orphan_cases() -> int:
    """Public helper: delete all orphan cases (no calls pointing to them)."""
    conn = get_connection()
    removed = _cleanup_orphan_cases(conn)
    conn.close()
    return removed


def count_orphan_cases() -> int:
    """Count cases that have no calls referencing them."""
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM cases
           WHERE id NOT IN (
               SELECT DISTINCT case_id FROM calls
               WHERE case_id IS NOT NULL
           )"""
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


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
    """Insert a customer. If phone already exists, returns the existing customer's id
    (idempotent — safe for seed scripts to re-run)."""
    if phone:
        existing = get_customer_by_phone(phone)
        if existing:
            return existing["id"]
    now = _now()
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

def get_warranty_by_registration(registration_no: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM warranty_registrations WHERE registration_no = ?",
        (registration_no,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_warranty(
    registration_no: str, customer_id: int, channel: str = None,
    certificate_no: str = None, category: str = None, brand: str = None,
    model: str = None, size: str = None, sku: str = None,
    serial_no: str = None, label_no: str = None,
    warranty_period_months: int = 120, date_of_purchase: str = None,
    date_of_delivery: str = None, purchase_channel: str = None,
    order_number: str = None, expiry_date: str = None, remark: str = None,
) -> int:
    """Insert a warranty registration. If registration_no already exists,
    returns the existing id (idempotent — safe for seed scripts to re-run)."""
    existing = get_warranty_by_registration(registration_no)
    if existing:
        return existing["id"]
    now = _now()
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


def update_call_customer_phone(call_id: int, phone: str) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE calls SET customer_phone = ?, updated_at = ? WHERE id = ?",
            (phone, now, call_id),
        )
    conn.close()


def auto_link_call_by_phone(call_id: int, phone: str) -> dict | None:
    """Try to auto-link a call to a customer (and their latest warranty) by phone.

    Returns a dict with link info if successful, None otherwise.
    """
    if not phone:
        return None

    customer = get_customer_by_phone(phone)
    if not customer:
        return None

    # Pick the latest warranty for this customer (if any)
    warranties = get_warranties_by_customer(customer["id"])
    warranty_id = warranties[0]["id"] if warranties else None

    link_id = link_call_customer(
        call_id=call_id,
        customer_id=customer["id"],
        warranty_id=warranty_id,
        matched_by="auto_phone",
    )
    return {
        "link_id": link_id,
        "customer_id": customer["id"],
        "customer_name": f"{customer['first_name']} {customer['last_name']}",
        "customer_phone": phone,
        "warranty_id": warranty_id,
    }


# ─── Call–Customer Links ──────────────────────────────────────────────────────

def link_call_customer(
    call_id: int, customer_id: int,
    warranty_id: int = None, matched_by: str = "manual",
) -> int:
    now = _now()
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


# ─── Cases ───────────────────────────────────────────────────────────────────

def create_case(customer_id: int, subject: str, status: str = "open") -> int:
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO cases (customer_id, subject, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (customer_id, subject, status, now, now),
        )
    conn.close()
    return cur.lastrowid


def update_case_status(case_id: int, status: str) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE cases SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, case_id),
        )
    conn.close()


def update_case_subject(case_id: int, subject: str) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE cases SET subject = ?, updated_at = ? WHERE id = ?",
            (subject, now, case_id),
        )
    conn.close()


def assign_call_to_case(call_id: int, case_id: int) -> None:
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE calls SET case_id = ?, updated_at = ? WHERE id = ?",
            (case_id, now, call_id),
        )
    conn.close()


def get_case_by_id(case_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def latest_call_time_in_case(case_id: int) -> str | None:
    """Return ISO timestamp of the most recent call.created_at in this case.

    Used by the pipeline's auto-assign logic to decide whether a new call is
    close enough in time to the case's sibling calls to skip LLM matching.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(created_at) AS latest FROM calls WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    conn.close()
    return row["latest"] if row and row["latest"] else None


def merge_cases(src_case_id: int, dst_case_id: int) -> int:
    """Move all calls from src into dst, then delete the now-empty src case.

    Returns the number of calls moved. A no-op (returns 0) when src == dst.
    Raises ValueError if either case id does not exist.
    """
    if src_case_id == dst_case_id:
        return 0
    conn = get_connection()
    src = conn.execute("SELECT id FROM cases WHERE id = ?", (src_case_id,)).fetchone()
    dst = conn.execute("SELECT id FROM cases WHERE id = ?", (dst_case_id,)).fetchone()
    if not src or not dst:
        conn.close()
        raise ValueError(f"merge_cases: invalid ids src={src_case_id} dst={dst_case_id}")

    now = _now()
    with conn:
        cur = conn.execute(
            "UPDATE calls SET case_id = ?, updated_at = ? WHERE case_id = ?",
            (dst_case_id, now, src_case_id),
        )
        moved = cur.rowcount
        conn.execute(
            "UPDATE cases SET updated_at = ? WHERE id = ?",
            (now, dst_case_id),
        )
        conn.execute("DELETE FROM cases WHERE id = ?", (src_case_id,))
    conn.close()
    return moved


def get_cases_by_customer(customer_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM cases WHERE customer_id = ? ORDER BY created_at DESC",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_cases_by_customer(customer_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT cs.*, GROUP_CONCAT(c.id) as call_ids
           FROM cases cs
           LEFT JOIN calls c ON c.case_id = cs.id
           WHERE cs.customer_id = ? AND cs.status IN ('open', 'follow_up')
           GROUP BY cs.id
           ORDER BY cs.updated_at DESC""",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_calls_by_case(case_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM calls WHERE case_id = ? ORDER BY created_at ASC",
        (case_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_cases() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT cs.*,
                  c.first_name, c.last_name, c.phone,
                  COUNT(cl.id) as call_count
           FROM cases cs
           LEFT JOIN customers c ON c.id = cs.customer_id
           LEFT JOIN calls cl ON cl.case_id = cs.id
           GROUP BY cs.id
           ORDER BY cs.updated_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_calls_by_customer(customer_id: int) -> list[dict]:
    """Get all calls linked to a customer (via call_customer_links), newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.*, l.matched_by
           FROM calls c
           JOIN call_customer_links l ON l.call_id = c.id
           WHERE l.customer_id = ?
           ORDER BY c.created_at DESC""",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_case_counts() -> dict:
    """Return counts of cases by status: {'open': n, 'follow_up': n, 'closed': n, 'total': n}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM cases GROUP BY status"
    ).fetchall()
    conn.close()
    counts = {r["status"]: r["n"] for r in rows}
    counts["total"] = sum(counts.values())
    for s in ("open", "follow_up", "closed"):
        counts.setdefault(s, 0)
    return counts


def get_previous_call_summaries_for_customer(customer_id: int, exclude_call_id: int = None) -> list[dict]:
    """Get summaries of previous analyzed calls for a customer, grouped by case."""
    conn = get_connection()
    query = """
        SELECT c.id as call_id, c.summary, c.topic, c.case_id,
               cs.subject as case_subject, cs.status as case_status
        FROM calls c
        LEFT JOIN cases cs ON cs.id = c.case_id
        JOIN call_customer_links l ON l.call_id = c.id
        WHERE l.customer_id = ? AND c.status = 'done' AND c.summary IS NOT NULL
    """
    params: list = [customer_id]
    if exclude_call_id:
        query += " AND c.id != ?"
        params.append(exclude_call_id)
    query += " ORDER BY c.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
