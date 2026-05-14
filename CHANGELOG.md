# Changelog

All notable changes to SmartVoice will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2026-04-19 — Production-ready baseline

### Added
- **Logging system** (`smartvoice/logger.py`) — rotating file logger + console
  - Configurable via `SMARTVOICE_LOG_LEVEL` env var
  - Stored at `data/logs/smartvoice.log` (5 MB rotation, 3 backups)
- **File validation** on upload
  - Magic-byte audio type sniffing (WAV/MP3)
  - `MAX_FILE_SIZE_MB = 100` enforcement
  - `sanitize_filename()` to prevent path traversal
- **Idempotent seed functions** — `insert_customer` + `insert_warranty` return existing id if duplicate
- **Linux/Mac launcher** — `run.sh`
- **User Manual** — `docs/user_manual.md`
- **Architecture guide** — `docs/architecture.md`
- **CHANGELOG.md** — this file
- `get_warranty_by_registration()` helper
- Case management UI on Admin page — change status / edit subject
- `next_action_owner` field in Agent QA (who is responsible for follow-up)
- Keyword-based fallback for `next_action_owner` inference when LLM fails
- **Case grouping system** — LLM auto-assigns calls to existing/new cases per customer

### Changed
- Replaced `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` (Python 3.12 deprecation)
- `requirements.txt` now version-pinned with tested lower+upper bounds
- `pyproject.toml` — added `matplotlib`, `accelerate` dependencies
- All silent `except: pass` in LLM client + pipeline replaced with proper logging
- SETUP.md — expanded with troubleshooting, Linux/Mac support, MOCK_STT tip
- README.md — added `cases` table + `docs/report_corrections.md` to tree + `next_action_owner` field
- Admin page — show validation errors for oversized / wrong-format uploads
- Prompt: `next_action_owner` — added strict rule + few-shot examples

### Removed
- `smartvoice/whisperx_client.py` — unused backward-compat wrapper
- `db.hash_exists()` — dead code
- `file_manager.delete_audio_file()` — dead code
- Unused `shutil` import in `file_manager.py`
- `os` import in `ui_helpers.py` (no longer needed)

### Fixed
- `scripts/seed_mock_data.py` — `sys.path`/`chdir` pointed to `scripts/` instead of project root
- `scripts/generate_er_diagram.py` — output path saved to `scripts/` instead of `docs/`
- `scripts/generate_er_diagram.py` — missing `cases` table + 5 new columns on `calls`
- `docs/database_design.md` — table count, missing columns, `matched_by` docs mismatch
- `.gitignore` — added `smartvoice.egg-info/`, `data/logs/`
- Pipeline — restored `_auto_assign_case` helper that was accidentally deleted
- Agent QA — LLM returning `next_action_owner = "ไม่มี"` for non-closed cases (prompt + Python fallback)

---

## [0.9.0] — Pre-release (baseline captured before v1.0 polish)

### Features at this point
- Streamlit UI with Admin / Dashboard / Customers pages
- Whisper STT + pyannote diarization + Ollama LLM analysis
- SQLite storage with 5 tables (calls, customers, warranty_registrations, call_customer_links, cases)
- Auto-link call to customer by phone in filename
- 4-pass LLM analysis (summary/topic, sentiment, agent QA, anomaly)
- Multi-step speaker correction heuristics + LLM cleanup
- Background processing via threading
- ER diagram generator script
- Mock-data seeder script
- 32 passing pytest unit tests (speaker correction heuristics)
