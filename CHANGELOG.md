# Changelog

All notable changes to SmartVoice are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.1.0] — 2026-05-20 — Delivery handoff (ส่งมอบ 2026-05-23)

### Added
- หน้า `Settings` สำหรับสลับ Demo / Real AI และแก้ค่า `.env` ผ่าน UI
- `Deployment readiness` checks บนหน้า Home และหน้า Settings
- Login แบบ PBKDF2 ผ่าน `SMARTVOICE_USERS` พร้อม demo/audit fallback mode
- Audit fields `uploaded_by` และ `uploaded_by_role` บน `calls`
- Recovery งานค้างในสถานะ `processing` ผ่าน `PROCESSING_STALE_MINUTES`
- Recency short-circuit สำหรับ auto case assignment ผ่าน `CASE_RECENCY_HOURS`
- Case merge, orphan-case cleanup, admin search/filter/sort, bulk delete, pagination
- คู่มือ one-click run และ release checklist สำหรับส่งต่อเครื่อง demo
- Agent QA evidence fields (`politeness_evidence`, `problem_solving_evidence`) สำหรับตรวจสอบเหตุผลของคะแนนบน Dashboard
- Sanitizer ใน `ollama_client._scrub_prompt_example_leakage` กรอง JSON-schema placeholder ที่ Typhoon-8B copy มาจาก prompt
- `scripts/scrub_existing_next_actions.py` สำหรับ backfill ลบ prompt placeholder ที่หลุดเข้ามาในแถวเดิมของ `agent_performance`

### Changed
- เอกสารทั้งหมดถูกปรับให้ตรงกับสถานะปัจจุบันของโค้ด ณ วันส่งมอบ
- เอกสาร pipeline เปลี่ยนจากคำอธิบาย “4 parallel calls” เป็น “4 calls” ให้ตรงกับการทำงานจริงแบบ sequential
- Project structure docs อัปเดตให้รวม `auth.py`, `env_settings.py`, `preflight.py`, `4_Settings.py`, และ scripts ปัจจุบันทั้งหมด
- Database docs อัปเดตให้รวม audit columns ล่าสุดของ `calls`
- Agent QA prompt เข้มขึ้น: ให้คะแนนเฉพาะข้อที่มีหลักฐานจากคำพูด Agent, ห้ามเดาจากน้ำเสียงหรือมารยาททั่วไป, และบังคับ quote สั้นใน evidence
- Backend clamp คะแนน `politeness` / `problem_solving` ให้อยู่ช่วง 1-5 และคำนวณ `overall_score = politeness + problem_solving` เอง
- Dashboard แสดงหลักฐาน Politeness / Problem Solving และคำนวณ Score จากคะแนนย่อยที่ sanitize แล้ว

### Fixed
- ป้องกัน Typhoon-8B copy JSON-schema placeholder ของ next_action (เช่น 15,000 / #REG0012 / 081-987-9336) เข้า evidence จริง

### Tests
- Test baseline ปัจจุบัน: `145 passed` (ทดสอบเมื่อ 2026-05-20)

---

## [1.0.0] — 2026-04-19 — Production-ready baseline

### Added
- Logging system (`smartvoice/logger.py`) — rotating file logger + console
- File validation on upload
  - Magic-byte audio type sniffing (WAV/MP3)
  - `MAX_FILE_SIZE_MB = 100` enforcement
  - `sanitize_filename()` to prevent path traversal
- Idempotent seed functions — `insert_customer` + `insert_warranty`
- Linux/Mac launcher — `run.sh`
- User Manual — `docs/user_manual.md`
- Architecture guide — `docs/architecture.md`
- CHANGELOG.md
- `get_warranty_by_registration()` helper
- Case management UI on Admin page
- `next_action_owner` field in Agent QA
- Keyword-based fallback for `next_action_owner`
- Case grouping system

### Changed
- Replaced `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`
- `requirements.txt` version-pinned with tested lower/upper bounds
- `pyproject.toml` added `matplotlib`, `accelerate`
- Replaced silent `except: pass` in LLM client + pipeline with logging
- Expanded setup docs and upload validation feedback
- Prompt rules tightened for `next_action_owner`

### Removed
- `smartvoice/whisperx_client.py`
- `db.hash_exists()`
- `file_manager.delete_audio_file()`
- Unused imports in `file_manager.py` and `ui_helpers.py`

### Fixed
- `scripts/seed_mock_data.py` project-root path handling
- `scripts/generate_er_diagram.py` output path and missing schema items
- `docs/database_design.md` mismatches from the earlier schema
- `.gitignore` entries for generated runtime files
- `_auto_assign_case` helper restoration
- `next_action_owner` fallback for non-closed cases

---

## [0.9.0] — Pre-release

### Features at this point
- Streamlit UI with Admin / Dashboard / Customers pages
- Whisper STT + pyannote diarization + Ollama LLM analysis
- SQLite storage with 5 tables
- Auto-link call to customer by phone in filename
- 4-pass LLM analysis
- Multi-step speaker correction heuristics + LLM cleanup
- Background processing via threading
- ER diagram generator script
- Mock-data seeder script
