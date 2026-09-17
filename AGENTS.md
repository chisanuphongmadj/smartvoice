# AGENTS.md — Guide for AI Coding Agents

คู่มือสำหรับ AI agents (Cascade, Claude Code, Cursor, etc.) ที่ทำงานบน codebase นี้
อ่านไฟล์นี้ก่อนเริ่มแก้งานใหญ่ทุกครั้ง

---

## 1. โปรเจคนี้คืออะไร

**SmartVoice** — AI Call Center Analytics สำหรับสายภาษาไทย

**Pipeline ภาพรวม:** `audio (.wav/.mp3) → Whisper STT → Pyannote diarization → LLM speaker correction → LLM analysis (sentiment / QA / anomaly / case grouping) → SQLite → Streamlit UI`

**Domain:** call-centre ของบริษัทขายที่นอน/เฟอร์นิเจอร์ (Restonic, โลตัส) — ลูกค้าโทรเข้าร้องเรียน/ติดตามคำสั่งซื้อ/เคลมประกัน

**Tech:** Python 3.10+, Streamlit, SQLite, `faster-whisper` / `transformers` Whisper, `pyannote.audio` 3.1, Ollama LLM (`scb10x/llama3.1-typhoon2-8b-instruct`)

---

## 2. Quick-start (commands จริงที่ใช้บ่อย)

**OS:** Windows + PowerShell. **อย่าใช้ `cd`** — ตั้ง `Cwd` แทน

**Working dir:** `c:\Users\User\CascadeProjects\project\smartvoice`

**Python interpreter:** `.venv\Scripts\python.exe` (Windows venv path)

```powershell
# รัน test (ไม่รวม test_config.py — มี side effects กับ env)
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q

# รันเฉพาะไฟล์
& ".venv\Scripts\python.exe" -m pytest tests\test_pipeline.py -v

# เปิดแอป
.venv\Scripts\activate
streamlit run Home.py   # → http://localhost:8501

# หรือใช้ launcher
run.bat                 # Windows
./run.sh                # Linux/macOS
```

**Test baseline ล่าสุด:** 305 tests, ต้องผ่าน 100% ก่อน commit ทุกครั้ง

**เข้าใช้งานครั้งแรก:** ถ้ายังไม่มีบัญชีใดในระบบ แอปสร้าง `admin` / `admin1234` ให้อัตโนมัติ (มีคำเตือนค้างจนกว่าจะเปลี่ยนรหัสผ่าน)

---

## 3. โครงสร้างไฟล์สำคัญ

```
smartvoice/
├── Home.py                     # Router: login → st.navigation ตามสิทธิ์ของ role + หน้าแรก
├── pages/
│   ├── 1_📤_Admin.py           # Upload / process / เคส (Admin, Supervisor)
│   ├── 2_📊_Dashboard.py       # Analytics (ทุก role)
│   ├── 3_👥_Customers.py       # ดูลูกค้า + ทะเบียนรับประกัน (ทุก role)
│   ├── 4_Settings.py           # ตั้งค่า .env (Admin, Supervisor)
│   ├── 5_👤_Users.py           # บัญชีพนักงาน — เพิ่ม / เปลี่ยน role / เปิด-ปิด (Admin)
│   ├── 6_➕_Data_Entry.py      # เพิ่ม / แก้ / ซ่อน / กู้คืน ลูกค้าและทะเบียน (Admin)
│   └── 7_📜_Audit_Log.py       # ประวัติการใช้งาน (Admin, Supervisor)
├── smartvoice/                 # Business logic package
│   ├── config.py               # ⚠️ environment vars ทั้งหมดอยู่ที่นี่
│   ├── db.py                   # SQLite schema + migrations + CRUD
│   ├── pipeline.py             # 🔥 Core orchestrator (70 KB) — speaker correction, splitters, merge
│   ├── prompts.py              # 🔥 LLM prompts (54 KB) — system+user สำหรับทุก LLM call
│   ├── ollama_client.py        # LLM client + JSON extraction
│   ├── file_manager.py         # Upload + SHA-256 dedup
│   ├── ui_helpers.py           # CSS, login page, init_page() role guard, audit() wrapper, processing launcher
│   ├── auth.py                 # PBKDF2 hashing, บัญชี DB/.env, ROLE_PERMISSIONS
│   ├── audit.py                # คำศัพท์ audit trail + record() + redact() + diff_fields()
│   ├── customer_entry.py       # กติกา validate / บันทึก / ซ่อน / กู้คืน ของหน้าเพิ่มข้อมูล
│   ├── env_settings.py         # อ่าน/เขียน .env + GPU detect + combo validation
│   ├── preflight.py            # Deployment readiness checks
│   ├── logger.py               # Rotating file logger
│   └── stt/                    # Speech-to-Text sub-package
│       ├── orchestrator.py     # ties audio→transcribe→diarize
│       ├── audio.py            # load + resample + denoise
│       ├── transcribe.py       # HF transformers + faster-whisper backends
│       └── diarize.py          # pyannote 3.1 + speaker assignment
├── tests/                      # pytest unit tests
├── data/                       # 🚫 gitignored runtime data (audio, db, logs, models)
└── docs/                       # Architecture, DB design, user manual
```

**DB tables:** `calls`, `customers`, `warranty_registrations`, `call_customer_links`, `cases`, `users`, `audit_log`

⚠️ ชื่อไฟล์ใน `pages/` มี emoji อยู่จริง และ `Home.py` route ไปที่ path ตรงตัวนั้น — ห้ามลบ emoji ออกจาก path (แต่ห้ามใส่ emoji ในป้ายที่ผู้ใช้เห็น ดูข้อ 7.8)

---

## 4. หลักการทำงาน (สำคัญที่สุด)

### 4.1 Bug-fixing discipline
- **หา root cause ก่อนแก้** — อย่าทำ downstream workaround
- ใช้การแก้แบบ minimal upstream fix (มักเป็น 1-line) มากกว่า over-engineer
- เพิ่ม regression test ทุกครั้งที่แก้ bug
- ห้ามลบ/ลดความเข้มงวดของ test ที่มีอยู่ ถ้าไม่ได้รับอนุญาตชัดเจน

### 4.2 Testing discipline
- เขียน test ก่อนทำงาน implementation ใหญ่
- รัน test ทุกครั้งหลังแก้: `pytest tests\ --ignore=tests\test_config.py -q`
- ถ้าทำ test pass ไม่ได้ → **ห้ามแก้ test ให้มันผ่าน** ให้แก้ code แทน

### 4.3 Code style
- **ห้ามเติมหรือลบ comment / docstring** ถ้าไม่ได้สั่ง
- ตามสไตล์ที่มีอยู่ในไฟล์ (snake_case, double-quoted strings, type hints)
- Import ต้องอยู่บนสุดของไฟล์เสมอ — ห้ามใส่กลางไฟล์
- ใช้ regex ที่มี comment กำกับ pattern ภาษาไทยถ้าซับซ้อน

### 4.4 อย่าสร้างไฟล์รก
- ห้ามสร้าง `.md` ใหม่เพื่อสรุปงานตัวเอง
- Sanity script ชั่วคราว (`_*.py`) ต้องลบหลังใช้
- อย่าสร้าง helper module ใหม่ถ้ามี util เดิมที่ทำได้

---

## 5. Pipeline architecture (ส่วนสำคัญที่ agent ต้องเข้าใจ)

### 5.1 Speaker correction multi-pass (`pipeline.py:1408-1459`)

```
1. STT → diarization → grouped segments
2. _split_long_segments_by_sentence()         # pre-split mega-chunks at Thai boundaries
3. ollama_client.correct_speakers()            # LLM-based label correction
4. _aggressive_relabel_from_strong_cues()      # ⭐ deterministic override จาก domain cues
5. Splitters (ในลำดับนี้):
   _split_opening_mixed_turns()
   _split_answer_prefixed_turns()
   _split_embedded_agent_answer_turns()
   _split_mixed_question_answer_turns()
   _split_followup_question_turns()
   _split_embedded_customer_reaction_turns()
   _split_trailing_customer_question_turns()
   _split_leading_agent_continuation_turns()
   _split_mixed_closing_turns()
6. _stabilize_sandwiched_turns()
7. _aggressive_relabel_from_strong_cues()      # อีกรอบ — บน chunks ที่ splitter สร้าง
8. _merge_adjacent_same_speaker()
9. _enforce_role_rules()
10. ollama_client.cleanup_transcript()         # LLM text polish
11. ทำซ้ำ steps 2-9 รอบ 2
12. _apply_domain_normalization()
13. _drop_redundant_opening_segments() / _drop_adjacent_duplicate_segments()
```

**Key insight:** Pyannote มัก mislabel — LLM ก็พลาดบ่อย → ใช้ rule-based override ที่ตรวจ "strong cues" ภาษาไทย:
- **Customer cues:** `พี่(สะดวก|ติดประชุม|ลางาน|...)`, `ได้ไหมลูก`, `ขอเลื่อนวัน`, `ติดตามเรื่องส่ง...`
- **Agent cues:** `พลอย(ขอ|ดู|...)`, `คุณลูกค้า`, `ทางบริษัท`, `กลุ่มบริษัทที่นอน`

### 5.2 LLM analysis (`ollama_client.py:300+`)

4 separate LLM calls (ไม่รวมในก้อนเดียวเพราะ context window + ความแม่นยำ):
1. `extract_summary_and_topics()` — summary + topic + **topic_detail** + keywords + brand/platform mentions
2. `analyze_sentiment()` — sentiment + reason
3. `evaluate_agent_qa()` — politeness + problem_solving + evidence + overall_score + next_action + next_action_owner
4. `detect_anomaly()` — anomaly flag + reason + severity

ทุก call → `extract_json()` → fallback เป็น empty dict ถ้า parse fail (log + continue)

**Agent QA guardrails ล่าสุด:** `politeness` และ `problem_solving` ต้องอิงหลักฐานจากคำพูด Agent ใน transcript, เก็บ `politeness_evidence` / `problem_solving_evidence`, clamp คะแนนย่อยให้อยู่ช่วง 1-5, และคำนวณ `overall_score = politeness + problem_solving` ใน backend เสมอ

**`topic_detail` vocabulary** (กรอกเมื่อ `topic == "แจ้งปัญหาสินค้า"` เท่านั้น): `ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ` — clamp ผ่าน `ollama_client.normalize_topic_detail()` ก่อนเขียน DB เพื่อให้ chart group ได้สะอาด

### 5.3 Auto case assignment (`pipeline.py:_auto_assign_case`)

ลำดับการตัดสินใจ:
1. **Recency short-circuit** — ถ้ามี case เปิดอยู่ของลูกค้าคนนี้ภายใน `CASE_RECENCY_HOURS` (default 4h) → attach ทันที (ข้าม LLM)
2. **LLM topic match** — ส่ง topic + summary ของสายใหม่ + existing cases → LLM ตัดสินใจว่าจะ attach หรือสร้าง case ใหม่
3. ถ้าไม่ match อะไรเลย → สร้าง case ใหม่

---

## 6. Domain knowledge (ภาษาไทย call center)

### 6.1 Speaker indicators ที่ใช้ใน rule-based logic

| Pattern | บอกว่าเป็น | ตัวอย่าง |
|---------|-----------|---------|
| `สวัสดีค่ะ [บริษัท]` | Agent (เปิดสาย) | "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ" |
| `ทาง(บริษัท\|เรา\|เจ้าหน้าที่)` | Agent | "ทางเราจะตรวจสอบให้" |
| `คุณลูกค้า` | Agent (เรียกอีกฝ่าย) | "คุณลูกค้าสะดวกวันไหนคะ" |
| `พลอย\|พอย + verb` | Agent (พนักงานเรียกตัวเอง) | "พลอยขอตรวจสอบในระบบ" |
| `พี่ + verb` (self-ref) | Customer | "พี่สะดวกวันที่ 8", "พี่ติดประชุม" |
| `(ลูก\|น้อง)` (vocative) | Customer (เรียกพนักงาน) | "ได้ไหมลูก", "นะลูก" |
| `ติดตามเรื่อง...ส่ง` | Customer | "ติดตามเรื่องการส่งที่นอน" |
| `ขอเลื่อนวัน/รับสินค้า` | Customer | "ขอเลื่อนวันรับ" |
| `ขอบคุณค่ะ + สวัสดีค่ะ` (ลงท้าย) | ทั้งคู่พูดได้ — ไม่ใช้แยก |

### 6.2 Anomaly detection rules (`prompts.py:ANOMALY_USER`)

**หลักการ:** Anomaly = เหตุการณ์ที่ต้อง **escalate ให้หัวหน้า** ไม่ใช่แค่ลูกค้าไม่พอใจ
ทุก flag **ต้องมี quote คำพูดจริง** จาก transcript

| Category | ต้องเจอ keyword | Severity |
|----------|----------------|----------|
| A1 ขู่ฟ้อง | "ฟ้อง", "ทนาย", "ดำเนินคดี", "ศาล", "แจ้งความ" | high |
| A2 ขู่ร้องเรียน | "สคบ.", "ร้องเรียน", "กระทรวง", "เพจ", "สื่อ" | high |
| A3 ขอหัวหน้า | "ขอคุยกับหัวหน้า", "ขอสายผู้จัดการ" | medium |
| A4 คำหยาบ | คำด่าจริง (ไม่ใช่แค่น้ำเสียง) | low |
| B พนักงานผิดระเบียบ | quote คำพูดจริง | high |
| C safety/legal | "เชื้อรา", "สารเคมี", "บาดเจ็บ", ค่าเสียหาย+จำนวนเงิน | medium-low |
| D สายขัดข้อง | หลักฐานชัดใน transcript | medium |

**ห้าม flag** เคสที่ลูกค้าโทรร้องเรียน/ขอคืนสินค้าตามปกติ + ลงท้ายสุภาพ — นั่นคือ negative sentiment ปกติ ไม่ใช่ anomaly

### 6.3 Common STT errors ที่ต้องระวัง
- ชื่อบริษัท "โอมาสนา" / "โนโลตัส" / "ฟิวทู" / "โลตัส" — Whisper สับสนชื่อยี่ห้อบ่อย
- "ที่นอน" บางครั้งเป็น "ที่โน่น" / "ทีเนี่ย"
- เลขโทรศัพท์ Thai มักผิดเป็นไทย-อังกฤษปน

---

## 6.4 Scale-friendly Home / Admin / Dashboard

ทั้งสามหน้าไม่โหลด row ที่ไม่ได้แสดง เพื่อให้ไม่ค้างเมื่อมี 10K+ ไฟล์:

- **Home** (`Home.py`): การ์ด 4 ใบใช้ `db.count_calls_by_status()` — ห้ามกลับไปใช้ `get_all_calls()` (เป็น `SELECT *` ลาก transcript ทุกสายเข้าหน่วยความจำ วัดได้ ~278 ms / ~57 MB ที่ 5,000 สาย). readiness checks ครอบด้วย `@st.cache_data(ttl=300)` เพราะเนื้อใน expander รันทุก rerun แม้พับอยู่ และมันยิง network ~2.6 วินาที — รวมแล้วหน้าแรกจาก 2.9 วินาที เหลือ 0.2 วินาที
- **Admin** (`pages/1_📤_Admin.py`): metric cards ใช้ `db.count_calls_by_status()` (SQL `GROUP BY`) ให้แม่นแม้โหลดแค่ N สายล่าสุด. Load-limit picker default `200 ล่าสุด` ถ้า total > 200. "Process All Pending" lazy query ผ่าน `db.get_pending_call_ids()`. Auto-refresh fragment ใช้ `db.get_processing_calls()` (0-1 row โดยปกติ).
- **Dashboard** (`pages/2_📊_Dashboard.py`): load-limit default `1,000 ล่าสุด` ถ้า total > 1000 — analytics ต้อง signal มาก กว่าหน้า Admin

## 6.5 Filename-derived filters

Filename รูปแบบ `YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav` ใช้สกัด:

- **Phone** — `file_manager.extract_phone_from_filename()` (auto-link ตอน upload)
- **Direction** — `file_manager.extract_direction_from_filename()` → radio filter Inbound/Outbound ที่หน้า Admin
- **Agent extension** — `file_manager.extract_agent_code_from_filename()` → dropdown filter Agent ที่ Dashboard → Agent Performance (segment 2-5 หลัก ที่ไม่ใช่ timestamp 14 หลักและไม่ใช่เบอร์ไทย)

ไม่ต้อง migrate DB — derive runtime ตอนกรอง

## 6.6 Backfill scripts

- `scripts/scrub_existing_next_actions.py` — ลบ prompt-example placeholder ที่หลุดเข้า `agent_performance` เก่า
- `scripts/backfill_topic_detail.py` — re-classify `topic_detail` ของสายเก่าที่ `topic="แจ้งปัญหาสินค้า"` แต่ยังไม่มี detail (LLM-only, ไม่รัน STT ใหม่)

ทั้งคู่มี `--apply` flag (default = dry-run)

## 6.7 Settings page (`pages/4_Settings.py`)

**ตั้งใจไม่ใช้ `st.form`** เพราะ form widget ไม่ fire `on_change` จนกว่าจะ submit — ทำให้ feature "auto-apply combo on model change" ใช้ไม่ได้ใน form

โครงสร้างปัจจุบัน:
- Widget ทุกตัวมี `key=` + session_state seeded จาก `.env`
- Whisper model selectbox มี `on_change=_apply_model_recommendations` → ปรับ Backend/Device/Compute ทันที
- ปุ่ม Save เป็น `st.button` ปกติ (ไม่ใช่ `form_submit_button`) — บันทึก `.env` ครั้งเดียวเมื่อกด

Helpers ใน `env_settings.py`:
- `gpu_available()` / `gpu_device_name()` — ตรวจ CUDA, safe ถ้า torch ไม่มี
- `validate_whisper_combo(model, backend, device, compute, has_gpu)` → list[(severity, message)]
- `recommended_combo_for_model(model, has_gpu=None)` → tuple(backend, device, compute) | None
- `_MODEL_RECOMMENDED_COMBO` — table mapping model → preferred combo (เพิ่ม model ใหม่ใน dropdown ต้องเพิ่มใน table นี้ด้วย)

## 6.8 Login, สิทธิ์ และนโยบายบัญชี

`Home.py` เป็น **router** ไม่ใช่แค่หน้าแรก: ยังไม่ login → เห็นแค่หน้าเข้าสู่ระบบ; login แล้ว → `st.navigation()` สร้างเมนูจาก `auth.visible_pages(role)` เท่านั้น หน้าที่ไม่มีสิทธิ์จึงไม่ขึ้นเมนูเลย และพิมพ์ URL ตรง ๆ ก็เข้าไม่ได้

| Role | home | admin | dashboard | customers | data_entry | audit | settings | users |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Supervisor | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| QA | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Agent | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

กติกาที่ต้องรักษา:
- ทุกหน้าเริ่มด้วย `user, role = init_page(PAGE_<KEY>)` — ห้ามเช็ค `if role in {...}` เอง
- **เพิ่มหน้าใหม่ต้องครบ 5 จุด:** `PAGE_*` constant + `PAGE_ORDER`/`PAGE_LABELS_TH` + `ROLE_PERMISSIONS` + route ใน `_PAGE_SPECS` ของ `Home.py` + `init_page()` ในไฟล์หน้า (`tests/test_home_entrypoint.py` จับได้ถ้าขาด)
- `normalize_role()` แปลงค่าที่ไม่รู้จักเป็น `Agent` (สิทธิ์ต่ำสุด)
- ต้องเหลือ Admin ที่เปิดใช้งาน ≥ 1 บัญชีเสมอ (`auth.would_remove_last_admin()`)
- **ไม่มีการรีเซ็ตรหัสผ่านโดย Admin — ตามนโยบาย** รหัสผ่านเป็นของเจ้าของบัญชี ตั้งได้ผ่าน `auth.change_password()` ซึ่งบังคับกรอกรหัสเดิมเท่านั้น สิ่งที่ Admin ทำได้คือเปิด/ปิดบัญชี ห้ามเพิ่ม reset helper หรือฟอร์มรีเซ็ต (`tests/test_auth.py` จับได้)
- **หน้าจัดการผู้ใช้ไม่มีปุ่มลบบัญชี** เพราะ `audit_log` อ้างถึงบัญชีเหล่านั้น — ใช้ปิดใช้งานแทน (`db.delete_user()` ยังอยู่แต่ไม่มีหน้าไหนเรียก)
- session อยู่ใน Streamlit session_state — กด F5 = ออกจากระบบ (ยอมรับได้ ไม่มี cookie/JWT)

## 6.9 Soft delete + audit trail

**ลูกค้าและทะเบียนรับประกันไม่ถูกลบออกจากฐานข้อมูล** — "ลบ" ใน UI คือประทับ `deleted_at` / `deleted_by` แล้วแถวจะหายจาก query ปกติ ห้ามเขียน `DELETE FROM customers` / `DELETE FROM warranty_registrations`

- `soft_delete_customer()` ซ่อนลูกค้า **และ** ทะเบียนของเขา (ติดธง `hidden_with_customer = 1`) โดยไม่แตะสาย เคส และการเชื่อมสาย
- `restore_customer()` กู้คืนเฉพาะทะเบียนที่มีธงนั้น — ห้ามใช้ `deleted_at` ที่ตรงกันเป็นตัวจับคู่ เพราะซ่อนสองครั้งในวินาทีเดียวกันจะชนกัน
- ฟังก์ชันอ่านทุกตัวมี `include_deleted=False` เป็นค่าเริ่มต้น; `phone` / `registration_no` เป็น UNIQUE แถวที่ซ่อนจึงยังจองค่าไว้ — ตัวตรวจซ้ำใน `customer_entry` ต้องมองด้วย `include_deleted=True` แล้วบอกให้กู้คืนแทน

**Audit trail** — ทุก action ที่เปลี่ยนข้อมูลต้องผ่าน `audit.record()` (หน้าเว็บเรียก `ui_helpers.audit()` ซึ่งเติมผู้ใช้จาก session ให้) ลงตาราง `audit_log` ดูได้ที่หน้า `7_📜_Audit_Log.py`

| จาก | บันทึกอะไร |
|---|---|
| `ui_helpers` (login flow) | เข้าสู่ระบบ, เข้าสู่ระบบไม่สำเร็จ, ออกจากระบบ, เปลี่ยนรหัสผ่านตัวเอง |
| `customer_entry` | ลูกค้า/ทะเบียน: เพิ่ม, แก้ไข, ซ่อน, กู้คืน |
| `5_👤_Users.py` | สร้างบัญชี, เปลี่ยน role, เปิด/ปิดใช้งาน |
| `1_📤_Admin.py` | อัปโหลด/ลบสาย, เชื่อมลูกค้าแบบ manual, เปลี่ยนสถานะ/หัวข้อ/รวมเคส |
| `4_Settings.py` | บันทึก `.env` และปุ่ม preset |

- `audit_log` เป็น **append-only** — ห้ามมีโค้ด UPDATE/DELETE แถวในตารางนี้
- `audit.record()` **ห้าม raise** — log ล้มต้องไม่ทำให้งานของผู้ใช้หาย
- `audit.redact()` ตัดค่า `password` / `password_hash` / `hf_token` ออก (เก็บชื่อฟิลด์ไว้)
- entry แบบ `update` เก็บ `{field: [ก่อน, หลัง]}` จาก `audit.diff_fields()` และถ้าไม่มีอะไรเปลี่ยนจะไม่เขียน entry
- เพิ่ม action ใหม่ที่เปลี่ยนข้อมูล → ต้องมี `audit()` ข้าง ๆ (`tests/test_audit.py` ตรวจ)

---

## 7. Pitfalls / สิ่งที่เคยพังมาแล้ว

### 7.1 อย่าใช้ `cd` ใน `run_command`
PowerShell ใน Windows → ตั้ง `Cwd` แทน `cd && ...`

### 7.2 อย่าทำ test_config.py พัง
มัน manipulate env vars และ side-effect ต่อ test อื่น → ใช้ `--ignore=tests\test_config.py`

### 7.3 อย่าแก้ `_AGENT_MARKERS` / `_CUSTOMER_MARKERS` แบบเดาๆ
markers ใช้กับ `_enforce_role_rules` ที่ scoring ตำแหน่ง + role — เพิ่ม marker ที่กำกวมจะทำให้ flip ผิด ทำ regression test ครอบคลุมก่อนเพิ่ม

### 7.4 LLM prompt — เลี่ยง nested bullet
ปัญหาที่เจอจริง: LLM (Typhoon 8B) เคย copy sub-bullet เป็น `anomaly_reason` แม้ไม่มีหลักฐาน → ต้องระบุ keyword required list ชัดและสั่ง quote evidence
สำหรับ Agent QA ห้ามใส่ตัวอย่าง Next Action ที่มีข้อมูลจริงปลอม เช่น ยอดเงิน/เบอร์โทร/รหัสสินค้า เพราะ LLM เคย copy ตัวอย่างไปแสดงทุกสาย; ใช้ template นามธรรมและ sanitize output ใน `ollama_client.sanitize_next_action()`

### 7.5 Pipeline เรียง step ผิด
`_aggressive_relabel_from_strong_cues` ต้องเรียก **ก่อน** `_merge_adjacent_same_speaker` ไม่งั้นการรวมจะ lock label ผิดถาวร

### 7.6 `created_at` ใน DB
คือเวลา **upload/process** ไม่ใช่ **วันที่โทรจริง** — วันที่โทรอยู่ใน filename pattern `YYYYMMDDHHMMSS-...`

### 7.7 ตัดข้อความภาษาไทยด้วยจำนวนตัวอักษร
`summary[:100]` เคยทำให้ข้อความขาดกลางคำ ("...คืนสินค้า พนั") เพราะภาษาไทยไม่มีเว้นวรรคระหว่างคำ ตัดที่ไหนก็ลงกลางคำ — แสดงเต็มแล้วปล่อยให้ตัดบรรทัดเอง

### 7.8 ป้ายใน UI ต้องเป็นคำ ไม่ใช่ emoji
อาจารย์ให้เปลี่ยนไอคอนเป็นคำที่สื่อความหมาย — `tests/test_home_entrypoint.py::test_ui_labels_are_words_not_decorative_icons` fail ถ้ามีไอคอนกลับมา (ยกเว้นบรรทัดที่เป็น path ไฟล์ใน `pages/`)

### 7.9 Widget key ของฟอร์มแก้ไขต้องผูกกับ id ของแถว
Streamlit จำค่าของ widget ที่มี `key=` คงที่ข้าม rerun และไม่สนใจ `value=` — เคยทำให้หน้าจัดการผู้ใช้เอาชื่อของบัญชีก่อนหน้าไปบันทึกทับบัญชีใหม่ ใช้ `key=f"_edit_role_{user_id}"`

### 7.10 เนื้อใน `st.expander` รันทุกครั้ง แม้พับอยู่
ของที่ช้า (network, query ใหญ่) ใน expander จะทำงานทุก rerun — ต้อง `@st.cache_data`

---

## 8. ก่อน commit / ก่อนปิดงาน

- [ ] รัน `pytest tests\ --ignore=tests\test_config.py -q` → ผ่าน 100%
- [ ] เพิ่ม regression test สำหรับการแก้ bug
- [ ] ลบไฟล์ชั่วคราว `_*.py`, `_*.txt` ออกจาก project root
- [ ] ไม่แตะ `.env` (gitignored — มี secrets)
- [ ] ไม่แตะ `data/` (gitignored — runtime data)
- [ ] ถ้าแก้ schema DB → migration ต้องไม่ break ของเก่า + อัปเดต `docs/database_design.md`
- [ ] ถ้าเปลี่ยน prompt → ทดสอบ end-to-end อย่างน้อย 1 ไฟล์เสียงจริงก่อน
- [ ] action ใหม่ที่เปลี่ยนข้อมูล → มี `audit()` บันทึกไว้
- [ ] ห้ามลบลูกค้า/ทะเบียน/บัญชีผู้ใช้ออกจาก DB จริง — ใช้ซ่อน / ปิดใช้งาน
- [ ] ป้ายใหม่ใน UI เป็นคำ ไม่ใช่ emoji

---

## 9. ไฟล์เอกสารที่เกี่ยวข้อง

| ไฟล์ | เนื้อหา |
|------|---------|
| `CLAUDE.md` | คู่มือสำหรับ Claude Code — เนื้อหาเดียวกับไฟล์นี้ในภาษาอังกฤษ (แก้ไฟล์หนึ่งให้แก้อีกไฟล์ด้วย) |
| `README.md` | ภาพรวมโปรเจค + tech stack |
| `SETUP.md` | คู่มือติดตั้งเชิงลึก + troubleshooting |
| `ONE_CLICK_RUN.md` | คู่มือ launcher สำหรับเครื่อง demo / handoff |
| `CHANGELOG.md` | ประวัติ release |
| `docs/architecture.md` | โครงสร้าง + data flow |
| `docs/database_design.md` | ER diagram + data dictionary |
| `docs/user_manual.md` | คู่มือผู้ใช้ business |
| `docs/OMAZZ_RELEASE_CHECKLIST.md` | Checklist ก่อนส่งมอบ / live demo |
| `.env.example` | template ของ env vars (อ่านได้ — ไม่มี secret) |

---

## 10. การติดต่อสื่อสาร

- ตอบเป็นภาษาไทย (codebase + UI เป็น Thai-first)
- ตรงประเด็น ไม่ทักทาย ไม่ acknowledgment phrases
- ใช้ Markdown citation format `@<absolute_path>:<line>` เมื่ออ้างอิงโค้ด
- แสดง diff สำคัญด้วย table หรือ before/after เมื่อทำการแก้ไขที่กระทบ output
