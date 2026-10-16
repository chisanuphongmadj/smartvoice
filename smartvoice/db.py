import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone


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
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
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
            CREATE TABLE IF NOT EXISTS users (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name   TEXT NOT NULL,
                role           TEXT NOT NULL,
                password_hash  TEXT NOT NULL,
                is_active      INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                last_login_at  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                actor         TEXT,
                actor_role    TEXT,
                action        TEXT NOT NULL,
                entity        TEXT NOT NULL,
                entity_id     INTEGER,
                entity_label  TEXT,
                changes       TEXT,
                created_at    TEXT NOT NULL
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
        _create_sales_order_tables(conn)
        _migrate(conn)
    conn.close()


# ── Sales orders (SO) ─────────────────────────────────────────────────────
# Mirrors the company's sales-order document (Dynamics NAV "ใบสั่งขาย"): a
# header with sell-to / ship-to parties and totals, plus item lines.
SO_HEADER_COLUMNS = (
    "so_number", "document_date", "order_date", "shipment_date", "promised_delivery_date",
    "due_date", "currency", "sales_type", "purchasing_type", "salesperson",
    "external_doc", "credit_term", "customer_po_no",
    "sell_to_no", "sell_to_name", "sell_to_address", "sell_to_contact", "sell_to_phone",
    "ship_to_name", "ship_to_address", "ship_to_contact", "ship_to_phone", "ship_to_email",
    "total", "discount", "net_amount", "vat", "grand_total", "remark",
)
SO_LINE_COLUMNS = (
    "line_no", "item_no", "description", "requested_delivery_date", "uom",
    "location", "quantity", "unit_price", "discount", "amount",
)
_SO_MONEY_COLUMNS = {"total", "discount", "net_amount", "vat", "grand_total"}


def _create_sales_order_tables(conn: sqlite3.Connection) -> None:
    header_cols = ",\n".join(
        f"                {col} {'REAL' if col in _SO_MONEY_COLUMNS else 'TEXT'}"
        for col in SO_HEADER_COLUMNS if col != "so_number"
    )
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS sales_orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            so_number    TEXT NOT NULL UNIQUE,
{header_cols},
            customer_id  INTEGER REFERENCES customers(id),
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            created_by   TEXT,
            deleted_at   TEXT,
            deleted_by   TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_order_lines (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_order_id           INTEGER NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
            line_no                  INTEGER,
            item_no                  TEXT,
            description              TEXT,
            requested_delivery_date  TEXT,
            uom                      TEXT,
            location                 TEXT,
            quantity                 REAL,
            unit_price               REAL,
            discount                 REAL,
            amount                   REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_so_customer ON sales_orders(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_so_ship_phone ON sales_orders(ship_to_phone)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_so_lines_order ON sales_order_lines(sales_order_id)")


def _migrate(conn: sqlite3.Connection) -> None:
    _migrate_calls(conn)
    _migrate_soft_delete(conn)
    _migrate_case_assignment(conn)
    _migrate_warranty_fields(conn)


def _migrate_warranty_fields(conn: sqlite3.Connection) -> None:
    """Fields the company's warranty-registration system has and we lacked.

    `status` is the system's Active/Cancelled state — a cancelled registration
    is still shown (with its status), unlike a hidden (`deleted_at`) row.
    """
    for table, columns in (
        ("customers", (("nick_name", "TEXT"), ("channel", "TEXT"))),
        ("warranty_registrations", (
            ("ref_id", "TEXT"), ("so_number", "TEXT"),
            ("status", "TEXT DEFAULT 'active'"), ("cancelled_at", "TEXT"),
            ("cancelled_by", "TEXT"), ("proof_path", "TEXT"),
        )),
    ):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, col_type in columns:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")


def _migrate_case_assignment(conn: sqlite3.Connection) -> None:
    """Add the case-ownership columns to existing databases.

    A staff member claims a case (`assignee_*`); from then on only they can
    change its status, so nobody else can take it over. `closed_by` /
    `closed_at` record who closed it, since the assignee can be released later.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
    for col in ("assignee_username", "assignee_name", "assigned_at", "closed_by", "closed_at"):
        if col not in existing:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {col} TEXT")


def _migrate_soft_delete(conn: sqlite3.Connection) -> None:
    """Add the soft-delete columns to existing databases.

    Customers and warranty registrations are never removed from the database —
    they are hidden by stamping `deleted_at`, so the row stays available as a
    record of what happened (see `soft_delete_customer`).
    """
    for table in ("customers", "warranty_registrations"):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in ("deleted_at", "deleted_by"):
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")

    # Marks the warranties that were hidden *because* their customer was hidden,
    # so restoring the customer brings back exactly those (and not the ones an
    # Admin hid separately). A timestamp cannot tell them apart — two hides in
    # the same second would collide.
    warranty_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(warranty_registrations)").fetchall()
    }
    if "hidden_with_customer" not in warranty_cols:
        conn.execute(
            "ALTER TABLE warranty_registrations ADD COLUMN hidden_with_customer INTEGER DEFAULT 0"
        )


def _migrate_calls(conn: sqlite3.Connection) -> None:
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
        ("topic_detail",      "TEXT"),
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
    topic_detail: str = "",
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
                topic_detail = ?,
                status = 'done', updated_at = ?
            WHERE id = ?
            """,
            (
                transcript, summary, sentiment, topic,
                speaker_mapping, agent_performance, keywords,
                brand_mentions, platform_mentions,
                int(anomaly_detected), anomaly_reason,
                sentiment_reason, anomaly_severity,
                topic_detail,
                now, call_id,
            ),
        )
    conn.close()


def get_all_calls(limit: int | None = None) -> list[dict]:
    """Return all calls newest-first.

    `limit=None` keeps the original behavior (return everything). Passing an
    int caps the result for the Admin page so it stays responsive at scale
    (10K+ uploads). Status counts displayed at the top of the page should
    use `count_calls_by_status()` so they remain accurate even when this
    call returns a capped subset.
    """
    conn = get_connection()
    sql = "SELECT * FROM calls ORDER BY created_at DESC"
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_calls_by_status() -> dict[str, int]:
    """Return {'uploaded': N, 'processing': N, 'done': N, 'error': N, 'total': N}.

    Implemented as a single GROUP BY so the Admin page can show accurate
    counts without loading the full table.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM calls GROUP BY status"
    ).fetchall()
    conn.close()
    counts = {"uploaded": 0, "processing": 0, "done": 0, "error": 0}
    for r in rows:
        if r["status"] in counts:
            counts[r["status"]] = int(r["n"] or 0)
    counts["total"] = sum(counts.values())
    return counts


def count_anomaly_calls() -> dict[str, int]:
    """{'total': N, 'high': N} — analysed calls flagged as anomalies, for the
    home page's "งานที่รอคุณ" cards (one SQL count, no rows loaded)."""
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN anomaly_severity = 'high' THEN 1 ELSE 0 END) AS high
           FROM calls WHERE status = 'done' AND anomaly_detected = 1"""
    ).fetchone()
    conn.close()
    return {"total": int(row["total"] or 0), "high": int(row["high"] or 0)}


def get_pending_call_ids() -> list[int]:
    """Return IDs of every call awaiting processing (status='uploaded').

    Used by "Process All Pending" — the Admin page now loads only the latest
    N rows for display, so we cannot derive the full pending set from that
    capped list.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM calls WHERE status = 'uploaded' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [int(r["id"]) for r in rows]


def get_processing_calls() -> list[dict]:
    """Return all calls currently in 'processing' state (usually 0-1 rows).

    Used by the Admin auto-refresh fragment so it doesn't have to scan the
    whole table every 3 seconds.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM calls WHERE status = 'processing' ORDER BY updated_at DESC"
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


def recover_stale_processing(max_age_minutes: int) -> int:
    """Reset stale processing calls to uploaded so they can be retried."""
    if max_age_minutes <= 0:
        return 0
    threshold = (
        datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    ).isoformat(timespec="seconds")
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            UPDATE calls
            SET status = 'uploaded',
                processing_step = NULL,
                error_msg = ?,
                updated_at = ?
            WHERE status = 'processing'
              AND updated_at < ?
            """,
            (
                f"Recovered from stale processing state after {max_age_minutes} minutes.",
                _now(),
                threshold,
            ),
        )
    conn.close()
    return cur.rowcount or 0


def get_done_calls(limit: int | None = None, offset: int = 0) -> list[dict]:
    """Return completed calls newest-first.

    `limit=None` keeps the original behavior (return everything). Passing an int
    caps the result for dashboards that need to stay responsive on large datasets.
    """
    conn = get_connection()
    sql = "SELECT * FROM calls WHERE status = 'done' ORDER BY created_at DESC"
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (int(limit), int(offset))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_done_calls() -> int:
    """Return total number of completed calls (used for 'X of Y' indicators)."""
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM calls WHERE status = 'done'").fetchone()[0]
    conn.close()
    return int(n or 0)


# ─── Customers ────────────────────────────────────────────────────────────────

def insert_customer(
    first_name: str, last_name: str, phone: str = None, email: str = None,
    gender: str = None, date_of_birth: str = None, address: str = None,
    subdistrict: str = None, district: str = None, city_province: str = None,
    country: str = "Thailand", postcode: str = None,
    nick_name: str = None, channel: str = None,
) -> int:
    """Insert a customer. If phone already exists, returns the existing customer's id
    (idempotent — safe for seed scripts to re-run).

    Hidden customers count as existing: `phone` is UNIQUE, so a soft-deleted row
    still owns the number. The UI blocks this case earlier and offers a restore.
    """
    if phone:
        existing = get_customer_by_phone(phone, include_deleted=True)
        if existing:
            return existing["id"]
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO customers
               (first_name, last_name, phone, email, gender, date_of_birth,
                address, subdistrict, district, city_province, country, postcode,
                nick_name, channel, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (first_name, last_name, phone, email, gender, date_of_birth,
             address, subdistrict, district, city_province, country, postcode,
             nick_name, channel, now),
        )
    conn.close()
    return cur.lastrowid


def get_all_customers(include_deleted: bool = False) -> list[dict]:
    """Active customers. Hidden (soft-deleted) rows are excluded by default."""
    where = "" if include_deleted else "WHERE deleted_at IS NULL"
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM customers {where} ORDER BY last_name, first_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_deleted_customers() -> list[dict]:
    """Hidden customers, newest hidden first — the 'trash' view."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM customers WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_by_phone(phone: str, include_deleted: bool = False) -> dict | None:
    """Look up by phone. `include_deleted` matters because `phone` is UNIQUE —
    a hidden customer still owns their number, so the caller has to notice."""
    extra = "" if include_deleted else "AND deleted_at IS NULL"
    conn = get_connection()
    row = conn.execute(
        f"SELECT * FROM customers WHERE phone = ? {extra}", (phone,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_by_id(customer_id: int, include_deleted: bool = False) -> dict | None:
    extra = "" if include_deleted else "AND deleted_at IS NULL"
    conn = get_connection()
    row = conn.execute(
        f"SELECT * FROM customers WHERE id = ? {extra}", (customer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# Columns the Admin data-entry page may patch. `id` and `created_at` are not
# editable — everything else on the row is.
CUSTOMER_EDITABLE_COLUMNS = (
    "first_name", "last_name", "phone", "email", "gender", "date_of_birth",
    "address", "subdistrict", "district", "city_province", "country", "postcode",
    "nick_name", "channel",
)


def update_customer(customer_id: int, **fields) -> int:
    """Patch editable customer columns. Unknown keys are ignored.

    Returns the number of rows updated (0 when the id is unknown or nothing
    editable was passed).
    """
    updates = {col: fields[col] for col in CUSTOMER_EDITABLE_COLUMNS if col in fields}
    if not updates:
        return 0
    assignments = ", ".join(f"{col} = ?" for col in updates)
    params = [*updates.values(), customer_id]
    conn = get_connection()
    with conn:
        cur = conn.execute(f"UPDATE customers SET {assignments} WHERE id = ?", params)
        updated = cur.rowcount
    conn.close()
    return updated


def count_customer_dependencies(customer_id: int) -> dict[str, int]:
    """Rows that still reference this customer — checked before a delete."""
    conn = get_connection()
    counts = {
        "warranties": conn.execute(
            "SELECT COUNT(*) FROM warranty_registrations WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()[0],
        "calls": conn.execute(
            "SELECT COUNT(*) FROM call_customer_links WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()[0],
        "cases": conn.execute(
            "SELECT COUNT(*) FROM cases WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0],
    }
    conn.close()
    return counts


def soft_delete_customer(customer_id: int, actor: str | None = None) -> dict[str, int]:
    """Hide a customer instead of deleting the row.

    Nothing is removed from the database: the customer and their warranty
    registrations get a `deleted_at` stamp so they drop out of every default
    query, while call links, cases and the calls themselves stay exactly as they
    were. `restore_customer` puts everything back.

    Returns {"customer": 0|1, "warranties": n, "deleted_at": timestamp}.
    """
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE customers SET deleted_at = ?, deleted_by = ?
               WHERE id = ? AND deleted_at IS NULL""",
            (now, actor, customer_id),
        )
        hidden = cur.rowcount
        warranties = 0
        if hidden:
            wcur = conn.execute(
                """UPDATE warranty_registrations
                   SET deleted_at = ?, deleted_by = ?, hidden_with_customer = 1
                   WHERE customer_id = ? AND deleted_at IS NULL""",
                (now, actor, customer_id),
            )
            warranties = wcur.rowcount or 0
    conn.close()
    return {"customer": hidden, "warranties": warranties, "deleted_at": now if hidden else None}


def restore_customer(customer_id: int) -> dict[str, int]:
    """Un-hide a customer, together with the warranties hidden in the same action.

    Warranties an Admin hid separately keep their own `deleted_at` and stay
    hidden — only the ones flagged `hidden_with_customer` come back.
    """
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE customers SET deleted_at = NULL, deleted_by = NULL
               WHERE id = ? AND deleted_at IS NOT NULL""",
            (customer_id,),
        )
        restored = cur.rowcount
        warranties = 0
        if restored:
            wcur = conn.execute(
                """UPDATE warranty_registrations
                   SET deleted_at = NULL, deleted_by = NULL, hidden_with_customer = 0
                   WHERE customer_id = ? AND hidden_with_customer = 1""",
                (customer_id,),
            )
            warranties = wcur.rowcount or 0
    conn.close()
    return {"customer": restored, "warranties": warranties}


# ─── Warranty Registrations ───────────────────────────────────────────────────

def get_warranty_by_registration(
    registration_no: str, include_deleted: bool = False
) -> dict | None:
    """Look up by registration number, which is UNIQUE — so a hidden row still
    owns its number and `include_deleted` decides whether the caller sees it."""
    extra = "" if include_deleted else "AND deleted_at IS NULL"
    conn = get_connection()
    row = conn.execute(
        f"SELECT * FROM warranty_registrations WHERE registration_no = ? {extra}",
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
    ref_id: str = None, so_number: str = None, proof_path: str = None,
) -> int:
    """Insert a warranty registration. If registration_no already exists,
    returns the existing id (idempotent — safe for seed scripts to re-run).

    Hidden rows count as existing: `registration_no` is UNIQUE, so the number
    stays taken. The UI blocks this earlier and offers a restore instead.
    """
    existing = get_warranty_by_registration(registration_no, include_deleted=True)
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
                expiry_date, remark, ref_id, so_number, proof_path, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
            (registration_no, customer_id, channel, certificate_no, category, brand,
             model, size, sku, serial_no, label_no, warranty_period_months,
             date_of_purchase, date_of_delivery, purchase_channel, order_number,
             expiry_date, remark, ref_id, so_number, proof_path, now),
        )
    conn.close()
    return cur.lastrowid


def get_warranty_by_id(warranty_id: int, include_deleted: bool = False) -> dict | None:
    extra = "" if include_deleted else "AND deleted_at IS NULL"
    conn = get_connection()
    row = conn.execute(
        f"SELECT * FROM warranty_registrations WHERE id = ? {extra}", (warranty_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# Everything on the row except `id` and `created_at` may be corrected from the
# Admin data-entry page, including which customer the registration belongs to.
WARRANTY_EDITABLE_COLUMNS = (
    "registration_no", "customer_id", "channel", "certificate_no", "category",
    "brand", "model", "size", "sku", "serial_no", "label_no",
    "warranty_period_months", "date_of_purchase", "date_of_delivery",
    "purchase_channel", "order_number", "expiry_date", "remark",
    "ref_id", "so_number", "proof_path",
)


def update_warranty(warranty_id: int, **fields) -> int:
    """Patch editable warranty columns. Unknown keys are ignored."""
    updates = {col: fields[col] for col in WARRANTY_EDITABLE_COLUMNS if col in fields}
    if not updates:
        return 0
    assignments = ", ".join(f"{col} = ?" for col in updates)
    params = [*updates.values(), warranty_id]
    conn = get_connection()
    with conn:
        cur = conn.execute(
            f"UPDATE warranty_registrations SET {assignments} WHERE id = ?", params
        )
        updated = cur.rowcount
    conn.close()
    return updated


def soft_delete_warranty(warranty_id: int, actor: str | None = None) -> int:
    """Hide a warranty registration; the row and its call link stay in the DB."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE warranty_registrations
               SET deleted_at = ?, deleted_by = ?, hidden_with_customer = 0
               WHERE id = ? AND deleted_at IS NULL""",
            (_now(), actor, warranty_id),
        )
        hidden = cur.rowcount
    conn.close()
    return hidden


def restore_warranty(warranty_id: int) -> int:
    """Un-hide a warranty registration."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE warranty_registrations
               SET deleted_at = NULL, deleted_by = NULL, hidden_with_customer = 0
               WHERE id = ? AND deleted_at IS NOT NULL""",
            (warranty_id,),
        )
        restored = cur.rowcount
    conn.close()
    return restored


def set_warranty_status(warranty_id: int, status: str, actor: str | None = None) -> int:
    """Active ↔ cancelled, like the company system's "Cancel" button.

    Cancelling keeps the row visible with its status (it is a business state,
    not a deletion); `cancelled_at` / `cancelled_by` record who did it.
    """
    if status not in ("active", "cancelled"):
        raise ValueError(f"unknown warranty status {status!r}")
    stamp = (_now(), actor) if status == "cancelled" else (None, None)
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE warranty_registrations
               SET status = ?, cancelled_at = ?, cancelled_by = ?
               WHERE id = ? AND COALESCE(status, 'active') != ?""",
            (status, *stamp, warranty_id, status),
        )
        changed = cur.rowcount
    conn.close()
    return changed


def get_warranties_by_so_number(so_number: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT w.*, c.first_name, c.last_name, c.phone
           FROM warranty_registrations w LEFT JOIN customers c ON c.id = w.customer_id
           WHERE w.so_number = ? AND w.deleted_at IS NULL""",
        (so_number,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_warranties_by_customer(customer_id: int, include_deleted: bool = False) -> list[dict]:
    extra = "" if include_deleted else "AND deleted_at IS NULL"
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT * FROM warranty_registrations
            WHERE customer_id = ? {extra}
            ORDER BY date_of_purchase DESC""",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_warranties(include_deleted: bool = False) -> list[dict]:
    where = "" if include_deleted else "WHERE w.deleted_at IS NULL"
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT w.*, c.first_name, c.last_name, c.phone
            FROM warranty_registrations w
            LEFT JOIN customers c ON c.id = w.customer_id
            {where}
            ORDER BY w.date_of_purchase DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_deleted_warranties() -> list[dict]:
    """Hidden warranty registrations, newest hidden first — the 'trash' view."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT w.*, c.first_name, c.last_name, c.phone
           FROM warranty_registrations w
           LEFT JOIN customers c ON c.id = w.customer_id
           WHERE w.deleted_at IS NOT NULL
           ORDER BY w.deleted_at DESC"""
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


# ─── Sales orders ────────────────────────────────────────────────────────────

def save_sales_order(header: dict, lines: list[dict], actor: str | None = None) -> tuple[int, bool]:
    """Insert or update an SO by its number, replacing its lines.

    Returns (id, created). A hidden SO that is saved again comes back.
    """
    values = {col: header.get(col) for col in SO_HEADER_COLUMNS}
    if not values["so_number"]:
        raise ValueError("so_number is required")
    now = _now()
    conn = get_connection()
    with conn:
        row = conn.execute(
            "SELECT id FROM sales_orders WHERE so_number = ?", (values["so_number"],)
        ).fetchone()
        customer_id = header.get("customer_id")
        if row:
            so_id, created = row["id"], False
            assignments = ", ".join(f"{col} = ?" for col in values)
            conn.execute(
                f"""UPDATE sales_orders SET {assignments}, customer_id = ?, updated_at = ?,
                    deleted_at = NULL, deleted_by = NULL WHERE id = ?""",
                (*values.values(), customer_id, now, so_id),
            )
            conn.execute("DELETE FROM sales_order_lines WHERE sales_order_id = ?", (so_id,))
        else:
            cols = ", ".join(values)
            marks = ", ".join("?" for _ in values)
            cur = conn.execute(
                f"""INSERT INTO sales_orders ({cols}, customer_id, created_at, updated_at, created_by)
                    VALUES ({marks}, ?, ?, ?, ?)""",
                (*values.values(), customer_id, now, now, actor),
            )
            so_id, created = cur.lastrowid, True
        for position, line in enumerate(lines, 1):
            line_values = {col: line.get(col) for col in SO_LINE_COLUMNS}
            line_values["line_no"] = line_values["line_no"] or position
            conn.execute(
                f"""INSERT INTO sales_order_lines (sales_order_id, {", ".join(line_values)})
                    VALUES (?, {", ".join("?" for _ in line_values)})""",
                (so_id, *line_values.values()),
            )
    conn.close()
    return so_id, created


def get_sales_order(so_id: int | None = None, so_number: str | None = None,
                    include_deleted: bool = False) -> dict | None:
    """One SO with its lines under "lines", plus the linked customer's name."""
    where, param = ("so.id = ?", so_id) if so_id is not None else ("so.so_number = ?", so_number)
    extra = "" if include_deleted else "AND so.deleted_at IS NULL"
    conn = get_connection()
    row = conn.execute(
        f"""SELECT so.*, c.first_name, c.last_name, c.phone AS customer_phone
            FROM sales_orders so LEFT JOIN customers c ON c.id = so.customer_id
            WHERE {where} {extra}""",
        (param,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    order = dict(row)
    order["lines"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM sales_order_lines WHERE sales_order_id = ? ORDER BY line_no, id",
            (order["id"],),
        ).fetchall()
    ]
    conn.close()
    return order


def _so_search_sql(search: str | None, customer_id: int | None, include_deleted: bool) -> tuple[str, list]:
    where, params = [], []
    if not include_deleted:
        where.append("so.deleted_at IS NULL")
    if customer_id is not None:
        where.append("so.customer_id = ?")
        params.append(customer_id)
    if search:
        like = f"%{search.strip()}%"
        where.append(
            "(so.so_number LIKE ? OR so.sell_to_name LIKE ? OR so.ship_to_name LIKE ? "
            "OR so.ship_to_phone LIKE ? OR so.external_doc LIKE ? OR so.customer_po_no LIKE ? "
            "OR EXISTS (SELECT 1 FROM sales_order_lines l WHERE l.sales_order_id = so.id "
            "AND (l.item_no LIKE ? OR l.description LIKE ?)))"
        )
        params.extend([like] * 8)
    return ("WHERE " + " AND ".join(where)) if where else "", params


def list_sales_orders(search: str | None = None, customer_id: int | None = None,
                      limit: int | None = None, offset: int = 0,
                      include_deleted: bool = False) -> list[dict]:
    """SO headers newest first (by order date), with line count and customer name."""
    where_sql, params = _so_search_sql(search, customer_id, include_deleted)
    sql = f"""SELECT so.*, c.first_name, c.last_name,
                     (SELECT COUNT(*) FROM sales_order_lines l WHERE l.sales_order_id = so.id) AS line_count
              FROM sales_orders so LEFT JOIN customers c ON c.id = so.customer_id
              {where_sql}
              ORDER BY COALESCE(so.order_date, so.document_date, so.created_at) DESC, so.id DESC"""
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [int(limit), int(offset)]
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_sales_orders(search: str | None = None, customer_id: int | None = None,
                       include_deleted: bool = False) -> int:
    where_sql, params = _so_search_sql(search, customer_id, include_deleted)
    conn = get_connection()
    n = conn.execute(f"SELECT COUNT(*) FROM sales_orders so {where_sql}", params).fetchone()[0]
    conn.close()
    return int(n or 0)


def get_deleted_sales_orders() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sales_orders WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def soft_delete_sales_order(so_id: int, actor: str | None = None) -> int:
    """Hide an SO (the row and its lines stay — same policy as customers)."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "UPDATE sales_orders SET deleted_at = ?, deleted_by = ? WHERE id = ? AND deleted_at IS NULL",
            (_now(), actor, so_id),
        )
        hidden = cur.rowcount
    conn.close()
    return hidden


def restore_sales_order(so_id: int) -> int:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "UPDATE sales_orders SET deleted_at = NULL, deleted_by = NULL WHERE id = ? AND deleted_at IS NOT NULL",
            (so_id,),
        )
        restored = cur.rowcount
    conn.close()
    return restored


def get_sales_orders_for_customers(customer_ids: list[int]) -> dict[int, list[dict]]:
    """{customer_id: [SO headers newest first]} — for the case dialog / customer page."""
    ids = sorted({int(i) for i in customer_ids if i})
    if not ids:
        return {}
    marks = ", ".join("?" for _ in ids)
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT so.*, (SELECT COUNT(*) FROM sales_order_lines l WHERE l.sales_order_id = so.id) AS line_count
            FROM sales_orders so
            WHERE so.customer_id IN ({marks}) AND so.deleted_at IS NULL
            ORDER BY COALESCE(so.order_date, so.document_date, so.created_at) DESC""",
        ids,
    ).fetchall()
    conn.close()
    grouped: dict[int, list[dict]] = {i: [] for i in ids}
    for row in rows:
        grouped[row["customer_id"]].append(dict(row))
    return grouped


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


def get_case_detail(case_id: int) -> dict | None:
    """One case plus its customer's name/phone and call count (for the case
    panel and the Discord message)."""
    conn = get_connection()
    row = conn.execute(
        """SELECT cs.*, c.first_name, c.last_name, c.phone,
                  (SELECT COUNT(*) FROM calls cl WHERE cl.case_id = cs.id) AS call_count
           FROM cases cs
           LEFT JOIN customers c ON c.id = cs.customer_id
           WHERE cs.id = ?""",
        (case_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_case(case_id: int, username: str, name: str) -> bool:
    """Make `username` the owner of an unclaimed, not-closed case.

    The check and the write are one UPDATE, so two people pressing the button
    at the same moment cannot both win: the second finds `assignee_username`
    already set and gets False.
    """
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE cases
               SET assignee_username = ?, assignee_name = ?, assigned_at = ?, updated_at = ?
               WHERE id = ? AND assignee_username IS NULL AND status != 'closed'""",
            (username, name, now, now, case_id),
        )
    conn.close()
    return cur.rowcount == 1


def release_case(case_id: int, expected_username: str) -> bool:
    """Clear the owner, but only if it is still `expected_username` — a page
    that went stale while someone else re-claimed the case changes nothing."""
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE cases
               SET assignee_username = NULL, assignee_name = NULL, assigned_at = NULL,
                   updated_at = ?
               WHERE id = ? AND assignee_username = ? COLLATE NOCASE""",
            (now, case_id, expected_username),
        )
    conn.close()
    return cur.rowcount == 1


def set_case_status_as_assignee(case_id: int, status: str, username: str, name: str) -> bool:
    """Change a case's status on behalf of its owner.

    The owner check lives in the WHERE clause, so it holds even when the
    page that sent the request is out of date. Closing stamps `closed_by` /
    `closed_at`; any other status clears them.
    """
    now = _now()
    closed_by, closed_at = (name, now) if status == "closed" else (None, None)
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """UPDATE cases
               SET status = ?, closed_by = ?, closed_at = ?, updated_at = ?
               WHERE id = ? AND assignee_username = ? COLLATE NOCASE""",
            (status, closed_by, closed_at, now, case_id, username),
        )
    conn.close()
    return cur.rowcount == 1


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


def get_calls_for_cases(case_ids: list[int]) -> dict[int, list[dict]]:
    """{case_id: [calls oldest-first]} for a page of cases, in one query.

    Lets the case list say what each case is about (summary, next step,
    urgency) without a query per row.
    """
    ids = sorted({int(i) for i in case_ids})
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT id, case_id, filename, summary, topic, topic_detail, sentiment,
                   anomaly_detected, anomaly_reason, anomaly_severity,
                   agent_performance, transcript, created_at
            FROM calls WHERE case_id IN ({placeholders})
            ORDER BY created_at ASC, id ASC""",
        ids,
    ).fetchall()
    conn.close()
    grouped: dict[int, list[dict]] = {case_id: [] for case_id in ids}
    for row in rows:
        grouped[row["case_id"]].append(dict(row))
    return grouped


def get_calls_by_case(case_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM calls WHERE case_id = ? ORDER BY created_at ASC",
        (case_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _case_filters(
    status: str | None,
    search: str | None,
    assignee: str | None,
    unassigned: bool,
) -> tuple[str, list]:
    """WHERE clause shared by `get_all_cases` and `count_cases`."""
    where: list[str] = []
    params: list = []
    if status:
        where.append("cs.status = ?")
        params.append(status)
    if search:
        like = f"%{search.strip()}%"
        where.append(
            "(cs.subject LIKE ? OR c.first_name LIKE ? OR "
            "c.last_name LIKE ? OR c.phone LIKE ? OR cs.assignee_name LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    if assignee:
        where.append("cs.assignee_username = ? COLLATE NOCASE")
        params.append(assignee)
    if unassigned:
        where.append("cs.assignee_username IS NULL")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


def get_all_cases(
    limit: int | None = None,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    assignee: str | None = None,
    unassigned: bool = False,
) -> list[dict]:
    """Return cases newest-first.

    Default behavior (no kwargs) is unchanged — returns every case. Optional
    `limit`, `status`, and `search` let the dashboard stay responsive when the
    cases table grows large (search matches subject, customer name, phone or
    assignee). `assignee` keeps one person's cases; `unassigned` keeps the
    ones nobody has claimed yet.
    """
    where_sql, params = _case_filters(status, search, assignee, unassigned)

    sql = f"""
        SELECT cs.*,
               c.first_name, c.last_name, c.phone,
               COUNT(cl.id) as call_count
        FROM cases cs
        LEFT JOIN customers c ON c.id = cs.customer_id
        LEFT JOIN calls cl ON cl.case_id = cs.id
        {where_sql}
        GROUP BY cs.id
        ORDER BY cs.updated_at DESC
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

    conn = get_connection()
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_cases(
    status: str | None = None,
    search: str | None = None,
    assignee: str | None = None,
    unassigned: bool = False,
) -> int:
    """Return number of cases matching optional status/search filters."""
    where_sql, params = _case_filters(status, search, assignee, unassigned)

    conn = get_connection()
    n = conn.execute(
        f"""SELECT COUNT(DISTINCT cs.id)
            FROM cases cs
            LEFT JOIN customers c ON c.id = cs.customer_id
            {where_sql}""",
        tuple(params),
    ).fetchone()[0]
    conn.close()
    return int(n or 0)


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
    """Return counts of cases by status: {'open': n, 'follow_up': n, 'closed': n, 'total': n}.

    `unassigned` counts the not-yet-closed cases nobody has claimed.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM cases GROUP BY status"
    ).fetchall()
    unassigned = conn.execute(
        "SELECT COUNT(*) FROM cases WHERE status != 'closed' AND assignee_username IS NULL"
    ).fetchone()[0]
    conn.close()
    counts = {r["status"]: r["n"] for r in rows}
    counts["total"] = sum(counts.values())
    for s in ("open", "follow_up", "closed"):
        counts.setdefault(s, 0)
    counts["unassigned"] = unassigned
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


# ── Audit trail ──────────────────────────────────────────────────────────
#
# Append-only history of who changed what. Rows are never updated or deleted,
# which is also why customers and warranties are hidden rather than removed —
# a log that points at rows which no longer exist explains nothing.


def log_action(
    action: str,
    entity: str,
    entity_id: int | None = None,
    entity_label: str | None = None,
    actor: str | None = None,
    actor_role: str | None = None,
    changes: dict | None = None,
) -> int:
    """Append one row to the audit trail.

    `action` is create / update / delete / restore, `entity` is the kind of row
    that changed (customer, warranty, ...), and `changes` is a small dict that is
    stored as JSON — {field: [before, after]} for an update, a snapshot of the
    identifying fields otherwise. Nothing here is ever updated or deleted.
    """
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO audit_log
               (actor, actor_role, action, entity, entity_id, entity_label, changes, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                actor,
                actor_role,
                action,
                entity,
                entity_id,
                entity_label,
                json.dumps(changes, ensure_ascii=False) if changes else None,
                _now(),
            ),
        )
    conn.close()
    return cur.lastrowid


def get_audit_log(
    entity: str | None = None,
    entity_id: int | None = None,
    limit: int = 200,
) -> list[dict]:
    """Audit entries, newest first, optionally narrowed to one entity or row."""
    clauses = []
    params: list = []
    if entity:
        clauses.append("entity = ?")
        params.append(entity)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", params
    ).fetchall()
    conn.close()

    entries = []
    for row in rows:
        entry = dict(row)
        try:
            entry["changes"] = json.loads(entry["changes"]) if entry["changes"] else {}
        except json.JSONDecodeError:  # pragma: no cover - defensive
            entry["changes"] = {}
        entries.append(entry)
    return entries


def count_audit_entries(entity: str | None = None) -> int:
    conn = get_connection()
    if entity:
        row = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity = ?", (entity,)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
    conn.close()
    return int(row[0] or 0)


# ── Users (staff login accounts) ─────────────────────────────────────────
#
# Password hashes are PBKDF2-SHA256 strings produced by smartvoice.auth —
# this module never sees a plaintext password.


def create_user(
    username: str,
    display_name: str,
    role: str,
    password_hash: str,
    is_active: bool = True,
) -> int:
    """Insert a staff account. Raises sqlite3.IntegrityError on duplicate username."""
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO users (
                username, display_name, role, password_hash,
                is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username.strip(), display_name.strip(), role,
             password_hash, 1 if is_active else 0, now, now),
        )
        new_id = cur.lastrowid
    conn.close()
    return new_id


def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
        ((username or "").strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY is_active DESC, role, username COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_users() -> int:
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return int(n)


def count_active_admins(exclude_user_id: int | None = None) -> int:
    """Number of enabled Admin accounts, optionally ignoring one user id."""
    conn = get_connection()
    query = "SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = 'Admin'"
    params: list = []
    if exclude_user_id is not None:
        query += " AND id != ?"
        params.append(exclude_user_id)
    n = conn.execute(query, params).fetchone()[0]
    conn.close()
    return int(n)


def update_user(
    user_id: int,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> None:
    """Patch the editable profile fields of a user. Unset args are left as-is."""
    fields: list[str] = []
    params: list = []
    if display_name is not None:
        fields.append("display_name = ?")
        params.append(display_name.strip())
    if role is not None:
        fields.append("role = ?")
        params.append(role)
    if is_active is not None:
        fields.append("is_active = ?")
        params.append(1 if is_active else 0)
    if not fields:
        return

    fields.append("updated_at = ?")
    params.extend([_now(), user_id])
    conn = get_connection()
    with conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    conn.close()


def update_user_password(user_id: int, password_hash: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, _now(), user_id),
        )
    conn.close()


def touch_user_login(user_id: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user_id)
        )
    conn.close()


def delete_user(user_id: int) -> int:
    conn = get_connection()
    with conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted = cur.rowcount
    conn.close()
    return deleted
