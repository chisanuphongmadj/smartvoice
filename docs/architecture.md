# SmartVoice — Architecture & Data Flow

---

## 1. ภาพรวมระบบ (High-Level)

```
┌─────────────────────────────────────────────────────────────────┐
│                      SmartVoice (Local Desktop App)              │
│                                                                  │
│  ┌─────────────┐    ┌───────────────┐    ┌──────────────────┐   │
│  │  Streamlit  │ ←→ │   Pipeline    │ ←→ │   SQLite DB      │   │
│  │     UI      │    │  (Background  │    │  (5 tables)      │   │
│  │   (pages)   │    │   Threads)    │    │                  │   │
│  └─────────────┘    └───────┬───────┘    └──────────────────┘   │
│                             │                                    │
│           ┌─────────────────┼────────────────┐                  │
│           ▼                 ▼                ▼                   │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│    │  Whisper    │  │   pyannote  │  │   Ollama    │            │
│    │    STT      │  │ Diarization │  │    LLM      │            │
│    │ (transformers)│  │    (HF)   │  │  (local)    │            │
│    └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Technology | หน้าที่ |
|-----------|-----------|---------|
| **UI** | Streamlit | หน้าเว็บอัปโหลด + dashboard + customer management |
| **Pipeline** | Python threading | จัดการ workflow: STT → Diarize → Cleanup → Analyze |
| **STT** | biodatlab/distill-whisper-th-large-v3 | ถอดเสียง Thai |
| **Diarization** | pyannote/speaker-diarization-3.1 | แยกผู้พูด |
| **LLM** | scb10x/llama3.1-typhoon2-8b (via Ollama) | วิเคราะห์ conversation |
| **Storage** | SQLite 3 | persist calls, customers, cases, warranties |
| **Audio Files** | Filesystem (`data/raw_audio/`) | เก็บไฟล์ `.wav` / `.mp3` |

---

## 2. Data Flow — การประมวลผลสาย

```
 User                Admin Page              Pipeline                 External Services
  │                      │                       │                          │
  ├─upload audio─────────►│                       │                          │
  │                      ├─save file + hash──────►│                          │
  │                      │                       ├─STT────────────────────► Whisper
  │                      │                       │◄───raw segments──────────┤
  │                      │                       ├─Diarize────────────────► pyannote
  │                      │                       │◄───speakers──────────────┤
  │                      │                       ├─Cleanup transcript─────► Ollama LLM
  │                      │                       │◄───cleaned text──────────┤
  │                      │                       ├─Correct speakers───────► Ollama LLM
  │                      │                       │◄───corrected─────────────┤
  │                      │                       ├─Analyze (4 parallel)───► Ollama LLM
  │                      │                       │◄───summary/topic/QA/anomaly┤
  │                      │                       ├─Match case─────────────► Ollama LLM
  │                      │                       │◄───case_id───────────────┤
  │                      │                       ├─Save to DB               │
  │                      │◄──status: done────────┤                          │
  │◄─view dashboard──────┤                       │                          │
```

### 7 Steps of `process_call()`

| # | Step | Technology | Output |
|---|------|-----------|--------|
| 1 | 🎙 Transcribe + Diarize | Whisper + pyannote | Raw segments with speaker |
| 2 | 🧹 Cleanup transcript | Ollama LLM | Corrected Thai text |
| 3 | 🗣️ Correct speakers | Ollama LLM | Proper Agent/Customer mapping |
| 4 | 🤖 Analyze (x4) | Ollama LLM | Summary, Sentiment, QA, Anomaly |
| 5 | 💾 Save results | SQLite | Persist to `calls` table |
| 6 | 📂 Auto-assign case | Ollama LLM | Group related calls into a case |
| 7 | ✅ Done | — | Status updated, UI auto-refreshes |

---

## 3. Auto-Linking (Upload Time)

ตอน upload ไฟล์ ระบบจะพยายาม**เชื่อมลูกค้าอัตโนมัติ**ก่อนเริ่ม process:

```
filename: "20251225134209-...-0631451550-Inbound.wav"
                                     │
                                     ▼
                    extract_phone_from_filename()
                                     │
                                     ▼
                         get_customer_by_phone()
                          │                  │
                     found │                  │ not found
                          ▼                  ▼
                   link_call_customer    skip (user can link manually later)
                   matched_by='auto_phone'
                          │
                          ▼
                  get_warranties_by_customer()
                  (pick latest warranty)
```

---

## 4. Auto-Case Assignment (After Analysis)

หลังวิเคราะห์ครบ ระบบจะจัดกลุ่มเคสอัตโนมัติ:

```python
if no customer linked:
    skip case assignment

existing_open_cases = get_open_cases_by_customer(customer_id)

if no open cases:
    create_case(customer_id, subject=new_topic)
else:
    # Ask LLM to decide
    result = llm.match_case(new_topic, new_summary, existing_open_cases)
    if result.match_case_id:
        assign_call_to_case(call_id, matched_id)
        update_case_status(matched_id, 'follow_up')
    else:
        create_case(customer_id, subject=result.suggested_subject)
```

---

## 5. Concurrency Model

- **UI:** Streamlit ใช้ `@st.fragment(run_every=3)` auto-refresh สถานะ processing
- **Pipeline:** ทำงานใน **daemon thread** (`threading.Thread`)
  - **Single-call:** `launch_processing(call_id)` — 1 thread per call
  - **Queue:** `launch_processing_queue([ids])` — 1 thread, serial through all ids
- **Lock:** `_processing_lock` + `_queue_lock` — กันการ process ซ้ำ
- **⚠️ Limitation:** ถ้า app restart ระหว่าง processing → งานหาย (no persistent queue)
  - Production improvement: ใช้ Celery + Redis หรือ PostgreSQL job queue

---

## 6. Project Structure

```
smartvoice/
├── app.py                         # Streamlit entry (home page)
├── pages/
│   ├── 1_📤_Admin.py              # Upload + processing + case management
│   ├── 2_📊_Dashboard.py          # Analytics charts
│   └── 3_👥_Customers.py          # Customer/warranty browse
├── smartvoice/                    # Core package
│   ├── __init__.py
│   ├── config.py                  # Env-based config
│   ├── logger.py                  # Centralized logging
│   ├── db.py                      # SQLite schema + CRUD
│   ├── file_manager.py            # File I/O + validation
│   ├── ollama_client.py           # LLM client (4 analyze calls)
│   ├── prompts.py                 # Thai LLM prompt templates
│   ├── pipeline.py                # Full processing orchestration
│   ├── ui_helpers.py              # Shared UI + background launchers
│   ├── cli.py                     # `smartvoice` command
│   └── stt/                       # Speech-to-Text sub-package
│       ├── audio.py               # Audio load/resample/denoise
│       ├── diarize.py             # pyannote wrapper
│       ├── transcribe.py          # Whisper wrapper
│       └── orchestrator.py        # STT + diarize orchestration
├── scripts/
│   ├── seed_mock_data.py          # Seed demo customers + warranties
│   └── generate_er_diagram.py     # Render ER diagram PNG
├── tests/                         # pytest unit tests
├── docs/
│   ├── database_design.md         # ER diagram + data dictionary
│   ├── architecture.md            # This file
│   ├── user_manual.md             # End-user manual
│   └── er_diagram.png             # Rendered ER diagram
├── data/                          # Runtime data (gitignored where appropriate)
│   ├── raw_audio/                 # Uploaded audio
│   ├── smartvoice.db              # SQLite database
│   ├── logs/                      # Rotating log files
│   └── models/                    # CTranslate2 cached models
├── requirements.txt
├── pyproject.toml
├── .env.example
├── run.bat                        # Windows launcher
├── run.sh                         # Linux/Mac launcher
├── README.md
├── SETUP.md
└── CHANGELOG.md
```

---

## 7. Security Model

| Threat | Mitigation |
|--------|-----------|
| **SQL injection** | ใช้ parameterized queries ทุกจุด |
| **Path traversal** via filename | `sanitize_filename()` strip path separators |
| **Oversized upload** | `MAX_FILE_SIZE_MB = 100` + magic-byte check |
| **Secret leakage** | `.env` gitignored + `HF_TOKEN` loaded at runtime |
| **Multi-user conflict** | ⚠️ ปัจจุบันยังไม่รองรับ — เป็น single-user local app |

### สิ่งที่ยังไม่มี (ถ้าจะทำ multi-user deploy)
- Authentication (login + session)
- Role-based access (Admin vs QA vs Supervisor)
- Rate limiting
- HTTPS reverse proxy (nginx/Caddy)
- Database encryption at rest

---

## 8. Performance Characteristics

| Phase | Typical Duration (GPU) | Typical Duration (CPU) |
|-------|----------------------|------------------------|
| STT (Whisper) | ~15% of audio length | ~100% of audio length |
| Diarization | ~10% of audio length | ~50% of audio length |
| LLM cleanup | ~5-15 sec | ~5-15 sec |
| LLM correct | ~5-15 sec | ~5-15 sec |
| LLM analyze (4x) | ~15-30 sec | ~15-30 sec |
| LLM match case | ~2-5 sec | ~2-5 sec |
| **Total (5-min call)** | **~1-2 min** | **~6-10 min** |

> GPU: NVIDIA GTX 1660 / RTX 3060+ / CUDA 12.x
> CPU: Ryzen/Core i5+ with 16 GB RAM

---

## 9. Extension Points

จุดที่ออกแบบไว้ให้แก้/ต่อยอดง่าย:

- **เปลี่ยน LLM:** แก้ `OLLAMA_MODEL` ใน `.env`
- **เปลี่ยน STT model:** แก้ `WHISPER_MODEL` ใน `.env`
- **เพิ่ม analysis call:** เพิ่มฟังก์ชันใน `ollama_client.py` + prompt ใน `prompts.py` + รวมเข้า `analyze_transcript()`
- **เพิ่มตาราง DB:** เพิ่ม `CREATE TABLE` ใน `db.init_db()` + migration ใน `_migrate()`
- **เปลี่ยน UI theme:** แก้ CSS ใน `ui_helpers.py:_CSS`
- **Migrate to PostgreSQL:** เปลี่ยน `sqlite3` → `psycopg2` ใน `db.py`; schema ใช้ได้เลย
