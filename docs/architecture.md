# SmartVoice — Architecture & Data Flow

---

## 1. ภาพรวมระบบ

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         SmartVoice (Local App)                      │
│                                                                     │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────────────┐ │
│  │ Streamlit UI │ ↔  │ Pipeline       │ ↔  │ SQLite DB           │ │
│  │ 8 pages      │    │ daemon threads │    │ 7 tables            │ │
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
| Streamlit UI | หน้าเข้าสู่ระบบ + หน้าแรก, Admin, Dashboard, Customers, เพิ่มข้อมูล, ประวัติการใช้งาน, Settings, จัดการผู้ใช้ — เมนูสร้างตามสิทธิ์ของ role |
| Pipeline | Orchestrate STT, transcript cleanup, speaker correction, analysis, case assignment |
| SQLite | เก็บสาย, ลูกค้า, warranty, link, case, บัญชีพนักงาน (`users`), ประวัติการใช้งาน (`audit_log`) |
| Whisper | ถอดเสียงไทย |
| pyannote | diarization |
| Ollama LLM | cleanup, speaker correction, extraction, sentiment, QA, anomaly, case matching |

---

## 2. UI Surface

| หน้า | หน้าที่ | Role ที่เข้าได้ |
|------|---------|----------------|
| หน้าแรก (`Home.py`) | การ์ดจำนวนสาย (นับด้วย SQL) + `Deployment readiness` (cache 5 นาที) | ทุก role |
| Admin | Upload, process, ค้นหา/กรอง (สถานะ + ทิศทางสาย Inbound/Outbound), load-limit picker สำหรับ scale, bulk delete, link ลูกค้า, จัดการ/รวมเคส | Admin, Supervisor |
| Dashboard | Charts (รวม drill-down ประเภทความเสียหายภายใน "แจ้งปัญหาสินค้า"), anomaly, agent performance พร้อม QA evidence + filter ตามรหัส Agent, case summary, call summaries, load-limit picker | ทุก role |
| Customers | ดูลูกค้า, warranty, เคส (summary แสดงเต็ม), สายที่เชื่อมไว้ | ทุก role |
| เพิ่มข้อมูล | เพิ่ม / แก้ไข / ซ่อน / กู้คืน ลูกค้าและทะเบียนรับประกัน | Admin |
| ประวัติการใช้งาน | ดู `audit_log` — กรอง, ค้นหา, ดาวน์โหลด CSV | Admin, Supervisor |
| Settings | preset Demo / Real AI, แก้ `.env`, GPU auto-detect + ซ่อน `cuda` ถ้าไม่พบ, auto-apply combo เมื่อเปลี่ยน Whisper model, post-save validation, readiness checks | Admin, Supervisor |
| จัดการผู้ใช้ | เพิ่มบัญชี, เปลี่ยน role, เปิด/ปิดใช้งาน — ไม่มีรีเซ็ตรหัสผ่านและไม่มีลบบัญชี | Admin |

`Home.py` เป็น router: ยังไม่ login จะเห็นแค่หน้าเข้าสู่ระบบ; login แล้ว `st.navigation()` สร้างเมนูจาก `auth.visible_pages(role)` — หน้าที่ role เข้าไม่ได้จึงไม่อยู่ในเมนูเลย และทุกหน้ายังเรียก `init_page(PAGE_*)` ตรวจสิทธิ์ซ้ำฝั่ง server

หน้า `Settings` ตั้งใจไม่ใช้ `st.form` เพราะ form widget ไม่ fire `on_change` ทำให้ feature auto-apply combo ใช้ไม่ได้

ป้ายทุกตัวใน UI เป็นคำที่สื่อความหมาย ไม่ใช้ emoji/ไอคอนตกแต่ง (มีเทสต์ตรวจ)

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

Extraction call (`extract_summary_and_topics()`) ยังเก็บ `topic_detail` เพิ่ม — controlled vocabulary 7 ค่าสำหรับประเภทความเสียหาย (กรอกเมื่อ `topic="แจ้งปัญหาสินค้า"`) ผ่าน `normalize_topic_detail()` clamp ให้อยู่ใน enum ก่อนเขียน DB

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

## 5. Auto-Linking ตอน Upload + Filename-derived filters

CDR filename รูปแบบ `YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav` มี metadata ที่ใช้ทั้งตอน upload และตอนกรองภายหลัง:

```text
filename
  → extract_phone_from_filename()         → auto-link ลูกค้า/warranty ตอน upload (ไม่ link กับลูกค้าที่ถูกซ่อนไว้)
  → extract_direction_from_filename()     → ใช้ตอนกรอง Inbound/Outbound บน Admin (runtime, ไม่เก็บ DB)
  → extract_agent_code_from_filename()    → ใช้ตอนกรองตามรหัส Agent บน Dashboard (runtime, ไม่เก็บ DB)
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
- `@st.fragment(run_every=3)` ใช้ refresh สถานะบนหน้า Admin (query เฉพาะ `db.get_processing_calls()` 0-1 row ต่อ tick เพื่อให้เบาที่ 10K+ uploads)
- ถ้าแอปถูกปิดกลางทาง ระบบจะ reset สายที่ค้างเกิน `PROCESSING_STALE_MINUTES` กลับเป็น `uploaded` ตอนเปิดหน้าใหม่

ข้อจำกัดที่ยังมี:

- queue ยังไม่ persistent ข้าม process restart
- ระบบยังเป็น local single-node app

## 7.1 Scale-friendly หน้าแรก / Admin / Dashboard

ทั้งสามหน้าไม่โหลด row ที่ไม่ได้แสดง เพื่อให้ใช้ได้กับ DB ขนาด 10K+ ไฟล์:

| หน้า | Default เริ่มต้น | ตัวเลือก | กลไกฝั่ง DB |
|------|------------------|----------|-------------|
| หน้าแรก | — | — | การ์ด 4 ใบใช้ `count_calls_by_status()`; readiness checks ครอบ `@st.cache_data(ttl=300)` เพราะเนื้อใน expander รันทุก rerun แม้พับอยู่และ checks ยิง network ~2.6 วินาที — วัดที่ 5,000 สาย: 2,895 ms → 213 ms |
| Admin | `ทั้งหมด ≤ 200, ไม่งั้น 200 ล่าสุด` | 100 / 200 / 500 / 1,000 / 5,000 / ทั้งหมด | `count_calls_by_status()` (SQL `GROUP BY`) สำหรับ metric cards; `get_pending_call_ids()` lazy สำหรับ "Process All"; `get_processing_calls()` สำหรับ auto-refresh fragment |
| Dashboard | `ทั้งหมด ≤ 1,000, ไม่งั้น 1,000 ล่าสุด` | 100 / 500 / 1,000 / 5,000 / ทั้งหมด | `get_done_calls(limit=N)` |

## 7.2 Settings page reactive flow

หน้า `Settings` ใช้ reactive widget แทน `st.form` เพื่อให้ on_change callback ของ Whisper model ทำงานทันที:

```
[Page load]
  ├── ตรวจ GPU ด้วย gpu_available()
  ├── สร้าง _DEVICE_OPTIONS = ["auto", "cpu"] + (["cuda"] ถ้ามี GPU)
  ├── Seed session_state จาก .env (เฉพาะครั้งแรก)
  └── Render widgets ทุกตัวด้วย key= + session_state binding

[User เปลี่ยน Whisper model]
  ├── on_change → _apply_model_recommendations()
  │     ├── ดึง combo จาก recommended_combo_for_model(model, has_gpu)
  │     ├── ถ้า device ไม่ใน _DEVICE_OPTIONS → fall back เป็น "auto"
  │     └── เขียน session_state สำหรับ Backend / Device / Compute
  └── Streamlit rerun → widget ทั้ง 3 re-render ตามค่าใหม่

[User กด Save Settings]
  ├── อ่านค่าจาก local variables (ที่ผูกกับ session_state ผ่าน key=)
  ├── write_env(updates) → atomic write ลง .env
  ├── audit() บันทึกเฉพาะค่าที่เปลี่ยน (HF_TOKEN ถูก redact)
  ├── แสดง success
  └── รัน validate_whisper_combo() → render error/warning/info
```

## 7.3 Soft delete + Audit trail

**ข้อมูลลูกค้าไม่ถูกลบออกจากฐานข้อมูล** — ปุ่ม "ลบ" บนหน้าเพิ่มข้อมูลเรียก soft delete ซึ่งประทับเวลาแทนการลบแถว:

```text
[ลบลูกค้า]
  customer_entry.hide_customer(id, actor)
    └── db.soft_delete_customer()
          ├── customers.deleted_at / deleted_by ← now / actor
          ├── warranty_registrations ของลูกค้านี้ ← deleted_at + hidden_with_customer = 1
          └── calls / cases / call_customer_links ← ไม่แตะ (ประวัติสายยังอยู่ครบ)
    └── audit.record("delete", "customer", ...)

[กู้คืนลูกค้า]
  db.restore_customer()
    ├── customers.deleted_at ← NULL
    └── warranty ที่ hidden_with_customer = 1 ← กู้คืน
        (ทะเบียนที่ Admin ซ่อนแยกไว้เองยังซ่อนอยู่)
```

- ฟังก์ชันอ่านทุกตัวใน `db.py` มี `include_deleted=False` เป็นค่าเริ่มต้น ทุกหน้าจึงไม่เห็นแถวที่ซ่อนโดยอัตโนมัติ
- `phone` / `registration_no` เป็น UNIQUE — แถวที่ซ่อนยังจองค่าไว้ ตัวตรวจซ้ำจึงค้นแบบ `include_deleted=True` และบอกผู้ใช้ให้กู้คืนแทนการสร้างซ้ำ
- บัญชีพนักงานก็ไม่ถูกลบ ใช้ปิดใช้งาน (`users.is_active = 0`) แทน

**Audit trail** — ทุก action ที่เปลี่ยนข้อมูลเรียก `audit.record()` (หน้าเว็บเรียกผ่าน `ui_helpers.audit()` ซึ่งเติมผู้ใช้จาก session ให้):

```text
หน้าเว็บ / customer_entry / login flow
   └── audit.record(action, entity, entity_id, entity_label, actor, actor_role, changes)
         ├── redact()  → ตัดค่า password / password_hash / hf_token
         └── db.log_action() → INSERT INTO audit_log   (append-only, ไม่มี UPDATE/DELETE)
               └── ถ้าเขียนไม่สำเร็จ → log error แล้วไปต่อ (ไม่ raise)
```

| Source | บันทึก |
|---|---|
| login flow (`ui_helpers`) | เข้าสู่ระบบ, เข้าสู่ระบบไม่สำเร็จ, ออกจากระบบ, เปลี่ยนรหัสผ่านตัวเอง |
| `customer_entry` | ลูกค้า/ทะเบียน: เพิ่ม, แก้ไข (`{field: [ก่อน, หลัง]}`), ซ่อน, กู้คืน |
| จัดการผู้ใช้ | สร้างบัญชี, เปลี่ยน role, เปิด/ปิดใช้งาน |
| Admin | อัปโหลด/ลบสาย, เชื่อมลูกค้าแบบ manual, เปลี่ยนสถานะ/หัวข้อ/รวมเคส |
| Settings | บันทึกค่า `.env`, ปุ่ม preset |

---

## 8. Project Structure

```text
smartvoice/
├── Home.py
├── pages/
│   ├── 1_📤_Admin.py
│   ├── 2_📊_Dashboard.py
│   ├── 3_👥_Customers.py
│   ├── 4_Settings.py
│   ├── 5_👤_Users.py
│   ├── 6_➕_Data_Entry.py
│   └── 7_📜_Audit_Log.py
├── smartvoice/
│   ├── audit.py
│   ├── auth.py
│   ├── cli.py
│   ├── config.py
│   ├── customer_entry.py
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
│   ├── backfill_topic_detail.py    # Re-classify topic_detail for legacy product-issue calls
│   ├── extract_pdf.py
│   ├── generate_er_diagram.py
│   ├── make_password_hash.py
│   ├── scrub_existing_next_actions.py
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
| Login | บังคับ login ทุกหน้า; บัญชี PBKDF2-SHA256 (260,000 รอบ) ในตาราง `users` + fallback `SMARTVOICE_USERS`; ใส่รหัสผิด 5 ครั้งล็อก 60 วินาที; บัญชี `admin` เริ่มต้นถูกเตือนจนกว่าจะเปลี่ยนรหัส |
| Role check (RBAC) | ครบทุกหน้า — เมนูสร้างจาก `auth.visible_pages(role)` และทุกหน้าเรียก `init_page(PAGE_*)` ตรวจซ้ำฝั่ง server; role ที่ไม่รู้จักถูกลดเป็น `Agent` |
| นโยบายบัญชี | Admin ตั้ง/รีเซ็ตรหัสผ่านของคนอื่นไม่ได้ (เจ้าของบัญชีเปลี่ยนเองโดยต้องกรอกรหัสเดิม); ไม่มีการลบบัญชี มีแค่ปิดใช้งาน; ต้องเหลือ Admin ที่ใช้งานได้ ≥ 1 เสมอ |
| Data retention | ลูกค้า/ทะเบียนเป็น soft delete — แถวไม่ถูกลบจริง |
| Audit trail | ตาราง `audit_log` แบบ append-only ครอบคลุม login, บัญชี, ลูกค้า/ทะเบียน, สาย, เคส, การตั้งค่า; ไม่บันทึกค่ารหัสผ่าน/token |

สิ่งที่ยังไม่ใช่ production-grade multi-user deployment:

- session ผูกกับ Streamlit session — refresh หน้า (F5) = ออกจากระบบ (ยังไม่มี cookie/JWT)
- Admin ยังเป็นคนตั้งรหัสผ่านตั้งต้นตอนสร้างบัญชี (ยังไม่มีการบังคับเปลี่ยนรหัสตอนล็อกอินครั้งแรก)
- การลบ "สาย" ในหน้า Admin ยังลบไฟล์และแถวจริง (มีบันทึกใน audit log ว่าใครลบ)
- ยังไม่มี HTTPS reverse proxy / rate limiting
- ยังไม่มี persistent distributed queue
- SQLite ยังเหมาะกับ local app มากกว่า concurrent multi-user workload

---

## 10. Extension Points

- เปลี่ยน LLM ผ่าน `OLLAMA_MODEL`
- เปลี่ยน STT model/backend ผ่าน `WHISPER_MODEL` และ `WHISPER_BACKEND`
- เพิ่ม analysis call ใน `ollama_client.py` + `prompts.py`
- เพิ่ม schema ผ่าน `db.init_db()` + `_migrate()` (อัปเดต `docs/database_design.md` ทุกครั้ง)
- เพิ่มหน้าใหม่: `PAGE_*` + `PAGE_ORDER`/`PAGE_LABELS_TH` + `ROLE_PERMISSIONS` ใน `auth.py`, route ใน `Home.py`, และ `init_page()` ในไฟล์หน้า
- เพิ่ม action ที่เปลี่ยนข้อมูล: เรียก `audit()` ข้าง ๆ เสมอ; เพิ่มประเภทข้อมูลใหม่ใน audit log ที่ `audit.ENTITY_*` + `ENTITY_LABELS_TH`
- ปรับ demo/real presets ใน `env_settings.py`
- ย้าย storage backend จาก SQLite ไป PostgreSQL เมื่อ workload โตขึ้น
