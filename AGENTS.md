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
streamlit run app.py    # → http://localhost:8501

# หรือใช้ launcher
run.bat                 # Windows
./run.sh                # Linux/macOS
```

**Test baseline:** 91 tests, ต้องผ่าน 100% ก่อน commit ทุกครั้ง

---

## 3. โครงสร้างไฟล์สำคัญ

```
smartvoice/
├── app.py                      # Streamlit home page
├── pages/                      # Streamlit multi-page (Admin / Dashboard / Customers / Settings)
├── smartvoice/                 # Business logic package
│   ├── config.py               # ⚠️ environment vars ทั้งหมดอยู่ที่นี่
│   ├── db.py                   # SQLite schema + CRUD (26 KB)
│   ├── pipeline.py             # 🔥 Core orchestrator (70 KB) — speaker correction, splitters, merge
│   ├── prompts.py              # 🔥 LLM prompts (54 KB) — system+user สำหรับทุก LLM call
│   ├── ollama_client.py        # LLM client + JSON extraction
│   ├── file_manager.py         # Upload + SHA-256 dedup
│   ├── ui_helpers.py           # CSS, badges, processing launcher
│   ├── auth.py                 # Streamlit login
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

**DB tables:** `calls`, `customers`, `warranty_registrations`, `call_customer_links`, `cases`

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
1. `extract_summary_and_topics()` — summary + topic + keywords
2. `analyze_sentiment()` — sentiment + reason
3. `evaluate_agent_qa()` — politeness + problem_solving + overall_score + next_action_owner
4. `detect_anomaly()` — anomaly flag + reason + severity

ทุก call → `extract_json()` → fallback เป็น empty dict ถ้า parse fail (log + continue)

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

## 7. Pitfalls / สิ่งที่เคยพังมาแล้ว

### 7.1 อย่าใช้ `cd` ใน `run_command`
PowerShell ใน Windows → ตั้ง `Cwd` แทน `cd && ...`

### 7.2 อย่าทำ test_config.py พัง
มัน manipulate env vars และ side-effect ต่อ test อื่น → ใช้ `--ignore=tests\test_config.py`

### 7.3 อย่าแก้ `_AGENT_MARKERS` / `_CUSTOMER_MARKERS` แบบเดาๆ
markers ใช้กับ `_enforce_role_rules` ที่ scoring ตำแหน่ง + role — เพิ่ม marker ที่กำกวมจะทำให้ flip ผิด ทำ regression test ครอบคลุมก่อนเพิ่ม

### 7.4 LLM prompt — เลี่ยง nested bullet
ปัญหาที่เจอจริง: LLM (Typhoon 8B) เคย copy sub-bullet เป็น `anomaly_reason` แม้ไม่มีหลักฐาน → ต้องระบุ keyword required list ชัดและสั่ง quote evidence

### 7.5 Pipeline เรียง step ผิด
`_aggressive_relabel_from_strong_cues` ต้องเรียก **ก่อน** `_merge_adjacent_same_speaker` ไม่งั้นการรวมจะ lock label ผิดถาวร

### 7.6 `created_at` ใน DB
คือเวลา **upload/process** ไม่ใช่ **วันที่โทรจริง** — วันที่โทรอยู่ใน filename pattern `YYYYMMDDHHMMSS-...`

---

## 8. ก่อน commit / ก่อนปิดงาน

- [ ] รัน `pytest tests\ --ignore=tests\test_config.py -q` → ผ่าน 100%
- [ ] เพิ่ม regression test สำหรับการแก้ bug
- [ ] ลบไฟล์ชั่วคราว `_*.py`, `_*.txt` ออกจาก project root
- [ ] ไม่แตะ `.env` (gitignored — มี secrets)
- [ ] ไม่แตะ `data/` (gitignored — runtime data)
- [ ] ถ้าแก้ schema DB → migration ต้องไม่ break ของเก่า + อัปเดต `docs/database_design.md`
- [ ] ถ้าเปลี่ยน prompt → ทดสอบ end-to-end อย่างน้อย 1 ไฟล์เสียงจริงก่อน

---

## 9. ไฟล์เอกสารที่เกี่ยวข้อง

| ไฟล์ | เนื้อหา |
|------|---------|
| `README.md` | ภาพรวมโปรเจค + tech stack |
| `SETUP.md` | คู่มือติดตั้งเชิงลึก + troubleshooting |
| `CHANGELOG.md` | ประวัติ release |
| `docs/architecture.md` | โครงสร้าง + data flow |
| `docs/database_design.md` | ER diagram + data dictionary |
| `docs/user_manual.md` | คู่มือผู้ใช้ business |
| `.env.example` | template ของ env vars (อ่านได้ — ไม่มี secret) |

---

## 10. การติดต่อสื่อสาร

- ตอบเป็นภาษาไทย (codebase + UI เป็น Thai-first)
- ตรงประเด็น ไม่ทักทาย ไม่ acknowledgment phrases
- ใช้ Markdown citation format `@<absolute_path>:<line>` เมื่ออ้างอิงโค้ด
- แสดง diff สำคัญด้วย table หรือ before/after เมื่อทำการแก้ไขที่กระทบ output
