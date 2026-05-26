"""Backfill: re-classify `topic_detail` for existing product-issue calls.

Older calls were processed before the `topic_detail` field existed, so they
have `topic = "แจ้งปัญหาสินค้า"` but `topic_detail = NULL`. This script asks
the LLM to assign a damage category (ผ้าขาด / เตียงหัก / …) from the
controlled vocabulary in `smartvoice.ollama_client.TOPIC_DETAIL_CHOICES`,
then writes it back to the DB — without re-running Whisper or diarization.

Requires Ollama to be running locally (same model as the pipeline).

Usage:
    # Dry-run (default): print what each call would be classified as, no DB write
    python scripts/backfill_topic_detail.py

    # Persist
    python scripts/backfill_topic_detail.py --apply

    # Limit to first N rows (useful for sampling before a full run)
    python scripts/backfill_topic_detail.py --limit 10 --apply
"""

import argparse
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr so Thai labels print correctly on Windows consoles
# (cp874 default codepage can't encode characters like → and many Thai glyphs)
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartvoice import db  # noqa: E402
from smartvoice.ollama_client import (  # noqa: E402
    PRODUCT_ISSUE_TOPIC,
    TOPIC_DETAIL_CHOICES,
    chat,
    extract_json,
    normalize_topic_detail,
)


_SYSTEM = (
    "คุณคือ Call Center Analyst AI ของบริษัท Omazz (กลุ่มบริษัทที่นอนโลตัส) "
    "ตอบเป็น JSON เท่านั้น"
)


def _build_user_prompt(transcript: str) -> str:
    choices = "\n".join(f'   - "{c}"' for c in TOPIC_DETAIL_CHOICES)
    return f"""บทสนทนา call center ที่ลูกค้าแจ้งปัญหาสินค้า:

{transcript}

== งานของคุณ ==
ระบุ "ประเภทความเสียหายหลัก" ที่ลูกค้าโทรมาแจ้ง โดยเลือก 1 ค่าจากรายการนี้
(ห้ามแต่งค่าเอง — ต้องเลือกจากรายการเท่านั้น):
{choices}

⚠️ ถ้ามีหลายความเสียหายในสายเดียว → เลือก **ความเสียหายหลัก** ที่ลูกค้า
โทรมาแจ้งเป็นเรื่องหลัก
⚠️ ถ้าความเสียหายไม่เข้า 6 หมวดข้างต้น → ตอบ "อื่นๆ"

ตอบ JSON:
{{"topic_detail": "..."}}
"""


def _classify(transcript: str) -> str:
    """Run a focused LLM call and clamp the result to the allowed vocabulary."""
    user = _build_user_prompt(transcript or "")
    try:
        raw = chat(_SYSTEM, user)
        result = extract_json(raw)
    except Exception as exc:
        print(f"  ! LLM call/parse failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        result = {}
    return normalize_topic_detail(PRODUCT_ISSUE_TOPIC, result.get("topic_detail", ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true",
        help="Persist changes (default: dry-run, prints classification only)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after processing the first N matching calls",
    )
    args = parser.parse_args()

    conn = db.get_connection()
    query = (
        "SELECT id, filename, transcript FROM calls "
        "WHERE status = 'done' AND topic = ? "
        "  AND (topic_detail IS NULL OR topic_detail = '') "
        "ORDER BY id"
    )
    params: tuple = (PRODUCT_ISSUE_TOPIC,)
    if args.limit:
        query += " LIMIT ?"
        params = params + (args.limit,)

    rows = conn.execute(query, params).fetchall()
    total = len(rows)
    if total == 0:
        print("No calls to backfill — every product-issue call already has topic_detail.")
        conn.close()
        return 0

    print(f"Found {total} call(s) to classify"
          f"{' (dry-run, no DB write)' if not args.apply else ''}\n")

    bucket: dict[str, int] = {}
    skipped = 0
    for idx, row in enumerate(rows, 1):
        transcript = row["transcript"] or ""
        if not transcript.strip():
            print(f"[{idx}/{total}] id={row['id']} {row['filename']}: skipped (empty transcript)")
            skipped += 1
            continue

        detail = _classify(transcript)
        bucket[detail] = bucket.get(detail, 0) + 1
        print(f"[{idx}/{total}] id={row['id']} {row['filename']} → {detail}")

        if args.apply:
            conn.execute(
                "UPDATE calls SET topic_detail = ?, updated_at = ? WHERE id = ?",
                (detail, db._now(), row["id"]),
            )

    if args.apply:
        conn.commit()

    print("\n── Summary ──")
    for label in TOPIC_DETAIL_CHOICES:
        n = bucket.get(label, 0)
        if n:
            print(f"  {label:25s} {n}")
    if skipped:
        print(f"  (skipped, empty transcript): {skipped}")
    print()
    if args.apply:
        print(f"Updated {sum(bucket.values())} row(s).")
    else:
        print(f"Dry-run only. Re-run with --apply to persist.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
