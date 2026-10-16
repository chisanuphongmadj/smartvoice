# SmartVoice

AI-powered Call Center Analytics สำหรับสายภาษาไทย: รับไฟล์เสียง, ถอดเสียง, แยกผู้พูด, วิเคราะห์คุณภาพการสนทนาด้วย LLM (ตรวจคำตอบของ AI ก่อนบันทึกทุกครั้ง), จัดกลุ่มและติดตามเคสลูกค้า, เก็บข้อมูลลูกค้า / ทะเบียนรับประกัน / ใบสั่งขาย และออกรายงาน — ทำงานในเครื่องเดียว

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | Streamlit แบบ multi-page (`st.navigation` + สิทธิ์ตาม role) |
| Database | SQLite 3 |
| STT (default) | `biodatlab/distill-whisper-th-large-v3` ผ่าน `transformers` |
| STT (alternative) | `faster-whisper` สำหรับ `large-v3`, `large-v3-turbo`, หรือโมเดล CT2 native |
| Speaker Diarization | `pyannote/speaker-diarization-3.1` |
| LLM | Ollama + `scb10x/llama3.1-typhoon2-8b-instruct` |
| รายงาน | `fpdf2` + `uharfbuzz` (PDF ภาษาไทย), `openpyxl` (Excel ใบสั่งขาย) |

## Current Capabilities

**ประมวลผลสาย**
- Upload `.wav` / `.mp3`, ตรวจ magic bytes, จำกัดขนาดไฟล์ 100 MB, และ deduplicate ด้วย SHA-256
- ดึงเบอร์โทร, ทิศทางสาย (Inbound/Outbound), รหัสพนักงาน และเวลาโทรจริงจากชื่อไฟล์อัตโนมัติ; เชื่อมลูกค้า/รับประกันอัตโนมัติจากเบอร์
- ถอดเสียง + diarization + speaker correction แบบหลายชั้น โดยผสม LLM กับ heuristic rules ภาษาไทย
- วิเคราะห์ 5 คำขอแยกกัน: สรุป/หัวข้อ/ประเภทปัญหา, อารมณ์ลูกค้า, คะแนนพนักงาน, สิ่งที่ต้องทำต่อ, ความผิดปกติ
- **AI เสนอ ระบบตัดสิน** (`insight_rules.py`) — คะแนนพนักงานนับเฉพาะข้อที่มีคำพูดของพนักงานในสายจริง, ความผิดปกติต้องมีคำพูดจริงที่มีคำของหมวดนั้น, แบรนด์/ช่องทางนับเฉพาะที่พูดจริงและรวมชื่อสะกดต่างกัน
- จัดกลุ่มเคสอัตโนมัติ (สายจากลูกค้าเดิมภายในไม่กี่ชั่วโมงเข้าเคสเดิมทันที ไม่งั้นให้ LLM เทียบหัวข้อ)

**งานลูกค้า**
- **จัดการเคส** — พนักงานกด "รับเคส" เอง คนอื่นแย่งไม่ได้, เปลี่ยนสถานะ/ปิดเคสได้เฉพาะผู้รับ, แจ้งเตือนเข้า Discord ทุกการรับ/คืน/ปิดเคส; ตารางเคสบอกเรื่องที่ลูกค้าแจ้ง สิ่งที่ต้องทำต่อ และความเร่งด่วน
- **ลูกค้าและการรับประกัน** — คลิกแถวลูกค้าเพื่อดูทะเบียนรับประกัน (พร้อมหลักฐานการซื้อ), ใบสั่งขาย, เคส และสายทั้งหมด
- **ทะเบียนรับประกัน** ตามแบบระบบของบริษัท — เลขที่ SO, Ref Id, สถานะ ใช้งาน/ยกเลิก, แนบรูปใบเสร็จ/สลิป
- **ใบสั่งขาย (SO)** — นำเข้าจาก Excel/CSV (แม่แบบของระบบ หรือไฟล์ export จาก NAV), เพิ่ม/แก้ไขทีละใบ, ดูทั้งใบแบบเดียวกับเอกสารของบริษัท, ผูกกับลูกค้าอัตโนมัติจากเบอร์
- **หน้าเพิ่มข้อมูล** (Admin) — เพิ่ม / แก้ไข / ซ่อน / กู้คืน ลูกค้าและทะเบียนรับประกัน พร้อมตรวจเบอร์และเลขทะเบียนซ้ำ และคำนวณวันหมดประกันอัตโนมัติ

**Dashboard** (5 หน้า ใช้ตัวกรองร่วมกัน)
- ภาพรวม · คีย์เวิร์ด แบรนด์ ช่องทาง · สายที่ผิดปกติ · ผลงานพนักงาน · รายการสาย
- **ส่งออกรายงาน** ทุกหน้า: รายงาน PDF (กราฟและตารางทุกหน้า), สรุปตัวเลข CSV, รายการสาย CSV — ตามตัวกรองที่เลือก เปิดใน Excel แล้วภาษาไทยไม่เพี้ยน
- ตารางที่มีข้อความยาว คลิกช่องไหนก็ได้เพื่อเปิดอ่านเต็มในหน้าต่าง

**ระบบ**
- **Login จริง + สิทธิ์ตาม role** — 4 บทบาท (Admin / Supervisor / QA / Agent), เมนูแสดงเฉพาะหน้าที่มีสิทธิ์, ตรวจสิทธิ์ซ้ำฝั่ง server ทุกหน้า, ล็อก 60 วินาทีเมื่อใส่รหัสผิด 5 ครั้ง
- **นโยบายบัญชี** — Admin เปิด/ปิดบัญชีได้แต่ตั้งหรือรีเซ็ตรหัสผ่านของคนอื่นไม่ได้ และไม่มีการลบบัญชีถาวร
- **ไม่ลบข้อมูลลูกค้าจริง (soft delete)** — "ลบ" ลูกค้า/ทะเบียน/SO คือซ่อน แถวยังอยู่ครบและกู้คืนได้
- **Audit log ทั้งระบบ** — การเข้าสู่ระบบ, บัญชี, ลูกค้า/ทะเบียน/SO, สาย, เคส, การตั้งค่า และการส่งออกรายงาน พร้อมค่าก่อน→หลัง (Admin + Supervisor)
- ภาษาไทยทั้งหน้าจอ เวลาแสดงเป็นเวลาไทย (UTC+7); หน้าแรก / Admin / Dashboard รองรับ 10K+ ไฟล์
- Settings page — auto-detect GPU, แนะนำ Backend/Device/Compute ตาม Whisper model, ตรวจ combo ก่อน save

## Project Structure

```text
smartvoice/
├── Home.py                        # Router (เมนูตาม role) + หน้าแรก "งานที่รอคุณ"
├── pages/
│   ├── 1_📤_Admin.py              # อัปโหลดและประมวลผลเสียง
│   ├── 2_📊_Dashboard.py          # Dashboard — ภาพรวม
│   ├── 3_👥_Customers.py          # ลูกค้าและการรับประกัน
│   ├── 4_Settings.py              # ตั้งค่าระบบ (Admin + Supervisor)
│   ├── 5_👤_Users.py               # จัดการผู้ใช้ (Admin)
│   ├── 6_➕_Data_Entry.py          # เพิ่ม/แก้ไขข้อมูลลูกค้า (Admin)
│   ├── 7_📜_Audit_Log.py           # ประวัติการใช้งาน (Admin + Supervisor)
│   ├── 8_Dashboard_Insights.py    # Dashboard — คีย์เวิร์ด แบรนด์ ช่องทาง
│   ├── 9_Dashboard_Anomaly.py     # Dashboard — สายที่ผิดปกติ
│   ├── 10_Agent_Performance.py    # Dashboard — ผลงานพนักงาน
│   ├── 11_Cases.py                # จัดการเคส (รับเคส / ปิดเคส)
│   ├── 12_Call_Summaries.py       # Dashboard — รายการสาย
│   └── 13_Sales_Orders.py         # ใบสั่งขาย (SO)
├── smartvoice/
│   ├── audit.py                   # Audit trail vocabulary + record()
│   ├── auth.py                    # Login, PBKDF2 hashing, role permissions
│   ├── case_workflow.py           # รับเคส / คืนเคส / เปลี่ยนสถานะ + สรุปเคส
│   ├── cli.py                     # `smartvoice` console entrypoint
│   ├── config.py                  # Environment config ทั้งหมด
│   ├── customer_entry.py          # Validation ของหน้าเพิ่มข้อมูล
│   ├── customer_view.py           # ตาราง/รายละเอียดลูกค้าในหน้าลูกค้า
│   ├── dashboard_common.py        # ตัวกรองร่วม, สไตล์กราฟ, ปุ่มส่งออกรายงาน
│   ├── dashboard_report.py        # รายงาน PDF / CSV + สูตรคะแนนพนักงาน
│   ├── db.py                      # SQLite schema, migrations, CRUD
│   ├── discord_notify.py          # แจ้งเตือน Discord (webhook)
│   ├── env_settings.py            # อ่าน/เขียน `.env` จากหน้า Settings
│   ├── file_manager.py            # Upload validation, SHA-256 dedup, หลักฐานการซื้อ
│   ├── insight_rules.py           # ตรวจคำตอบของ LLM ก่อนบันทึก
│   ├── labels.py                  # คำภาษาไทยของทุกรหัส + เวลาไทย
│   ├── logger.py                  # Rotating logger
│   ├── ollama_client.py           # LLM client + JSON parsing
│   ├── pipeline.py                # Core orchestration
│   ├── preflight.py               # Deployment readiness checks
│   ├── prompts.py                 # Prompt templates
│   ├── sales_orders.py            # นำเข้า/บันทึกใบสั่งขาย + แม่แบบ Excel
│   ├── so_view.py                 # แสดงใบสั่งขายแบบเอกสาร
│   ├── ui_helpers.py              # CSS, login page, role guard, background processing
│   └── stt/
│       ├── audio.py               # Load, resample, denoise
│       ├── diarize.py             # pyannote wrapper
│       ├── orchestrator.py        # Audio → STT → diarization
│       └── transcribe.py          # `transformers` + `faster-whisper`
├── scripts/
│   ├── backfill_topic_detail.py   # Re-classify topic_detail for legacy calls
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
│   ├── warranty_proofs/            # รูป/PDF หลักฐานการซื้อ
│   └── smartvoice.db
├── AGENTS.md / CLAUDE.md           # คู่มือสำหรับ AI coding agents
├── CHANGELOG.md
├── ONE_CLICK_RUN.md
├── SETUP.md
├── requirements.txt
└── .env.example
```

## Database Tables

| Table | คำอธิบาย |
|-------|----------|
| `calls` | ไฟล์เสียง, transcript, ผลวิเคราะห์ AI, สถานะ, ผู้อัปโหลด, และ `case_id` |
| `customers` | ข้อมูลลูกค้า รวมชื่อเล่นและช่องทาง (soft delete ผ่าน `deleted_at`) |
| `warranty_registrations` | ทะเบียนรับประกัน — เลขที่ SO, Ref Id, สถานะ ใช้งาน/ยกเลิก, หลักฐานการซื้อ (soft delete) |
| `sales_orders` | หัวใบสั่งขาย — วันที่, ข้อมูลการขาย, ผู้ซื้อ, ผู้รับ, ยอดเงิน (soft delete) |
| `sales_order_lines` | รายการสินค้าในใบสั่งขาย |
| `call_customer_links` | ความสัมพันธ์ระหว่างสาย, ลูกค้า, และ warranty |
| `cases` | กลุ่มสายของลูกค้าคนเดียวกันในเรื่องเดียวกัน + ผู้รับเคส |
| `users` | บัญชีพนักงาน — username, ชื่อที่แสดง, role, PBKDF2 hash, สถานะเปิด/ปิด |
| `audit_log` | ประวัติการใช้งานแบบเขียนเพิ่มอย่างเดียว — ใคร ทำอะไร กับอะไร เมื่อไหร่ ค่าก่อน→หลัง |

รายละเอียดคอลัมน์ทั้งหมดอยู่ใน [`docs/database_design.md`](docs/database_design.md)

## First Login

เปิดแอปครั้งแรก ระบบสร้างบัญชี `admin` / `admin1234` ให้อัตโนมัติ — **เปลี่ยนรหัสผ่านทันที** ที่กล่องบัญชีใน sidebar (ระบบจะเตือนค้างไว้จนกว่าจะเปลี่ยน) แล้วสร้างบัญชีพนักงานที่หน้า "จัดการผู้ใช้"

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

> อัปเดตจากเวอร์ชันก่อน: รัน `pip install -r requirements.txt` อีกครั้ง (เพิ่ม `openpyxl`, `fpdf2`, `uharfbuzz`) — ฐานข้อมูลเดิมจะถูกเพิ่มตาราง/คอลัมน์ใหม่ให้เองตอนเปิดแอป ข้อมูลเดิมไม่เปลี่ยน

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
OLLAMA_NUM_CTX=12288          # context ของ LLM (Ollama ตั้งต้น 4096 ซึ่งไม่พอ)
CASE_RECENCY_HOURS=4.0
SMARTVOICE_USERS=
PROCESSING_STALE_MINUTES=180
DISCORD_WEBHOOK_URL=          # แจ้งเตือนการรับ/ปิดเคส (ว่าง = ไม่ส่ง)
REPORT_FONT_PATH=             # ฟอนต์ไทยของรายงาน PDF (ว่าง = Tahoma/Leelawadee อัตโนมัติ)
```

## Processing Pipeline

```text
Audio (.wav/.mp3)
  → validate + save + optional phone auto-link
  → load / resample / denoise
  → Whisper STT + pyannote diarization
  → heuristic cleanup + transcript cleanup LLM
  → speaker correction LLM + deterministic Thai role rules
  → LLM analysis 5 requests (JSON mode, temperature 0)
  → insight_rules: verify quotes, compute scores/flags
  → SQLite save
  → auto case assignment
  → Streamlit UI
```

## LLM Output Fields

| Field | Description |
|-------|-------------|
| `summary` | สรุปบทสนทนา |
| `topic` | หัวข้อหลักที่ลูกค้าติดต่อ (จำกัดไว้ 9 หัวข้อ) |
| `topic_detail` | ประเภทความเสียหาย — กรอกเมื่อ `topic="แจ้งปัญหาสินค้า"` เท่านั้น (`ผ้าขาด/ผ้าหุ้มชำรุด`, `เตียง/โครงหัก`, `สปริง/ฟองน้ำยุบ`, `เปื้อน/รอยขีดข่วน`, `กลิ่น/แพ้/ระคายเคือง`, `ความชื้น/น้ำท่วม`, `ขนาด/สเปคผิด`, `อื่นๆ`) |
| `sentiment` | `positive` / `neutral` / `negative` (ตรวจซ้ำด้วยคำพูดลูกค้า) |
| `sentiment_reason` | เหตุผลพร้อมคำพูดของลูกค้า |
| `agent_performance` | `politeness`, `politeness_evidence`, `problem_solving`, `problem_solving_evidence`, `overall_score`, `next_action`, `next_action_owner` — คะแนนคำนวณใหม่ใน Python จากคำพูดที่ยืนยันแล้ว |
| `keywords` | คำสำคัญ |
| `brand_mentions` | แบรนด์ที่ถูกพูดถึงจริงในสาย (ชื่อมาตรฐานเดียว) |
| `platform_mentions` | ช่องทางซื้อ/ติดต่อที่ถูกพูดถึง |
| `anomaly_detected` | พบความผิดปกติหรือไม่ (ต้องมีคำพูดจริงเป็นหลักฐาน) |
| `anomaly_reason` | เหตุผลพร้อมคำพูดจาก transcript |
| `anomaly_severity` | `low` / `medium` / `high` — กำหนดจากหมวด ไม่ใช่จาก LLM |

## Tests

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

ผลล่าสุดที่ยืนยันแล้ว: `492 passed` (ทดสอบเมื่อ 2026-10-16)
