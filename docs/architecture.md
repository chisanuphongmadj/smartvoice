# SmartVoice — Architecture & Data Flow

---

## 1. ภาพรวมระบบ

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         SmartVoice (Local App)                      │
│                                                                     │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────────────┐ │
│  │ Streamlit UI │ ↔  │ Pipeline       │ ↔  │ SQLite DB           │ │
│  │ 5 pages      │    │ daemon threads │    │ 5 tables            │ │
│  └──────────────┘    └────────┬───────┘    └─────────────────────┘ │
│                               │                                     │
│              ┌────────────────┼────────────────┐                    │
│              ▼                ▼                ▼                    │
│       ┌────────────┐   ┌────────────┐   ┌──────────────┐           │
│       │ Whisper STT│   │ pyannote   │   │ Ollama LLM   │           │
│       │ HF / FW    │   │ diarization│   │ local model  │           │
│       └────────────┘   └────────────┘   └──────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

| Component | หน้าที่ |
|-----------|---------|
| Streamlit UI | Home, Admin, Dashboard, Customers, Settings |
| Pipeline | Orchestrate STT, transcript cleanup, speaker correction, analysis, case assignment |
| SQLite | เก็บสาย, ลูกค้า, warranty, link, case |
| Whisper | ถอดเสียงไทย |
| pyannote | diarization |
| Ollama LLM | cleanup, speaker correction, extraction, sentiment, QA, anomaly, case matching |

---

## 2. UI Surface

| หน้า | หน้าที่ |
|------|---------|
| Home | KPI เร็ว + `Deployment readiness` |
| Admin | Upload, process, ค้นหา/กรอง, bulk delete, link ลูกค้า, จัดการ/รวมเคส |
| Dashboard | Charts, anomaly, agent performance พร้อม QA evidence, case summary, call summaries |
| Customers | ลูกค้า, warranty, เคส, สายที่เชื่อมไว้ |
| Settings | preset Demo / Real AI, แก้ `.env`, readiness checks |

หน้า `Settings` ต้อง login ก่อน และจำกัด role เป็น `Admin` หรือ `Supervisor`

---

## 3. Data Flow

```text
Upload audio
  → validate extension / size / magic bytes
  → SHA-256 dedup
  → optional phone extraction + auto customer link
  → background processing
  → STT + diarization
  → deterministic normalization / splitters
  → transcript cleanup LLM
  → speaker correction LLM
  → deterministic strong-cue relabel + role enforcement
  → LLM analysis 4 calls
  → save results to `calls`
  → auto case assignment
  → UI refresh
```

### `process_call()` stage summary

| Stage | สิ่งที่เกิดขึ้น |
|-------|----------------|
| 1. STT + diarization | ถอดเสียง, group segment, normalize, split, enforce role เบื้องต้น |
| 2. Transcript cleanup | ให้ LLM เก็บกวาดข้อความ แล้ว rerun splitter / normalization |
| 3. Speaker correction | ให้ LLM แก้ speaker turn แล้วตามด้วย deterministic strong cues + รอบ cleanup/splitter ซ้ำ |
| 4. Analysis | เรียก LLM 4 ครั้ง: extraction, sentiment, agent QA พร้อม evidence, anomaly |
| 5. Save | บันทึก transcript + analysis ลง DB |
| 6. Case assignment | ใช้ recency short-circuit ก่อน fallback ไป LLM case match |

หมายเหตุ: 4 analysis calls ทำแบบ **sequential** ใน `analyze_transcript()` ไม่ใช่ parallel

Agent QA score ถูก normalize ใน `ollama_client.evaluate_agent_qa()`: `politeness` และ `problem_solving` ถูก clamp ให้อยู่ช่วง 1-5, เก็บ evidence แยก, และ `overall_score` ถูกคำนวณจากคะแนนย่อยใน backend เพื่อลดผลเพี้ยนจาก LLM

---

## 4. Speaker Correction Strategy

Pipeline ไม่พึ่ง LLM อย่างเดียว เพราะ pyannote และ LLM ยังสลับบทบาทได้ในภาษาไทย call center

ลำดับสำคัญ:

1. Normalize คำโดเมนและ split turn แบบ deterministic
2. Cleanup transcript ด้วย LLM
3. Pre-split segment ยาว
4. Correct speakers ด้วย LLM
5. `_aggressive_relabel_from_strong_cues()`
6. Splitters หลายตัวสำหรับ opening, answer prefix, mixed Q/A, closing ฯลฯ
7. `_enforce_role_rules()`
8. Cleanup + splitters รอบสอง

ตัวอย่าง strong cues:

| Cue | Role |
|-----|------|
| `คุณลูกค้า`, `ทางบริษัท`, `พลอยขอ...` | Agent |
| `พี่สะดวก...`, `ติดตามเรื่องส่ง...`, `ได้ไหมลูก` | Customer |

---

## 5. Auto-Linking ตอน Upload

```text
filename
  → extract_phone_from_filename()
  → get_customer_by_phone()
      → found: create `call_customer_links` with `matched_by='auto_phone'`
      → not found: keep phone on `calls.customer_phone`
```

ถ้าพบลูกค้า ระบบจะเลือก warranty ล่าสุดของคนนั้นมาเชื่อมให้ด้วย

---

## 6. Auto-Case Assignment

ลำดับจริงใน `_auto_assign_case()`:

1. ถ้า call ยังไม่เชื่อมลูกค้า → skip
2. ถ้าไม่มี open/follow-up case → สร้างเคสใหม่ทันที
3. ถ้ามีเคสเปิด และสายล่าสุดในเคสนั้นอยู่ในหน้าต่าง `CASE_RECENCY_HOURS` → attach ทันทีโดยไม่ถาม LLM
4. ถ้าไม่เข้าเงื่อนไข recency → ส่ง topic/summary ไปให้ LLM match กับเคสเปิดเดิม
5. ถ้า LLM ไม่ match → สร้างเคสใหม่

เมื่อ attach เข้ากับเคสเดิม ระบบจะเปลี่ยนสถานะเคสเป็น `follow_up`

---

## 7. Concurrency & Recovery

- `launch_processing(call_id)` ใช้ 1 daemon thread ต่อสาย
- `launch_processing_queue(ids)` ใช้ daemon thread เดียวแล้วไล่ทีละสาย
- `_processing_lock` และ `_queue_lock` ป้องกันงานซ้ำ
- `@st.fragment(run_every=3)` ใช้ refresh สถานะบนหน้า Admin
- ถ้าแอปถูกปิดกลางทาง ระบบจะ reset สายที่ค้างเกิน `PROCESSING_STALE_MINUTES` กลับเป็น `uploaded` ตอนเปิดหน้าใหม่

ข้อจำกัดที่ยังมี:

- queue ยังไม่ persistent ข้าม process restart
- ระบบยังเป็น local single-node app

---

## 8. Project Structure

```text
smartvoice/
├── Home.py
├── pages/
│   ├── 1_📤_Admin.py
│   ├── 2_📊_Dashboard.py
│   ├── 3_👥_Customers.py
│   └── 4_Settings.py
├── smartvoice/
│   ├── auth.py
│   ├── cli.py
│   ├── config.py
│   ├── db.py
│   ├── env_settings.py
│   ├── file_manager.py
│   ├── logger.py
│   ├── ollama_client.py
│   ├── pipeline.py
│   ├── preflight.py
│   ├── prompts.py
│   ├── ui_helpers.py
│   └── stt/
├── scripts/
│   ├── extract_pdf.py
│   ├── generate_er_diagram.py
│   ├── make_password_hash.py
│   └── seed_mock_data.py
├── tests/
├── docs/
└── data/
```

---

## 9. Security Model ปัจจุบัน

| ด้าน | สถานะปัจจุบัน |
|------|---------------|
| SQL injection | ใช้ parameterized queries |
| Path traversal | sanitize filename ก่อน save |
| Upload abuse | จำกัด extension, magic bytes, ขนาด 100 MB |
| Secret handling | เก็บ secret ใน `.env` |
| Login | มี sidebar login; รองรับ PBKDF2 ผ่าน `SMARTVOICE_USERS` |
| Role check | หน้า Settings จำกัดเฉพาะ `Admin` / `Supervisor` |
| Audit trail | เก็บ `uploaded_by`, `uploaded_by_role` |

สิ่งที่ยังไม่ใช่ production-grade multi-user deployment:

- ยังไม่มี RBAC ครบทุกหน้า
- ยังไม่มี HTTPS reverse proxy / rate limiting
- ยังไม่มี persistent distributed queue
- SQLite ยังเหมาะกับ local app มากกว่า concurrent multi-user workload

---

## 10. Extension Points

- เปลี่ยน LLM ผ่าน `OLLAMA_MODEL`
- เปลี่ยน STT model/backend ผ่าน `WHISPER_MODEL` และ `WHISPER_BACKEND`
- เพิ่ม analysis call ใน `ollama_client.py` + `prompts.py`
- เพิ่ม schema ผ่าน `db.init_db()` + `_migrate()`
- ปรับ demo/real presets ใน `env_settings.py`
- ย้าย storage backend จาก SQLite ไป PostgreSQL เมื่อ workload โตขึ้น
