"""Compare Ollama models on the analysis step — without touching the database.

Re-runs the 4 analyses (`ollama_client.analyze_transcript`: summary/topic,
sentiment, agent QA + next action, anomaly) on transcripts that are already in
the DB, once per model, and writes a side-by-side report. No Whisper, no
diarization, and the DB is opened read-only — the stored results stay as they are.

This is the check CLAUDE.md asks for before a prompt or model change: the
rules in `insight_rules` were tuned on Typhoon 8B's habits, so a new model has
to be read call by call, not just timed.

Usage:
    # Current OLLAMA_MODEL vs the candidate, every processed call
    python scripts/compare_llm_models.py --models scb10x/llama3.1-typhoon2-8b-instruct scb10x/typhoon2.1-gemma3-12b

    # A quick sample
    python scripts/compare_llm_models.py --models A B --limit 3

Output (default `data/llm_compare/<timestamp>/`, gitignored with the rest of data/):
    report.md   per-model speed, JSON failures, rule rejections, agreement, and every call side by side
    calls.csv   one row per call × model
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout/stderr so Thai prints on Windows consoles (cp874 can't encode → and friends)
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from smartvoice import labels, ollama_client  # noqa: E402

FIELDS = (
    "topic", "topic_detail", "sentiment", "qa_score", "anomaly",
    "next_action", "summary", "sentiment_reason", "seconds",
)


# ── Input ────────────────────────────────────────────────────────────────

def load_calls(db_path: str, limit: int | None = None, call_ids: list[int] | None = None) -> list[dict]:
    """Processed calls with a transcript, oldest first. Opens the DB read-only."""
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    sql = (
        "SELECT id, filename, transcript FROM calls "
        "WHERE status = 'done' AND transcript IS NOT NULL AND transcript != ''"
    )
    params: list = []
    if call_ids:
        sql += f" AND id IN ({','.join('?' * len(call_ids))})"
        params.extend(call_ids)
    sql += " ORDER BY id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


# ── Running one model ────────────────────────────────────────────────────

class RequestLog:
    """What the model actually answered, before `insight_rules` cleaned it up."""

    def __init__(self):
        self.requests = 0
        self.failures = 0          # answers with no JSON object — the analysis fell back to defaults
        self.raw: list[dict] = []

    def reset_call(self):
        self.raw = []


@contextmanager
def observe(log: RequestLog):
    """Count requests and keep each raw JSON answer, without changing behaviour."""
    real_chat, real_extract = ollama_client.chat, ollama_client.extract_json

    def chat(*args, **kwargs):
        log.requests += 1
        return real_chat(*args, **kwargs)

    def extract_json(raw):
        try:
            value = real_extract(raw)
        except Exception:
            log.failures += 1
            raise
        log.raw.append(value)
        return value

    ollama_client.chat, ollama_client.extract_json = chat, extract_json
    try:
        yield log
    finally:
        ollama_client.chat, ollama_client.extract_json = real_chat, real_extract


def rule_rejections(raw_answers: list[dict], result: dict) -> list[str]:
    """Claims the model made that the verification rules threw out.

    A model that keeps inventing quotes looks fine in the final table (the
    rules hide it) but is less reliable — so count it.
    """
    rejected = []
    for raw in raw_answers:
        if "customer_quote" in raw:
            quote = " ".join(str(raw.get("customer_quote") or "").split())
            if quote and "ลูกค้าพูดว่า" not in (result.get("sentiment_reason") or ""):
                rejected.append("sentiment: quote not said by the customer")
        if "anomaly_detected" in raw and str(raw.get("anomaly_detected")).strip().lower() in ("true", "1", "yes"):
            if not result.get("anomaly_detected"):
                rejected.append("anomaly: flag without a matching quote/keyword")
    return rejected


def summarize_result(result: dict) -> dict:
    """The fields a person compares, flattened for the report."""
    try:
        perf = json.loads(result.get("agent_performance") or "{}")
    except (TypeError, json.JSONDecodeError):
        perf = {}
    perf = perf if isinstance(perf, dict) else {}
    anomaly = ""
    if result.get("anomaly_detected"):
        anomaly = f"{labels.severity(result.get('anomaly_severity'))}: {result.get('anomaly_reason') or ''}"
    return {
        "topic": result.get("topic") or "",
        "topic_detail": result.get("topic_detail") or "",
        "sentiment": result.get("sentiment") or "",
        "qa_score": perf.get("overall_score", ""),
        "anomaly": anomaly,
        "next_action": perf.get("next_action") or "",
        "summary": result.get("summary") or "",
        "sentiment_reason": result.get("sentiment_reason") or "",
    }


def _ollama(path: str, payload: dict | None = None, method: str = "post") -> dict:
    url = f"{ollama_client._base_url()}{path}"
    response = requests.post(url, json=payload, timeout=600) if method == "post" else requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def gpu_share(model: str) -> str:
    """How much of the loaded model sits in VRAM (from Ollama's /api/ps)."""
    try:
        for m in _ollama("/api/ps", method="get").get("models", []):
            if m.get("name", "").startswith(model) or m.get("model", "").startswith(model):
                size, vram = m.get("size") or 0, m.get("size_vram") or 0
                share = f"{vram / size:.0%}" if size else "?"
                return f"{size / 1e9:.1f} GB loaded, {share} on GPU"
    except requests.RequestException:
        pass
    return "unknown"


def unload(model: str) -> None:
    """Free VRAM before the next model loads, so each model is timed alone."""
    try:
        _ollama("/api/generate", {"model": model, "keep_alive": 0})
    except requests.RequestException:
        pass


def run_model(model: str, calls: list[dict], progress=print) -> dict:
    """Analyse every call with `model`. Returns per-call rows and run totals."""
    os.environ["OLLAMA_MODEL"] = model
    # Load the model first so the first call's time doesn't include loading it.
    load_start = time.time()
    _ollama("/api/generate", {"model": model, "prompt": "", "keep_alive": "10m"})
    load_seconds = time.time() - load_start
    memory = gpu_share(model)

    log = RequestLog()
    rows, rejections = [], 0
    with observe(log):
        for i, call in enumerate(calls, 1):
            log.reset_call()
            start = time.time()
            result = ollama_client.analyze_transcript(call["transcript"])
            seconds = time.time() - start
            rejected = rule_rejections(log.raw, result)
            rejections += len(rejected)
            row = {"call_id": call["id"], "filename": call["filename"], **summarize_result(result),
                   "seconds": round(seconds, 1), "rejected": "; ".join(rejected)}
            rows.append(row)
            progress(f"  [{model}] {i}/{len(calls)} call {call['id']} — {seconds:.0f}s")
    unload(model)
    total = sum(r["seconds"] for r in rows)
    return {
        "model": model,
        "rows": rows,
        "load_seconds": round(load_seconds, 1),
        "memory": memory,
        "total_seconds": round(total, 1),
        "avg_seconds": round(total / len(rows), 1) if rows else 0,
        "requests": log.requests,
        "json_failures": log.failures,
        "rule_rejections": rejections,
    }


# ── Report ───────────────────────────────────────────────────────────────

def agreement(runs: list[dict], field: str) -> str:
    """Share of calls where every model gave the same value for `field`."""
    if len(runs) < 2 or not runs[0]["rows"]:
        return "-"
    same = sum(
        1 for rows in zip(*(run["rows"] for run in runs))
        if len({str(r[field]) for r in rows}) == 1
    )
    return f"{same}/{len(runs[0]['rows'])}"


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value not in (None, "") else "—"


def render_markdown(runs: list[dict], db_path: str) -> str:
    out = [
        "# เทียบโมเดล LLM บนบทสนทนาที่มีอยู่",
        "",
        f"สร้างเมื่อ {datetime.now():%d/%m/%Y %H:%M} • ฐานข้อมูล `{db_path}` (อ่านอย่างเดียว) • "
        f"{len(runs[0]['rows']) if runs else 0} สาย",
        "",
        "## ภาพรวม",
        "",
        "| โมเดล | เวลาเฉลี่ย/สาย | รวม | โหลดโมเดล | หน่วยความจำ | คำขอ | JSON พัง | ถูกกฎตรวจทิ้ง |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        out.append(
            f"| `{run['model']}` | {run['avg_seconds']} s | {run['total_seconds']} s | {run['load_seconds']} s "
            f"| {run['memory']} | {run['requests']} | {run['json_failures']} | {run['rule_rejections']} |"
        )
    out += [
        "",
        "*JSON พัง* = คำตอบที่ไม่มี JSON เลย ระบบจึงใช้ค่าว่างแทน • "
        "*ถูกกฎตรวจทิ้ง* = โมเดลอ้างคำพูดหรือแจ้งความผิดปกติที่ไม่มีในสาย แล้ว `insight_rules` ตัดออก (ยิ่งน้อยยิ่งน่าเชื่อ)",
        "",
        "**ตอบตรงกันทุกโมเดล:** "
        + " • ".join(f"{name} {agreement(runs, field)}" for name, field in (
            ("เรื่อง", "topic"), ("ประเภทปัญหา", "topic_detail"),
            ("อารมณ์ลูกค้า", "sentiment"), ("คะแนน QA", "qa_score"), ("ความผิดปกติ", "anomaly"),
        )),
        "",
        "## รายสาย",
    ]
    for rows in zip(*(run["rows"] for run in runs)):
        first = rows[0]
        out += ["", f"### สาย {first['call_id']} — `{first['filename']}`", "",
                "| | " + " | ".join(f"`{run['model']}`" for run in runs) + " |",
                "|---|" + "---|" * len(runs)]
        for name, field in (
            ("เรื่อง", "topic"), ("ประเภทปัญหา", "topic_detail"), ("อารมณ์ลูกค้า", "sentiment"),
            ("คะแนน QA (เต็ม 10)", "qa_score"), ("ความผิดปกติ", "anomaly"), ("สิ่งที่ต้องทำต่อ", "next_action"),
            ("สรุปสาย", "summary"), ("เหตุผลอารมณ์", "sentiment_reason"), ("ถูกกฎตรวจทิ้ง", "rejected"),
            ("เวลา (วินาที)", "seconds"),
        ):
            out.append(f"| {name} | " + " | ".join(_cell(r[field]) for r in rows) + " |")
    return "\n".join(out) + "\n"


def write_csv(runs: list[dict], path: Path) -> None:
    columns = ["model", "call_id", "filename", *FIELDS, "rejected"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for run in runs:
            for row in run["rows"]:
                writer.writerow({"model": run["model"], **row})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names, the current one first")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/smartvoice.db"))
    parser.add_argument("--limit", type=int, help="only the first N processed calls")
    parser.add_argument("--calls", type=int, nargs="+", help="only these call ids")
    parser.add_argument("--out", help="output folder (default data/llm_compare/<timestamp>)")
    args = parser.parse_args(argv)

    calls = load_calls(args.db, args.limit, args.calls)
    if not calls:
        print("ไม่มีสายที่ประมวลผลเสร็จและมีบทสนทนา — ไม่มีอะไรให้เทียบ")
        return 1
    out_dir = Path(args.out or f"data/llm_compare/{datetime.now():%Y%m%d_%H%M%S}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"เทียบ {len(args.models)} โมเดล บน {len(calls)} สาย (DB อ่านอย่างเดียว: {args.db})")
    runs = []
    for model in args.models:
        print(f"→ {model}")
        runs.append(run_model(model, calls))

    (out_dir / "report.md").write_text(render_markdown(runs, args.db), encoding="utf-8")
    write_csv(runs, out_dir / "calls.csv")
    for run in runs:
        print(f"{run['model']}: เฉลี่ย {run['avg_seconds']} s/สาย, JSON พัง {run['json_failures']}, "
              f"ถูกกฎตรวจทิ้ง {run['rule_rejections']}, {run['memory']}")
    print(f"รายงาน: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
