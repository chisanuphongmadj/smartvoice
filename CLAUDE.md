# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SmartVoice** — AI-powered Call Center Analytics สำหรับ call center ภาษาไทย (domain: ร้านที่นอน/เฟอร์นิเจอร์ Restonic/โลตัส)

Pipeline: `audio (.wav/.mp3) → Whisper STT → Pyannote diarization → LLM speaker correction → LLM analysis → SQLite → Streamlit UI`

## Commands

All commands run from inside `smartvoice/` using the venv Python interpreter on Windows:

```powershell
# Run all tests (ignore test_config.py — has env side-effects)
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q

# Run a single test file
& ".venv\Scripts\python.exe" -m pytest tests\test_pipeline.py -v

# Run the app
.venv\Scripts\activate
streamlit run Home.py       # → http://localhost:8501

# Seed mock data
& ".venv\Scripts\python.exe" scripts\seed_mock_data.py

# Backfill topic_detail for legacy "แจ้งปัญหาสินค้า" calls (dry-run by default)
& ".venv\Scripts\python.exe" scripts\backfill_topic_detail.py [--apply]
```

**Current test baseline:** 190 tests, must pass 100% before every commit.

**External dependency:** Ollama must be running before processing calls:
```powershell
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve
```

## Architecture

### Package layout (`smartvoice/smartvoice/`)

| File | Role |
|------|------|
| `config.py` | Single source of truth for all env vars |
| `db.py` | SQLite schema, migrations, CRUD (tables: `calls`, `customers`, `warranty_registrations`, `call_customer_links`, `cases`). Scale-friendly helpers: `count_calls_by_status()`, `get_pending_call_ids()`, `get_processing_calls()`, `get_all_calls(limit=N)` |
| `pipeline.py` | Core orchestrator — speaker correction multi-pass, case assignment (~70 KB) |
| `prompts.py` | All LLM prompt templates (~54 KB) |
| `ollama_client.py` | LLM client + JSON extraction; 4 separate analysis calls. Includes `normalize_topic_detail()` for the product-issue drill-down vocabulary |
| `file_manager.py` | Audio upload + SHA-256 deduplication. Filename helpers: `extract_phone_from_filename()`, `extract_direction_from_filename()` (Inbound/Outbound), `extract_agent_code_from_filename()` |
| `ui_helpers.py` | Shared CSS, badges, processing launchers |
| `auth.py` | Streamlit login |
| `stt/` | STT sub-package: `audio.py` → `transcribe.py` → `diarize.py` → `orchestrator.py` |

Streamlit pages: `pages/1_📤_Admin.py`, `2_📊_Dashboard.py`, `3_👥_Customers.py`, `4_Settings.py`

### Speaker correction pipeline (`pipeline.py:1408-1459`)

Pyannote frequently mislabels speakers; LLM also makes mistakes — the system uses layered correction:

1. STT → diarization → grouped segments
2. `_split_long_segments_by_sentence()` — pre-split at Thai sentence boundaries
3. `ollama_client.correct_speakers()` — LLM label correction
4. `_aggressive_relabel_from_strong_cues()` — **deterministic override** using Thai domain cues ⭐
5. 9 splitter functions (opening/mixed/question-answer/closing turns)
6. `_stabilize_sandwiched_turns()`
7. `_aggressive_relabel_from_strong_cues()` again — after splitters create new chunks
8. `_merge_adjacent_same_speaker()`
9. `_enforce_role_rules()`
10. `ollama_client.cleanup_transcript()` — text polish
11. Repeat steps 2–9 (round 2)
12. `_apply_domain_normalization()` + dedup drops

**Critical order constraint:** `_aggressive_relabel_from_strong_cues` must run **before** `_merge_adjacent_same_speaker`, or merging will lock in wrong labels permanently.

### LLM analysis (`ollama_client.py:300+`)

4 separate Ollama calls (split for context window + accuracy):
1. `extract_summary_and_topics()` — summary, topic, **topic_detail** (drill-down for product-issue calls), keywords, brand/platform mentions
2. `analyze_sentiment()` — sentiment + reason
3. `evaluate_agent_qa()` — politeness, problem_solving, evidence, overall_score, next_action, next_action_owner
4. `detect_anomaly()` — anomaly flag, reason, severity

Every call → `extract_json()` → falls back to empty dict on parse failure (logs and continues).

Agent QA guardrails: `politeness` and `problem_solving` must be supported by Agent quotes, persisted as `politeness_evidence` / `problem_solving_evidence`; scores are clamped to 1-5 and `overall_score` is recomputed as `politeness + problem_solving` in Python.

`topic_detail` vocabulary (filled only when `topic == "แจ้งปัญหาสินค้า"`): `ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ`. Output is clamped server-side via `normalize_topic_detail()` so the dashboard can group cleanly.

### Auto case assignment (`pipeline.py:_auto_assign_case`)

1. **Recency short-circuit** — open case for this customer within `CASE_RECENCY_HOURS` (default 4h) → attach immediately (no LLM)
2. **LLM topic match** — compare new call's topic/summary against existing open cases
3. No match → create new case

### STT modes

| `MOCK_STT` | `WHISPER_BACKEND` | Result |
|-----------|-------------------|--------|
| `true` | any | Mock transcripts (fast, no GPU) |
| `false` | `transformers` | Recommended for Thai accuracy (`biodatlab/distill-whisper-th-large-v3`) |
| `false` | `faster-whisper` | Speed-optimized, `large-v3` or native CT2 model |

HF_TOKEN required for `pyannote/speaker-diarization-3.1` access. Without it, diarization is skipped and all speech is attributed to "Speaker 0".

## Domain: Thai Speaker Cues

Rule-based logic in `_aggressive_relabel_from_strong_cues` uses these patterns:

| Pattern | Indicates |
|---------|-----------|
| `พลอย/พอย + verb` | Agent (self-reference by name) |
| `คุณลูกค้า`, `ทางบริษัท/เรา/เจ้าหน้าที่` | Agent |
| `สวัสดีค่ะ [company name]` | Agent (opening) |
| `พี่ + verb` (self-reference) | Customer |
| `(ลูก/น้อง)` as vocative | Customer addressing agent |
| `ขอเลื่อนวัน`, `ติดตามเรื่องส่ง` | Customer |

**Do not modify `_AGENT_MARKERS` / `_CUSTOMER_MARKERS` without regression tests** — scoring is position + role sensitive; ambiguous additions cause flip errors.

## Anomaly Detection

Anomaly = escalation-worthy event, NOT just negative sentiment. Every flag requires a quoted passage from the transcript.

| Category | Required keywords | Severity |
|----------|------------------|----------|
| A1 Legal threat | "ฟ้อง", "ทนาย", "ดำเนินคดี", "ศาล", "แจ้งความ" | high |
| A2 Complaint threat | "สคบ.", "ร้องเรียน", "กระทรวง", "เพจ", "สื่อ" | high |
| A3 Escalation request | "ขอคุยกับหัวหน้า", "ขอสายผู้จัดการ" | medium |
| A4 Profanity | Actual swear words (not just tone) | low |
| B Agent misconduct | Direct quote required | high |
| C Safety/legal | "เชื้อรา", "สารเคมี", "บาดเจ็บ", damage + amount | medium-low |

Normal complaints resolved politely = negative sentiment, **not** anomaly.

## Scale-friendly Admin / Dashboard

Both pages cap row loading so they stay responsive at 10K+ uploads:

- **Admin** (`pages/1_📤_Admin.py`): top metric cards read from `count_calls_by_status()` (SQL `GROUP BY`) so they're accurate even when only the latest-N rows are loaded for display. Load-limit picker defaults to `200 ล่าสุด` when total > 200, else `ทั้งหมด`. "Process All Pending" uses `get_pending_call_ids()` (lazy) so old pending calls aren't missed. The `@st.fragment(run_every=3)` auto-refresh queries only `get_processing_calls()` (typically 0-1 rows) instead of the full table.
- **Dashboard** (`pages/2_📊_Dashboard.py`): load-limit picker defaults to `1,000 ล่าสุด` when total > 1000, else `ทั้งหมด`. Analytics signal quality matters more here than first-paint speed, so the default is larger than on Admin.

## Filename-derived filters

Three pieces of metadata are derived from the CDR filename pattern `YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav`:

- **Phone** — `extract_phone_from_filename()` (used during upload for customer auto-link)
- **Direction** — `extract_direction_from_filename()` → powers the Inbound/Outbound radio filter on Admin
- **Agent extension** — `extract_agent_code_from_filename()` → powers the Agent dropdown filter on the Dashboard Agent Performance section. Returns the short numeric segment (2-5 digits) that isn't the 14-digit timestamp or a 10-digit Thai phone.

No DB migration needed for direction/agent — derive at filter-time.

## Known Pitfalls

- **`test_config.py`** manipulates env vars with side-effects on other tests — always pass `--ignore=tests\test_config.py`.
- **`created_at` in DB** = upload/process time, not the actual call date. Call date is in the filename: `YYYYMMDDHHMMSS-...`.
- **LLM nested bullets** — Typhoon 8B copies sub-bullets as `anomaly_reason` without evidence. Prompts must specify keyword required list and mandate quoting.
- **Agent QA examples** — avoid concrete fake values in Next Action examples; Typhoon can copy them into every call. Use abstract templates and keep `sanitize_next_action()` in the display path for older DB rows.
- **Common Whisper errors:** "โอมาสนา"/"โนโลตัส"/"ฟิวทู" for brand names; "ที่โน่น"/"ทีเนี่ย" for "ที่นอน"; Thai phone numbers often mixed Thai/Arabic digits.
- **PowerShell:** Never use `cd` — set `Cwd` parameter instead.
- **Imports** must be at the top of every file; never mid-file.

## Pre-commit Checklist

- `pytest tests\ --ignore=tests\test_config.py -q` → 100% pass
- Add a regression test for every bug fix
- Remove temp files `_*.py`, `_*.txt`
- DB schema changes → migration must not break existing data + update `docs/database_design.md`
- Prompt changes → end-to-end test with at least one real audio file

## Environment

Configure via `smartvoice/.env` (copy from `.env.example`). Key variables:
- `WHISPER_MODEL`, `WHISPER_BACKEND`, `WHISPER_DEVICE`, `WHISPER_COMPUTE`
- `HF_TOKEN` — required for pyannote diarization (request access at huggingface.co)
- `OLLAMA_MODEL`, `OLLAMA_BASE_URL`
- `MOCK_STT=true` — fast development mode without GPU
- `DB_PATH` — defaults to `data/smartvoice.db`
- `CASE_RECENCY_HOURS` — window for recency-based case attachment

`data/` and `.env` are gitignored (runtime data + secrets).
