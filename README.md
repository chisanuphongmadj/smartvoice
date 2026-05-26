# SmartVoice

AI-powered Call Center Analytics สำหรับสายภาษาไทย: รับไฟล์เสียง, ถอดเสียง, แยกผู้พูด, วิเคราะห์คุณภาพการสนทนาด้วย LLM, และจัดกลุ่มเคสลูกค้าในเครื่องเดียว

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | Streamlit แบบ multi-page |
| Database | SQLite 3 |
| STT (default) | `biodatlab/distill-whisper-th-large-v3` ผ่าน `transformers` |
| STT (alternative) | `faster-whisper` สำหรับ `large-v3`, `large-v3-turbo`, หรือโมเดล CT2 native |
| Speaker Diarization | `pyannote/speaker-diarization-3.1` |
| LLM | Ollama + `scb10x/llama3.1-typhoon2-8b-instruct` |

## Current Capabilities

- Upload `.wav` / `.mp3`, ตรวจ magic bytes, จำกัดขนาดไฟล์ 100 MB, และ deduplicate ด้วย SHA-256
- ดึงเบอร์โทร, ทิศทางสาย (Inbound/Outbound), และรหัส Agent จากชื่อไฟล์อัตโนมัติ; เชื่อมลูกค้า/รับประกันอัตโนมัติ และบันทึกผู้ upload เพื่อ audit
- ถอดเสียง + diarization + speaker correction แบบหลายชั้น โดยผสม LLM กับ heuristic rules ภาษาไทย
- วิเคราะห์ 4 ด้านแยกกัน: summary/topic/topic_detail, sentiment, agent QA พร้อมหลักฐานคะแนน, anomaly
- จัดกลุ่มเคสอัตโนมัติด้วย recency short-circuit ก่อนใช้ LLM match
- Dashboard + Admin scale-friendly สำหรับ 10K+ ไฟล์ (load-limit picker, SQL-side counts), drill-down chart สำหรับประเภทความเสียหายภายใน "แจ้งปัญหาสินค้า"
- Filter ตามทิศทางสาย (Inbound/Outbound) บนหน้า Admin และตามรหัส Agent ใน Agent Performance
- Settings page อัจฉริยะ — auto-detect GPU + ซ่อน `cuda` ถ้าไม่พบ, auto-apply Backend/Device/Compute ที่แนะนำเมื่อเปลี่ยน Whisper model, validate combo compatibility ก่อน save
- มี customer/warranty view, case management, case merge, login, และ deployment readiness checks

## Project Structure

```text
smartvoice/
├── Home.py                        # หน้า Home + deployment readiness
├── pages/
│   ├── 1_📤_Admin.py              # Upload, process, case management
│   ├── 2_📊_Dashboard.py          # Analytics dashboard
│   ├── 3_👥_Customers.py          # Customer + warranty browse
│   └── 4_Settings.py              # Demo/AI presets + readiness checks
├── smartvoice/
│   ├── auth.py                    # Sidebar login + PBKDF2 helpers
│   ├── cli.py                     # `smartvoice` console entrypoint
│   ├── config.py                  # Environment config ทั้งหมด
│   ├── db.py                      # SQLite schema, migrations, CRUD
│   ├── env_settings.py            # อ่าน/เขียน `.env` จากหน้า Settings
│   ├── file_manager.py            # Upload validation + SHA-256 dedup
│   ├── logger.py                  # Rotating logger
│   ├── ollama_client.py           # LLM client + JSON parsing
│   ├── pipeline.py                # Core orchestration
│   ├── preflight.py               # Deployment readiness checks
│   ├── prompts.py                 # Prompt templates
│   ├── ui_helpers.py              # CSS, login, background processing
│   └── stt/
│       ├── audio.py               # Load, resample, denoise
│       ├── diarize.py             # pyannote wrapper
│       ├── orchestrator.py        # Audio → STT → diarization
│       └── transcribe.py          # `transformers` + `faster-whisper`
├── scripts/
│   ├── backfill_topic_detail.py     # Re-classify topic_detail for legacy calls
│   ├── extract_pdf.py
│   ├── generate_er_diagram.py
│   ├── make_password_hash.py
│   ├── scrub_existing_next_actions.py
│   └── seed_mock_data.py
├── tests/                          # pytest suite
├── docs/
│   ├── architecture.md
│   ├── database_design.md
│   ├── OMAZZ_RELEASE_CHECKLIST.md
│   ├── report_corrections.md
│   └── user_manual.md
├── data/                           # runtime data (gitignored)
│   ├── logs/
│   ├── models/
│   ├── raw_audio/
│   └── smartvoice.db
├── CHANGELOG.md
├── ONE_CLICK_RUN.md
├── SETUP.md
├── requirements.txt
└── .env.example
```

## Database Tables

| Table | คำอธิบาย |
|-------|----------|
| `calls` | ไฟล์เสียง, transcript, ผลวิเคราะห์ AI, สถานะ, audit uploader, และ `case_id` |
| `customers` | ข้อมูลลูกค้า |
| `warranty_registrations` | ทะเบียนรับประกันสินค้า |
| `call_customer_links` | ความสัมพันธ์ระหว่างสาย, ลูกค้า, และ warranty |
| `cases` | กลุ่มสายของลูกค้าคนเดียวกันในเรื่องเดียวกัน |

## Quick Start

### Windows

```powershell
run.bat
```

ตัว launcher จะสร้าง `.venv`, ติดตั้ง dependency, สร้าง `.env`, ตรวจ CUDA/Ollama, และเปิด `http://localhost:8501`

### Manual run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e . --no-deps
copy .env.example .env
streamlit run Home.py
```

ดูรายละเอียดเต็มใน [`SETUP.md`](SETUP.md) และคู่มือส่งต่อเครื่องใน [`ONE_CLICK_RUN.md`](ONE_CLICK_RUN.md)

## Core Environment Variables

```env
WHISPER_MODEL=biodatlab/distill-whisper-th-large-v3
WHISPER_BACKEND=transformers
WHISPER_DEVICE=auto
WHISPER_COMPUTE=auto
MOCK_STT=false
HF_TOKEN=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
CASE_RECENCY_HOURS=4.0
SMARTVOICE_USERS=
PROCESSING_STALE_MINUTES=180
```

## Processing Pipeline

```text
Audio (.wav/.mp3)
  → validate + save + optional phone auto-link
  → load / resample / denoise
  → Whisper STT + pyannote diarization
  → heuristic cleanup + transcript cleanup LLM
  → speaker correction LLM + deterministic Thai role rules
  → LLM analysis 4 calls
  → SQLite save
  → auto case assignment
  → Streamlit UI
```

## LLM Output Fields

| Field | Description |
|-------|-------------|
| `summary` | สรุปบทสนทนา |
| `topic` | หัวข้อหลักที่ลูกค้าติดต่อ |
| `topic_detail` | ประเภทความเสียหายเฉพาะ — กรอกเมื่อ `topic="แจ้งปัญหาสินค้า"` เท่านั้น (vocabulary: `ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ`) |
| `sentiment` | `positive` / `neutral` / `negative` |
| `sentiment_reason` | เหตุผลประกอบ sentiment |
| `agent_performance` | `politeness`, `politeness_evidence`, `problem_solving`, `problem_solving_evidence`, `overall_score`, `next_action`, `next_action_owner` |
| `keywords` | คำสำคัญ |
| `brand_mentions` | แบรนด์ที่ถูกพูดถึง |
| `platform_mentions` | แพลตฟอร์มหรือช่องทางที่ถูกพูดถึง |
| `anomaly_detected` | พบ anomaly หรือไม่ |
| `anomaly_reason` | เหตุผลพร้อมหลักฐานจาก transcript |
| `anomaly_severity` | `low` / `medium` / `high` |

## Tests

ชุดทดสอบปัจจุบัน:

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

ผลล่าสุดที่ยืนยันแล้ว: `209 passed` (ทดสอบเมื่อ 2026-05-27)
