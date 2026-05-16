"""Backfill: scrub leaked prompt-example tokens from existing `agent_performance`
rows in the calls table.

Earlier Typhoon-8B outputs frequently copied the in-prompt next_action example
verbatim (15,000 / #REG0012 / 081-987-9336). The runtime scrubber in
`ollama_client._scrub_prompt_example_leakage` only protects new calls — this
script applies the same scrubber to historical rows.

Usage:
    # dry-run (default) — prints what would change, no DB write
    python scripts/scrub_existing_next_actions.py

    # apply changes
    python scripts/scrub_existing_next_actions.py --apply
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartvoice import db  # noqa: E402
from smartvoice.ollama_client import _scrub_prompt_example_leakage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="Persist changes (default: dry-run, prints diff only)",
    )
    args = parser.parse_args()

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT id, filename, transcript, agent_performance "
        "FROM calls WHERE status = 'done' AND agent_performance IS NOT NULL"
    ).fetchall()

    changed = 0
    for row in rows:
        try:
            ap = json.loads(row["agent_performance"])
        except (json.JSONDecodeError, TypeError):
            continue
        old_action = ap.get("next_action") or ""
        if not old_action:
            continue
        new_action = _scrub_prompt_example_leakage(old_action, row["transcript"] or "")
        if new_action == old_action:
            continue
        changed += 1
        print(f"[{row['id']}] {row['filename']}")
        print(f"  OLD: {old_action}")
        print(f"  NEW: {new_action}")
        print()
        if args.apply:
            ap["next_action"] = new_action
            conn.execute(
                "UPDATE calls SET agent_performance = ? WHERE id = ?",
                (json.dumps(ap, ensure_ascii=False), row["id"]),
            )

    if args.apply:
        conn.commit()
        print(f"Updated {changed} row(s).")
    else:
        print(f"Dry-run: {changed} row(s) would be updated. Re-run with --apply to persist.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
