"""Compare Whisper (STT) models on real call audio — without touching the database.

Runs the production transcription step (`stt.transcribe.transcribe_hf`: same
audio loading, noise reduction, 15 s chunks, prompt and hallucination filter)
once per model on the stored audio of processed calls, and writes the
transcripts side by side. No diarization, no LLM, and the DB is opened
read-only — the stored transcripts stay as they are.

Without hand-checked transcripts there is no "right answer", so the report
shows signals instead: speed, VRAM, how much text came out per minute of
audio, domain words spelled correctly vs Whisper mistakes seen on real calls,
and how far each model's text is from the first model's. Read the
transcripts themselves before switching.

With hand-checked transcripts (`--refs DIR` holding `<call_id>.txt`) the
report also gives each model's character error rate (CER) on those calls.

Usage:
    # Current WHISPER_MODEL vs the candidates, every processed call
    python scripts/compare_stt_models.py --models biodatlab/distill-whisper-th-large-v3 typhoon-ai/typhoon-whisper-turbo

    # A quick sample, with hand-checked transcripts in data/stt_refs/<call_id>.txt
    python scripts/compare_stt_models.py --models A B --calls 284 289 --refs data/stt_refs

    # A model that loops on our domain-word prompt (Typhoon Large-v3) runs without it
    python scripts/compare_stt_models.py --models A typhoon-ai/typhoon-whisper-large-v3 --no-prompt typhoon-ai/typhoon-whisper-large-v3

Output (default `data/stt_compare/<timestamp>/`, gitignored: it holds real calls):
    report.md            per-model speed / VRAM / signals, then every call side by side
    calls.csv            one row per call × model
    <model>/<id>.txt     each transcript, for diffing in an editor
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

# Force UTF-8 stdout/stderr so Thai prints on Windows consoles (cp874 can't encode → and friends)
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from smartvoice.stt import audio as stt_audio, transcribe  # noqa: E402

# Words that should come out of these calls, with the spellings that count.
DOMAIN_TERMS = {
    "ที่นอน": ("ที่นอน",),
    "โลตัส": ("โลตัส", "lotus"),
    "Omazz": ("omazz", "โอมาซ", "โอมัซ", "โอมาส"),
    "Restonic": ("restonic", "เรสโทนิค", "เรสโตนิค", "เรสโทนิก"),
}
# Whisper mistakes seen on real calls (CLAUDE.md "Common Whisper errors").
# "โอมาสนา" is checked before "โอมาส" counts as Omazz — see domain_hits().
KNOWN_ERRORS = ("โอมาสนา", "โนโลตัส", "ฟิวทู", "ทีเนี่ย")

FIELDS = ("seconds", "audio_seconds", "rtf", "chars_per_min", "thai_ratio",
          "domain_terms", "known_errors", "similarity", "cer")


# ── Input ────────────────────────────────────────────────────────────────

def load_calls(db_path: str, limit: int | None = None, call_ids: list[int] | None = None) -> list[dict]:
    """Processed calls whose audio file still exists, oldest first. Opens the DB read-only."""
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    sql = "SELECT id, filename, file_path FROM calls WHERE status = 'done'"
    params: list = []
    if call_ids:
        sql += f" AND id IN ({','.join('?' * len(call_ids))})"
        params.extend(call_ids)
    sql += " ORDER BY id"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    rows = [r for r in rows if r["file_path"] and Path(r["file_path"]).exists()]
    return rows[:limit] if limit else rows


def load_references(refs_dir: str | None) -> dict[int, str]:
    """Hand-checked transcripts named `<call_id>.txt`."""
    if not refs_dir:
        return {}
    refs = {}
    for path in Path(refs_dir).glob("*.txt"):
        if path.stem.isdigit():
            refs[int(path.stem)] = path.read_text(encoding="utf-8")
    return refs


# ── Measuring a transcript ───────────────────────────────────────────────

_SPACE_RE = re.compile(r"\s+")
_THAI_RE = re.compile(r"[฀-๿]")


def squash(text: str) -> str:
    """Text without whitespace — Thai has no word spaces, so compare characters."""
    return _SPACE_RE.sub("", text or "").lower()


def domain_hits(text: str) -> dict[str, int]:
    """How often each domain word and each known mistake occurs."""
    lowered = (text or "").lower()
    hits = {error: lowered.count(error) for error in KNOWN_ERRORS}
    # A known mistake contains a correct-looking spelling ("โอมาสนา" ⊃ "โอมาส"); don't count it twice.
    cleaned = lowered
    for error in KNOWN_ERRORS:
        cleaned = cleaned.replace(error, " ")
    for term, spellings in DOMAIN_TERMS.items():
        hits[term] = sum(cleaned.count(s) for s in spellings)
    return hits


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, one row at a time."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(hypothesis: str, reference: str) -> float:
    """Character error rate against a hand-checked transcript (whitespace ignored)."""
    ref = squash(reference)
    return edit_distance(squash(hypothesis), ref) / len(ref) if ref else 0.0


def similarity(a: str, b: str) -> float:
    """How alike two transcripts are (0-1). Says nothing about which one is right."""
    return SequenceMatcher(None, squash(a), squash(b), autojunk=False).ratio()


def transcript_metrics(text: str, audio_seconds: float) -> dict:
    chars = squash(text)
    thai = len(_THAI_RE.findall(chars))
    hits = domain_hits(text)
    return {
        "chars_per_min": round(len(chars) / (audio_seconds / 60), 1) if audio_seconds else 0,
        "thai_ratio": round(thai / len(chars), 3) if chars else 0,
        "domain_terms": ", ".join(f"{t} {hits[t]}" for t in DOMAIN_TERMS if hits[t]) or "—",
        "known_errors": ", ".join(f"{e} {hits[e]}" for e in KNOWN_ERRORS if hits[e]) or "—",
        "_domain_total": sum(hits[t] for t in DOMAIN_TERMS),
        "_errors_total": sum(hits[e] for e in KNOWN_ERRORS),
    }


# ── Running one model ────────────────────────────────────────────────────

@contextmanager
def segment_level_output():
    """Keep Whisper's segments whole: production splits them into pseudo-words
    for diarization, which would glue the text together with no line breaks."""
    real_split = transcribe._split_segments_to_words
    transcribe._split_segments_to_words = lambda items: items
    try:
        yield
    finally:
        transcribe._split_segments_to_words = real_split


@contextmanager
def without_prompt():
    """Run with no domain-word prompt: Typhoon Whisper Large-v3 loops on one
    syllable ("ต้า ต้า ต้า …") when it gets our prompt_ids, and transcribes fine without."""
    real_prompt = transcribe._hf_prompt_ids
    transcribe._hf_prompt_ids = lambda *args, **kwargs: None
    try:
        yield
    finally:
        transcribe._hf_prompt_ids = real_prompt


def _mmss(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def segments_to_text(items: list[dict]) -> str:
    return "\n".join(
        f"[{_mmss(item.get('start'))}] {(item.get('word') or '').strip()}"
        for item in items if (item.get("word") or "").strip()
    )


def prepare_audio(calls: list[dict], progress=print) -> dict[int, tuple]:
    """Load + denoise each call once, exactly as production does, shared by every model."""
    prepared = {}
    for call in calls:
        audio, sr = stt_audio.load_audio_16k(call["file_path"])
        prepared[call["id"]] = (stt_audio.denoise(audio, sr, lambda _msg: None), sr)
        progress(f"  เตรียมเสียงสาย {call['id']} ({_mmss(len(audio) / sr)})")
    return prepared


def _cuda():
    try:
        import torch
        return torch if torch.cuda.is_available() else None
    except ImportError:
        return None


def run_model(model: str, calls: list[dict], audio: dict[int, tuple], progress=print,
              use_prompt: bool = True) -> dict:
    """Transcribe every call with `model`. Returns per-call rows and run totals."""
    transcribe.unload_model()
    transcribe.WHISPER_MODEL = model
    torch = _cuda()
    if torch:
        torch.cuda.reset_peak_memory_stats()

    with segment_level_output(), (nullcontext() if use_prompt else without_prompt()):
        # Load the model on one second of silence so the first call isn't timed with the load.
        _, sr = next(iter(audio.values()))
        load_start = time.time()
        transcribe.transcribe_hf(np.zeros(sr, dtype=np.float32), sr, lambda _msg: None)
        load_seconds = time.time() - load_start

        rows = []
        for i, call in enumerate(calls, 1):
            samples, sr = audio[call["id"]]
            audio_seconds = len(samples) / sr
            start = time.time()
            items = transcribe.transcribe_hf(samples, sr, lambda _msg: None)
            seconds = time.time() - start
            text = segments_to_text(items)
            rows.append({
                "call_id": call["id"], "filename": call["filename"], "text": text,
                "seconds": round(seconds, 1), "audio_seconds": round(audio_seconds, 1),
                "rtf": round(seconds / audio_seconds, 3) if audio_seconds else 0,
                **transcript_metrics(text, audio_seconds),
            })
            progress(f"  [{model}] {i}/{len(calls)} สาย {call['id']} ({_mmss(audio_seconds)}) — {seconds:.0f}s")

    peak = f"{torch.cuda.max_memory_allocated() / 1e9:.1f} GB" if torch else "CPU"
    transcribe.unload_model()
    total = sum(r["seconds"] for r in rows)
    audio_total = sum(r["audio_seconds"] for r in rows)
    return {
        "model": model if use_prompt else f"{model} (no prompt)",
        "rows": rows,
        "load_seconds": round(load_seconds, 1),
        "peak_vram": peak,
        "total_seconds": round(total, 1),
        "rtf": round(total / audio_total, 3) if audio_total else 0,
        "domain_total": sum(r["_domain_total"] for r in rows),
        "errors_total": sum(r["_errors_total"] for r in rows),
    }


def score_runs(runs: list[dict], references: dict[int, str]) -> None:
    """Fill each row's similarity to the first model and CER against a reference."""
    base = {r["call_id"]: r["text"] for r in runs[0]["rows"]} if runs else {}
    for run in runs:
        for row in run["rows"]:
            row["similarity"] = round(similarity(row["text"], base[row["call_id"]]), 3)
            ref = references.get(row["call_id"])
            row["cer"] = round(cer(row["text"], ref), 4) if ref else ""
        scored = [r for r in run["rows"] if r["cer"] != ""]
        run["cer"] = round(sum(r["cer"] for r in scored) / len(scored), 4) if scored else ""


# ── Report ───────────────────────────────────────────────────────────────

def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def _pct(value) -> str:
    return f"{value:.1%}" if value != "" else "—"


def render_markdown(runs: list[dict], db_path: str, references: dict[int, str]) -> str:
    n_calls = len(runs[0]["rows"]) if runs else 0
    audio_total = sum(r["audio_seconds"] for r in runs[0]["rows"]) if runs else 0
    out = [
        "# เทียบโมเดลถอดเสียง (STT) บนไฟล์เสียงจริง",
        "",
        f"สร้างเมื่อ {datetime.now():%d/%m/%Y %H:%M} • ฐานข้อมูล `{db_path}` (อ่านอย่างเดียว) • "
        f"{n_calls} สาย รวมเสียง {_mmss(audio_total)} นาที • "
        f"บทถอดเสียงที่ตรวจแก้แล้ว {len(references)} สาย",
        "",
        "## ภาพรวม",
        "",
        "| โมเดล | เวลาถอดเสียงรวม | เวลา/นาทีเสียง | โหลดโมเดล | VRAM สูงสุด | คำในโดเมน | คำที่ Whisper เคยถอดผิด | CER |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        out.append(
            f"| `{run['model']}` | {run['total_seconds']} s | {run['rtf'] * 60:.1f} s | {run['load_seconds']} s "
            f"| {run['peak_vram']} | {run['domain_total']} | {run['errors_total']} | {_pct(run.get('cer', ''))} |"
        )
    out += [
        "",
        "*คำในโดเมน* = ที่นอน / โลตัส / Omazz / Restonic ที่สะกดถูก (ยิ่งมากยิ่งดี ถ้าพูดจริงในสาย) • "
        f"*คำที่ Whisper เคยถอดผิด* = {' / '.join(KNOWN_ERRORS)} (ยิ่งน้อยยิ่งดี) • "
        "*CER* = อัตราตัวอักษรผิดเทียบกับบทที่คนตรวจแก้ (มีเฉพาะสายที่มีไฟล์ใน --refs)",
        "",
        "ตัวเลขเหล่านี้เป็นแค่สัญญาณ — **ต้องอ่านบทถอดเสียงจริงด้านล่าง** โดยเฉพาะชื่อสินค้า เบอร์โทร ตัวเลขเงิน และวันที่",
        "",
        "## รายสาย",
    ]
    for rows in zip(*(run["rows"] for run in runs)):
        first = rows[0]
        out += ["", f"### สาย {first['call_id']} ({_mmss(first['audio_seconds'])}) — `{first['filename']}`", "",
                "| | " + " | ".join(f"`{run['model']}`" for run in runs) + " |",
                "|---|" + "---|" * len(runs)]
        for name, field in (
            ("เวลาถอดเสียง (วินาที)", "seconds"), ("ตัวอักษร/นาที", "chars_per_min"),
            ("สัดส่วนอักษรไทย", "thai_ratio"), ("คำในโดเมน", "domain_terms"),
            ("คำที่เคยถอดผิด", "known_errors"), ("เหมือนโมเดลแรก", "similarity"),
        ):
            out.append(f"| {name} | " + " | ".join(str(r[field]) for r in rows) + " |")
        if first["call_id"] in references:
            out.append("| CER | " + " | ".join(_pct(r["cer"]) for r in rows) + " |")
        for run, row in zip(runs, rows):
            out += ["", f"<details><summary><code>{run['model']}</code></summary>", "", "```text",
                    row["text"] or "(ไม่มีข้อความ)", "```", "", "</details>"]
    return "\n".join(out) + "\n"


def write_outputs(runs: list[dict], out_dir: Path) -> None:
    columns = ["model", "call_id", "filename", *FIELDS]
    with (out_dir / "calls.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for run in runs:
            for row in run["rows"]:
                writer.writerow({"model": run["model"], **row})
    for run in runs:
        folder = out_dir / _slug(run["model"])
        folder.mkdir(parents=True, exist_ok=True)
        for row in run["rows"]:
            (folder / f"{row['call_id']}.txt").write_text(row["text"] + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", required=True, help="Hugging Face Whisper models, the current one first")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/smartvoice.db"))
    parser.add_argument("--limit", type=int, help="only the first N processed calls")
    parser.add_argument("--calls", type=int, nargs="+", help="only these call ids")
    parser.add_argument("--refs", help="folder of hand-checked transcripts named <call_id>.txt")
    parser.add_argument("--out", help="output folder (default data/stt_compare/<timestamp>)")
    parser.add_argument("--no-prompt", nargs="+", default=[], metavar="MODEL",
                        help="run these models without the domain-word prompt")
    args = parser.parse_args(argv)

    calls = load_calls(args.db, args.limit, args.calls)
    if not calls:
        print("ไม่มีสายที่ประมวลผลเสร็จและยังมีไฟล์เสียง — ไม่มีอะไรให้เทียบ")
        return 1
    references = load_references(args.refs)
    out_dir = Path(args.out or f"data/stt_compare/{datetime.now():%Y%m%d_%H%M%S}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"เทียบ {len(args.models)} โมเดล บน {len(calls)} สาย (DB อ่านอย่างเดียว: {args.db})")
    audio = prepare_audio(calls)
    runs = []
    for model in args.models:
        print(f"→ {model}")
        runs.append(run_model(model, calls, audio, use_prompt=model not in args.no_prompt))
    score_runs(runs, references)

    (out_dir / "report.md").write_text(render_markdown(runs, args.db, references), encoding="utf-8")
    write_outputs(runs, out_dir)
    for run in runs:
        print(f"{run['model']}: {run['total_seconds']} s รวม ({run['rtf'] * 60:.1f} s/นาทีเสียง), "
              f"VRAM {run['peak_vram']}, คำในโดเมน {run['domain_total']}, คำที่เคยถอดผิด {run['errors_total']}"
              + (f", CER {_pct(run['cer'])}" if run["cer"] != "" else ""))
    print(f"รายงาน: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
