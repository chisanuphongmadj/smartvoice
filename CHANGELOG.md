# Changelog

All notable changes to SmartVoice are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.2.0] — 2026-05-27 — Post-delivery feedback round 1

### Added — Dashboard / Analytics
- `topic_detail` column on `calls` + controlled vocabulary in extraction prompt: `ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ` (Omazz feedback: "แจ้งปัญหาสินค้า" หมวดเดียวกว้างเกินไป)
- Drill-down chart "เจาะลึก: ประเภทความเสียหายภายใน 'แจ้งปัญหาสินค้า'" บน Dashboard ใต้ Topic / Intent Distribution
- `ollama_client.normalize_topic_detail()` — clamp LLM output ให้อยู่ใน vocabulary 7 ค่า (keyword snap + fallback "อื่นๆ")
- Agent dropdown filter + "Agent" column บน Dashboard → Agent Performance (`extract_agent_code_from_filename()`)

### Added — Admin / Scale
- Scale-friendly DB helpers: `count_calls_by_status()`, `get_pending_call_ids()`, `get_processing_calls()`, และ `get_all_calls(limit=N)` — รองรับการใช้งานที่ 10K+ uploads
- Load-limit picker บนหน้า Admin (`100 / 200 / 500 / 1,000 / 5,000 / ทั้งหมด`) และ Dashboard (`100 / 500 / 1,000 / 5,000 / ทั้งหมด`) — default แยกตาม use case
- Inbound / Outbound radio filter บนหน้า Admin (`extract_direction_from_filename()`)

### Added — Settings page
- GPU auto-detection ด้วย `gpu_available()` / `gpu_device_name()` — แสดง banner ตามสถานะเครื่อง และซ่อน option `cuda` จาก Device dropdown ถ้าไม่พบ GPU
- `validate_whisper_combo()` — ตรวจ compatibility ของ model / backend / device / compute หลัง Save (error / warning / info)
- `recommended_combo_for_model()` — เมื่อผู้ใช้เลือก Whisper model ระบบจะปรับ Backend / Device / Compute เป็นค่าแนะนำให้อัตโนมัติ (auto-apply on change)
- `help=` tooltip ทุก selectbox อธิบายข้อดี/ข้อเสียของแต่ละตัวเลือก

### Added — Scripts
- `scripts/backfill_topic_detail.py` — re-classify topic_detail ของ call เก่า ๆ ที่ topic="แจ้งปัญหาสินค้า" แต่ยังไม่มี detail (LLM-only, ไม่รัน STT)

### Changed
- หน้า Admin metric cards เปลี่ยนมาใช้ `db.count_calls_by_status()` (SQL aggregate) แทนการนับจาก list ที่โหลดมา — ตัวเลขแม่นแม้โหลดแค่ N สายล่าสุด
- หน้า Admin "Process All Pending" ใช้ `db.get_pending_call_ids()` lazy query — ไม่พลาด pending เก่าที่อยู่นอก scope load limit
- Auto-refresh fragment ของ Admin (รันทุก 3 วิ) เปลี่ยนจาก `get_all_calls()` ทั้งตาราง → `get_processing_calls()` เฉพาะ row ที่กำลัง process (โดยปกติ 0-1 row)
- Dashboard default load: `ทั้งหมด ≤ 500 / ไม่งั้น 500 ล่าสุด` → `ทั้งหมด ≤ 1,000 / ไม่งั้น 1,000 ล่าสุด` (analytics ต้องการ signal มาก)
- Admin default load: `ทั้งหมด ≤ 500 / ไม่งั้น 500 ล่าสุด` → `ทั้งหมด ≤ 200 / ไม่งั้น 200 ล่าสุด` (ops focus on recent)
- หน้า Settings เอา `st.form` ออก — เปลี่ยนเป็น reactive widgets (key= + session_state) เพื่อให้ `on_change` callback ของ Whisper model selectbox ทำงานทันที (form widget ไม่ fire on_change จนกว่าจะ submit)
- ปุ่ม Save Settings เปลี่ยนเป็น `st.button` ปกติ พฤติกรรมเหมือนเดิม (บันทึก `.env` ครั้งเดียวเมื่อกด)

### Database
- `_migrate()` เพิ่ม column `topic_detail TEXT` (NULL สำหรับ row เก่า — ไม่ break migration)
- `docs/database_design.md` อัปเดต ER diagram + data dictionary

### Docs
- `docs/user_manual.md` เขียนใหม่ฉบับเต็ม (17 sections, ~1,200 บรรทัด) สำหรับใช้เป็นรายงานส่ง Omazz
- `docs/architecture.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/OMAZZ_RELEASE_CHECKLIST.md` อัปเดตให้ตรงกับฟีเจอร์ใหม่ทั้งหมด

### Tests
- Test baseline ปัจจุบัน: `209 passed` (เดิม 145) — เพิ่ม regression สำหรับ:
  - topic_detail vocabulary + normalize_topic_detail (8 tests)
  - scale-friendly DB helpers + topic_detail persistence (8 tests)
  - filename direction/agent extraction (12 tests)
  - Whisper combo validator (9 tests)
  - recommended_combo_for_model (6 tests)

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
