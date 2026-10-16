# SmartVoice — Architecture & Data Flow

---

## 1. ภาพรวมระบบ

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         SmartVoice (Local App)                      │
│                                                                     │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────────────┐ │
│  │ Streamlit UI │ ↔  │ Pipeline       │ ↔  │ SQLite DB           │ │
│  │ 13 pages     │    │ daemon threads │    │ 9 tables            │ │
│  └──────┬───────┘    └────────┬───────┘    └─────────────────────┘ │
│         │                     │                                     │
│         │     ┌───────────────┼────────────────┐                    │
│         │     ▼               ▼                ▼                    │
│         │ ┌────────────┐ ┌────────────┐ ┌──────────────┐           │
│         │ │ Whisper STT│ │ pyannote   │ │ Ollama LLM   │           │
│         │ │ HF / FW    │ │ diarization│ │ + insight_   │           │
│         │ └────────────┘ └────────────┘ │   rules      │           │
│         │                               └──────────────┘           │
│         └──→ Discord webhook (case claim/close) · PDF/CSV reports   │
└─────────────────────────────────────────────────────────────────────┘
```

| Component | หน้าที่ |
|-----------|---------|
| Streamlit UI | หน้าเข้าสู่ระบบ + 13 หน้า จัดเป็นหมวด Dashboard / งานลูกค้า / จัดการระบบ — เมนูสร้างตามสิทธิ์ของ role |
| Pipeline | Orchestrate STT, transcript cleanup, speaker correction, analysis, case assignment |
| `insight_rules.py` | ตรวจทุกคำตอบของ LLM ก่อนบันทึก — ยืนยันคำพูดอ้างอิง, คำนวณคะแนน/ธงเอง |
| SQLite | สาย, ลูกค้า, ทะเบียนรับประกัน, ใบสั่งขาย + รายการสินค้า, link, เคส, บัญชีพนักงาน (`users`), ประวัติการใช้งาน (`audit_log`) |
| Whisper | ถอดเสียงไทย |
| pyannote | diarization |
| Ollama LLM | cleanup, speaker correction, extraction, sentiment, QA, next action, anomaly, case matching |
| Discord | แจ้งเตือนเมื่อมีคนรับ/คืน/ปิด/เปิดเคสใหม่ (ถ้าตั้ง `DISCORD_WEBHOOK_URL`) |

---

## 2. UI Surface

| หมวด / หน้า | หน้าที่ | Role ที่เข้าได้ |
|------|---------|----------------|
| หน้าแรก (`Home.py`) | "งานที่รอคุณ" — เคสยังไม่มีคนรับ, เคสของฉัน, สายผิดปกติรุนแรง (นับด้วย SQL) + ลิงก์ไปหน้าที่กรองไว้; ตรวจความพร้อมระบบ (cache 5 นาที, Admin/Supervisor) | ทุก role |
| **Dashboard** — ภาพรวม, คีย์เวิร์ด แบรนด์ ช่องทาง, สายที่ผิดปกติ, ผลงานพนักงาน, รายการสาย | 5 หน้าใช้ตัวกรองร่วม (`dashboard_common.load_filtered_calls()`), ปุ่ม **ส่งออกรายงาน** (PDF / CSV สรุป / CSV รายการสาย) ทุกหน้า, ตารางคลิกเปิดรายละเอียด | ทุก role |
| **งานลูกค้า** — จัดการเคส | รับเคส / คืน / เปลี่ยนสถานะ / ปิด, สรุปเคส (`case_workflow.case_brief()`), SO ของลูกค้าในหน้าต่างเคส | ทุก role (QA รับเคสไม่ได้) |
| ลูกค้าและการรับประกัน | คลิกแถว → หน้าต่างลูกค้า: ทะเบียน + หลักฐานการซื้อ, SO, เคส, สาย (`customer_view`) | ทุก role |
| ใบสั่งขาย (SO) | ค้นหา/ดูทั้งใบ (`so_view`); นำเข้า Excel/CSV, เพิ่ม/แก้ไข, ผูกลูกค้า, ซ่อน/กู้คืน | ดู: ทุก role · แก้ไข: Admin |
| เพิ่ม/แก้ไขข้อมูลลูกค้า | เพิ่ม / แก้ไข / ซ่อน / กู้คืน ลูกค้าและทะเบียน, ยกเลิก/เปิดใช้ทะเบียน, แนบหลักฐานการซื้อ | Admin |
| **จัดการระบบ** — อัปโหลดและประมวลผลเสียง | Upload, process, ค้นหา/กรอง (สถานะ + Inbound/Outbound), load-limit picker, bulk delete (ยืนยันก่อน), link ลูกค้า, จัดการ/รวมเคส | Admin, Supervisor |
| ประวัติการใช้งาน | ดู `audit_log` — กรอง, ค้นหา, คลิกอ่านรายละเอียด, ดาวน์โหลด CSV | Admin, Supervisor |
| ตั้งค่าระบบ | preset สาธิต / ใช้งานจริง, แก้ `.env`, GPU auto-detect, auto-apply combo เมื่อเปลี่ยน Whisper model, post-save validation, Discord webhook + ปุ่มทดสอบ, readiness checks | Admin, Supervisor |
| จัดการผู้ใช้ | เพิ่มบัญชี, เปลี่ยน role, เปิด/ปิดใช้งาน — ไม่มีรีเซ็ตรหัสผ่านและไม่มีลบบัญชี | Admin |

`Home.py` เป็น router: ยังไม่ login จะเห็นแค่หน้าเข้าสู่ระบบ; login แล้ว `st.navigation(..., expanded=True)` สร้างเมนูจาก `auth.visible_pages(role)` แบ่งหมวดตาม `Home._SECTIONS` — หน้าที่ role เข้าไม่ได้จึงไม่อยู่ในเมนูเลย และทุกหน้ายังเรียก `init_page(PAGE_*)` ตรวจสิทธิ์ซ้ำฝั่ง server

หลักของ UI (มีเทสต์ตรวจใน `tests/test_usability.py` / `test_home_entrypoint.py`):

- ภาษาไทยบนหน้าจอ รหัสในฐานข้อมูล — แปลงผ่าน `labels.py`; เวลาแสดงเป็นเวลาไทยด้วย `labels.thai_time()`
- เมนูมีชื่อไทย + ไอคอน `:material/...:` ไม่ใช้ emoji ตกแต่ง
- ตารางที่มีข้อความยาวใช้ `selection_mode=TABLE_CLICK_MODES` (คลิกช่องไหนก็ได้ ไม่มีช่องติ๊ก) แล้วเปิด `@st.dialog`; `picked_row()` นับเป็นการคลิกเฉพาะเมื่อเลือกเพิ่ม
- การลบไฟล์เสียง/รวมเคสยืนยันก่อนเสมอ; ห้ามตัดข้อความไทยตามจำนวนตัวอักษร

หน้า `ตั้งค่าระบบ` ตั้งใจไม่ใช้ `st.form` เพราะ form widget ไม่ fire `on_change` ทำให้ feature auto-apply combo ใช้ไม่ได้

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
  → LLM analysis 5 requests (JSON mode, temperature 0)
  → insight_rules: verify quotes, recompute scores / flags / lists
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
| 4. Analysis | เรียก LLM 5 ครั้ง (sequential): สรุป/หัวข้อ, อารมณ์ลูกค้า, QA checklist, สิ่งที่ต้องทำต่อ, ความผิดปกติ |
| 5. Verify | `insight_rules.py` ตรวจและคำนวณผลใหม่ (ดูด้านล่าง) |
| 6. Save | บันทึก transcript + analysis ลง DB |
| 7. Case assignment | ใช้ recency short-circuit ก่อน fallback ไป LLM case match |

Transcript ยาวกว่า 14,000 ตัวอักษรถูกตัด**ช่วงกลาง** (เก็บต้นสายและท้ายสาย) และทุกคำขอใช้ `num_ctx` = `OLLAMA_NUM_CTX` (ค่าเริ่มต้น 12288)

**AI เสนอ ระบบตัดสิน** — ไม่เชื่อคะแนน ธง หรือรายการที่ LLM ส่งมาตรง ๆ:

| เรื่อง | กติกาใน `insight_rules.py` |
|---|---|
| คะแนนพนักงาน | ข้อ QA นับเมื่อคำพูดอ้างอิงเป็นของพนักงานจริง; ความสุภาพวัดจากสัดส่วนประโยคที่ลงท้ายค่ะ/ครับ; ข้อเห็นใจ/ขอโทษนับเฉพาะเมื่อลูกค้ามีปัญหา; คะแนนคำนวณใน Python |
| สิ่งที่ต้องทำต่อ | ประกอบจาก งาน \| รายละเอียด \| กำหนดเวลา \| การติดตาม; ตัดข้อความแม่แบบที่หลุดมา; ปฏิเสธงานคืนเงินในสายที่ไม่ได้คุยเรื่องเงิน |
| อารมณ์ลูกค้า | เชิงบวกต้องมีคำชมในคำพูดลูกค้า; ลูกค้าที่สบถ/บอกว่าไม่พอใจไม่มีทางเป็นเชิงบวก |
| ความผิดปกติ | คำพูดอ้างอิงต้องมีในสายและมีคำของหมวดนั้น; ระดับความรุนแรงมาจากหมวด; สแกนบรรทัดลูกค้าหาคำเรื่องสุขภาพ/คำหยาบเป็นด่านสำรอง |
| แบรนด์/ช่องทาง | นับเฉพาะชื่อที่พูดจริง (ชื่อบริษัทตอนทักทายไม่นับ) รวมเป็นชื่อสะกดเดียว |
| หัวข้อ | จำกัดไว้ 9 หัวข้อ; `topic_detail` 8 ค่า (รวม `กลิ่น/แพ้/ระคายเคือง`) กรอกเมื่อ `topic="แจ้งปัญหาสินค้า"` |

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

CDR filename รูปแบบ `YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav` มี metadata ที่ใช้ทั้งตอน upload และตอนแสดงผล:

```text
filename
  → extract_phone_from_filename()         → auto-link ลูกค้า/warranty ตอน upload (ไม่ link กับลูกค้าที่ถูกซ่อนไว้)
  → extract_direction_from_filename()     → กรอง Inbound/Outbound บนหน้าอัปโหลด (runtime, ไม่เก็บ DB)
  → extract_agent_code_from_filename()    → รหัสพนักงานบนหน้าผลงานพนักงาน / รายการสาย / รายงาน
  → extract_call_time_from_filename()     → "วันที่โทร" ที่แสดงทุกหน้า และใช้วัดระยะเวลาตอนจับคู่เคส
```

ถ้าพบลูกค้า ระบบจะเลือก warranty ล่าสุดของคนนั้นมาเชื่อมให้ด้วย

---

## 6. Cases — Auto Assignment และการรับเคส

ลำดับจริงใน `_auto_assign_case()`:

1. ถ้า call ยังไม่เชื่อมลูกค้า → skip
2. ถ้าไม่มี open/follow-up case → สร้างเคสใหม่ทันที
3. ถ้ามีเคสเปิด และสายล่าสุดในเคสนั้นอยู่ในหน้าต่าง `CASE_RECENCY_HOURS` (วัดจากเวลาโทรจริงในชื่อไฟล์) → attach ทันทีโดยไม่ถาม LLM
4. ถ้าไม่เข้าเงื่อนไข recency → ส่ง topic/summary ไปให้ LLM match กับเคสเปิดเดิม
5. ถ้า LLM ไม่ match → สร้างเคสใหม่

เมื่อ attach เข้ากับเคสเดิม ระบบจะเปลี่ยนสถานะเคสเป็น `follow_up`

**การรับเคส** (`case_workflow.py`, UI ผ่าน `ui_helpers.render_case_ownership()`):

```text
[รับเคสนี้]  db.claim_case()
               UPDATE cases SET assignee_* … WHERE id=? AND assignee_username IS NULL AND status != 'closed'
               → กดพร้อมกันสองคน มีคนเดียวที่ได้ (อีกคนเห็นว่าเคสมีเจ้าของแล้ว)
[เปลี่ยนสถานะ/ปิด]  db.set_case_status_as_assignee() — ตรวจเจ้าของใน WHERE ด้วย
[คืนเคส]  เจ้าของคืนเอง หรือ Admin/Supervisor ปลดให้ (แต่ "แย่ง" ไปเป็นของตัวเองไม่ได้)
ทุกครั้ง → audit.record(claim/release/update) + discord_notify (background thread, ไม่ raise, เบอร์โทรเหลือ 4 ตัวท้าย)
```

QA รับเคสไม่ได้ ส่วน `db.update_case_status()` สงวนไว้ให้ pipeline ตั้ง `follow_up` อัตโนมัติเท่านั้น

---

## 7. Concurrency & Recovery

- `launch_processing(call_id)` ใช้ 1 daemon thread ต่อสาย
- `launch_processing_queue(ids)` ใช้ daemon thread เดียวแล้วไล่ทีละสาย
- `_processing_lock` และ `_queue_lock` ป้องกันงานซ้ำ
- `@st.fragment(run_every=3)` ใช้ refresh สถานะบนหน้าอัปโหลด (query เฉพาะ `db.get_processing_calls()` 0-1 row ต่อ tick)
- ถ้าแอปถูกปิดกลางทาง ระบบจะ reset สายที่ค้างเกิน `PROCESSING_STALE_MINUTES` กลับเป็น `uploaded` ตอนเปิดหน้าใหม่

ข้อจำกัดที่ยังมี:

- queue ยังไม่ persistent ข้าม process restart
- ระบบยังเป็น local single-node app

## 7.1 Scale-friendly หน้าแรก / อัปโหลด / Dashboard

ทั้งสามส่วนไม่โหลด row ที่ไม่ได้แสดง เพื่อให้ใช้ได้กับ DB ขนาด 10K+ ไฟล์:

| หน้า | Default เริ่มต้น | ตัวเลือก | กลไกฝั่ง DB |
|------|------------------|----------|-------------|
| หน้าแรก | — | — | การ์ดใช้ SQL aggregate (`count_calls_by_status()`, `get_case_counts()`, `count_cases()`); readiness checks ครอบ `@st.cache_data(ttl=300)` — วัดที่ 5,000 สาย: 2,895 ms → 213 ms |
| อัปโหลดและประมวลผล | `ทั้งหมด ≤ 200, ไม่งั้น 200 ล่าสุด` | 100 / 200 / 500 / 1,000 / 5,000 / ทั้งหมด | `count_calls_by_status()` (SQL `GROUP BY`); `get_pending_call_ids()` lazy สำหรับ "Process All"; `get_processing_calls()` สำหรับ auto-refresh |
| Dashboard (5 หน้า) | `ทั้งหมด ≤ 1,000, ไม่งั้น 1,000 ล่าสุด` | 100 / 500 / 1,000 / 5,000 / ทั้งหมด | `get_done_calls(limit=N)`; ตัวกรองเก็บใน `_keep_*` session keys เพื่อให้ค่าตามไปทุกหน้า |
| จัดการเคส | กรอง/แบ่งหน้าใน SQL | — | อ่านเคสจาก SQL แล้วโหลดเฉพาะสายของเคสที่แสดง (`get_calls_for_cases()`, query เดียว) |
| ใบสั่งขาย | 200 ล่าสุด | 200 / 1,000 / ทั้งหมด | ค้นหาใน SQL รวมรายการสินค้า (`list_sales_orders()`, `count_sales_orders()`) |

## 7.2 Settings page reactive flow

หน้า `ตั้งค่าระบบ` ใช้ reactive widget แทน `st.form` เพื่อให้ on_change callback ของ Whisper model ทำงานทันที:

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

[User กด บันทึกการตั้งค่า]
  ├── write_env(updates) → atomic write ลง .env
  ├── audit() บันทึกเฉพาะค่าที่เปลี่ยน (HF_TOKEN / DISCORD_WEBHOOK_URL ถูก redact)
  ├── แสดง success
  └── รัน validate_whisper_combo() → render error/warning/info
```

## 7.3 Soft delete + Audit trail

**ข้อมูลลูกค้าไม่ถูกลบออกจากฐานข้อมูล** — ปุ่ม "ลบ" ลูกค้า / ทะเบียน / ใบสั่งขาย เรียก soft delete ซึ่งประทับเวลาแทนการลบแถว:

```text
[ลบลูกค้า]
  customer_entry.hide_customer(id, actor)
    └── db.soft_delete_customer()
          ├── customers.deleted_at / deleted_by ← now / actor
          ├── warranty_registrations ของลูกค้านี้ ← deleted_at + hidden_with_customer = 1
          └── calls / cases / call_customer_links / sales_orders ← ไม่แตะ (ประวัติยังอยู่ครบ)
    └── audit.record("delete", "customer", ...)

[กู้คืนลูกค้า]
  db.restore_customer()
    ├── customers.deleted_at ← NULL
    └── warranty ที่ hidden_with_customer = 1 ← กู้คืน
        (ทะเบียนที่ Admin ซ่อนแยกไว้เองยังซ่อนอยู่)
```

- ฟังก์ชันอ่านทุกตัวใน `db.py` มี `include_deleted=False` เป็นค่าเริ่มต้น ทุกหน้าจึงไม่เห็นแถวที่ซ่อนโดยอัตโนมัติ
- `phone` / `registration_no` / `so_number` เป็น UNIQUE — แถวที่ซ่อนยังจองค่าไว้ ตัวตรวจซ้ำจึงค้นแบบ `include_deleted=True` และบอกผู้ใช้ให้กู้คืนแทนการสร้างซ้ำ
- **ยกเลิกทะเบียน (Cancel)** ต่างจากการซ่อน: `warranty_registrations.status = 'cancelled'` ทะเบียนยังแสดงทุกหน้าพร้อมสถานะ
- บัญชีพนักงานก็ไม่ถูกลบ ใช้ปิดใช้งาน (`users.is_active = 0`) แทน

**Audit trail** — ทุก action ที่เปลี่ยนข้อมูลเรียก `audit.record()` (หน้าเว็บเรียกผ่าน `ui_helpers.audit()` ซึ่งเติมผู้ใช้จาก session ให้):

```text
หน้าเว็บ / customer_entry / sales_orders / case_workflow / login flow
   └── audit.record(action, entity, entity_id, entity_label, actor, actor_role, changes)
         ├── redact()  → ตัดค่า password / password_hash / hf_token / discord_webhook_url
         └── db.log_action() → INSERT INTO audit_log   (append-only, ไม่มี UPDATE/DELETE)
               └── ถ้าเขียนไม่สำเร็จ → log error แล้วไปต่อ (ไม่ raise)
```

| Source | บันทึก |
|---|---|
| login flow (`ui_helpers`) | เข้าสู่ระบบ, เข้าสู่ระบบไม่สำเร็จ, ออกจากระบบ, เปลี่ยนรหัสผ่านตัวเอง |
| `customer_entry` | ลูกค้า/ทะเบียน: เพิ่ม, แก้ไข (`{field: [ก่อน, หลัง]}`), ซ่อน, กู้คืน, ยกเลิก/เปิดใช้ทะเบียน |
| `sales_orders` | นำเข้าไฟล์ (1 รายการต่อไฟล์), เพิ่ม, แก้ไข, ผูกลูกค้า, ซ่อน, กู้คืน SO |
| `case_workflow` | รับเคส, คืนเคส, เปลี่ยนสถานะ/ปิดเคส |
| `dashboard_common` | ส่งออกรายงาน PDF / CSV (รูปแบบ, จำนวนสาย, ตัวกรอง) |
| จัดการผู้ใช้ | สร้างบัญชี, เปลี่ยน role, เปิด/ปิดใช้งาน |
| อัปโหลดและประมวลผล | อัปโหลด/ลบสาย, เชื่อมลูกค้าแบบ manual, หัวข้อ/รวมเคส |
| ตั้งค่าระบบ | บันทึกค่า `.env`, ปุ่ม preset |

## 7.4 ใบสั่งขาย (SO)

```text
Excel/CSV  → sales_orders.read_upload()    (หาแถวหัวตารางเอง, CSV cp874 ได้)
           → parse_import()                (1 แถว = 1 รายการสินค้า → รวมตามเลขที่ SO;
                                            จับคอลัมน์จากชื่อ: แม่แบบไทย หรือชื่อ NAV อังกฤษ;
                                            วันที่ พ.ศ./ค.ศ., ตัวเลขมีคอมมา, เบอร์ที่ Excel ตัด 0;
                                            ปัญหารายงานเป็นรายแถว → ปุ่มนำเข้ากดไม่ได้)
           → complete_totals()             (เติมเฉพาะยอดที่ว่าง; ค่าในไฟล์ชนะเสมอ)
           → import_orders()               (upsert ตาม so_number, แทนที่รายการสินค้าทั้งชุด,
                                            ผูกลูกค้าจากเบอร์ผู้รับ → ผู้ซื้อ, audit 1 รายการ)
```

SO ที่ผูกลูกค้าแสดงในหน้าลูกค้าและหน้าต่างเคส (`so_view.render_customer_orders()`) และทะเบียนรับประกันที่มี `so_number` ตรงกันแสดงในหน้าต่าง SO

## 7.5 รายงาน Dashboard (PDF / CSV)

`dashboard_report.py` (ไม่ import Streamlit) คำนวณจากชุดสายเดียวกับที่หน้าจอแสดง — สูตรคะแนนพนักงานอยู่ที่นี่และหน้าผลงานพนักงาน import ไปใช้ จึงไม่มีทางได้ตัวเลขต่างกัน

- **PDF** วาดด้วย `fpdf2` — กราฟแท่งเป็นสี่เหลี่ยมใน PDF (ไม่ต้องใช้ browser/kaleido) และจัดรูปตัวอักษรไทยด้วย HarfBuzz (`uharfbuzz`) ให้สระ/วรรณยุกต์ซ้อนถูกตำแหน่ง; ตัดบรรทัดเองด้วย `wrap_text()` ที่ไม่แยกพยัญชนะออกจากสระ/วรรณยุกต์ (โหมดตัดตามตัวอักษรของ fpdf2 ค้างเมื่อเจอข้อความไทยยาวไม่มีช่องว่าง); ฟอนต์จาก `REPORT_FONT_PATH` หรือ Tahoma/Leelawadee/Noto Sans Thai/TLWG ที่พบในเครื่อง
- **CSV** เป็น UTF-8 มี BOM (Excel บน Windows อ่านภาษาไทยได้) และเติม `'` หน้าข้อความที่ขึ้นต้นด้วย `= + @` กัน Excel ตีความเป็นสูตร
- ไฟล์สร้างตอนกดปุ่มเท่านั้น (deferred `st.download_button(data=callable)`) หน้า Dashboard จึงไม่ช้าลง และการดาวน์โหลดทุกครั้งถูกบันทึกใน audit log

---

## 8. Project Structure

```text
smartvoice/
├── Home.py
├── pages/
│   ├── 1_📤_Admin.py              # อัปโหลดและประมวลผลเสียง
│   ├── 2_📊_Dashboard.py          # Dashboard — ภาพรวม
│   ├── 3_👥_Customers.py          # ลูกค้าและการรับประกัน
│   ├── 4_Settings.py
│   ├── 5_👤_Users.py
│   ├── 6_➕_Data_Entry.py
│   ├── 7_📜_Audit_Log.py
│   ├── 8_Dashboard_Insights.py
│   ├── 9_Dashboard_Anomaly.py
│   ├── 10_Agent_Performance.py
│   ├── 11_Cases.py
│   ├── 12_Call_Summaries.py
│   └── 13_Sales_Orders.py
├── smartvoice/
│   ├── audit.py · auth.py · cli.py · config.py · logger.py · preflight.py
│   ├── case_workflow.py · discord_notify.py
│   ├── customer_entry.py · customer_view.py
│   ├── dashboard_common.py · dashboard_report.py
│   ├── db.py · env_settings.py · file_manager.py · labels.py
│   ├── insight_rules.py · ollama_client.py · pipeline.py · prompts.py
│   ├── sales_orders.py · so_view.py
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
└── data/                            # raw_audio, warranty_proofs, models, logs, smartvoice.db
```

---

## 9. Security Model ปัจจุบัน

| ด้าน | สถานะปัจจุบัน |
|------|---------------|
| SQL injection | ใช้ parameterized queries |
| Path traversal | sanitize filename ก่อน save; หลักฐานการซื้อตั้งชื่อด้วย SHA-256 ไม่ใช้ชื่อที่ผู้ใช้ส่งมา |
| Upload abuse | เสียง: จำกัด extension, magic bytes, ขนาด 100 MB · หลักฐานการซื้อ: ตรวจชนิดจากเนื้อไฟล์ (JPG/PNG/WEBP/PDF), ≤ 10 MB · Excel/CSV: อ่านเป็นข้อมูลเท่านั้น |
| Secret handling | เก็บ secret ใน `.env`; `HF_TOKEN` และ `DISCORD_WEBHOOK_URL` ไม่ถูกเขียนลง audit log |
| Login | บังคับ login ทุกหน้า; บัญชี PBKDF2-SHA256 (260,000 รอบ) ในตาราง `users` + fallback `SMARTVOICE_USERS`; ใส่รหัสผิด 5 ครั้งล็อก 60 วินาที; บัญชี `admin` เริ่มต้นถูกเตือนจนกว่าจะเปลี่ยนรหัส |
| Role check (RBAC) | ครบทุกหน้า — เมนูสร้างจาก `auth.visible_pages(role)` และทุกหน้าเรียก `init_page(PAGE_*)` ตรวจซ้ำฝั่ง server; ปุ่มแก้ไข SO ตรวจ `can_access(role, PAGE_DATA_ENTRY)`; role ที่ไม่รู้จักถูกลดเป็น `Agent` |
| เคส | รับเคส/เปลี่ยนสถานะตรวจเจ้าของใน `WHERE` ของ SQL — แย่งเคสไม่ได้แม้กดพร้อมกัน |
| นโยบายบัญชี | Admin ตั้ง/รีเซ็ตรหัสผ่านของคนอื่นไม่ได้; ไม่มีการลบบัญชี มีแค่ปิดใช้งาน; ต้องเหลือ Admin ที่ใช้งานได้ ≥ 1 เสมอ |
| Data retention | ลูกค้า/ทะเบียน/SO เป็น soft delete — แถวไม่ถูกลบจริง |
| Audit trail | ตาราง `audit_log` แบบ append-only ครอบคลุม login, บัญชี, ลูกค้า/ทะเบียน/SO, สาย, เคส, การตั้งค่า, การส่งออกรายงาน; ไม่บันทึกค่ารหัสผ่าน/token |
| Discord | ส่งเลขเคส หัวข้อ ชื่อลูกค้า เบอร์ลูกค้าเฉพาะ 4 ตัวท้าย และชื่อผู้ทำรายการ; ปิด `allowed_mentions` (ข้อความ @ ใครไม่ได้) |

สิ่งที่ยังไม่ใช่ production-grade multi-user deployment:

- session ผูกกับ Streamlit session — refresh หน้า (F5) = ออกจากระบบ (ยังไม่มี cookie/JWT)
- Admin ยังเป็นคนตั้งรหัสผ่านตั้งต้นตอนสร้างบัญชี (ยังไม่มีการบังคับเปลี่ยนรหัสตอนล็อกอินครั้งแรก)
- การลบ "สาย" ในหน้าอัปโหลดยังลบไฟล์และแถวจริง (ยืนยันก่อน และมีบันทึกใน audit log ว่าใครลบ)
- ไฟล์รายงาน PDF/CSV ที่ดาวน์โหลดไปแล้วอยู่นอกการควบคุมของระบบ (มีแค่บันทึกว่าใครดาวน์โหลด)
- ยังไม่มี HTTPS reverse proxy / rate limiting
- ยังไม่มี persistent distributed queue
- SQLite ยังเหมาะกับ local app มากกว่า concurrent multi-user workload

---

## 10. Extension Points

- เปลี่ยน LLM ผ่าน `OLLAMA_MODEL` (ต้อง re-validate prompt ด้วยการรันวิเคราะห์ซ้ำบน transcript ที่เก็บไว้)
- เปลี่ยน STT model/backend ผ่าน `WHISPER_MODEL` และ `WHISPER_BACKEND`
- เพิ่ม analysis call ใน `ollama_client.py` + `prompts.py` แล้วเพิ่มกติกาตรวจใน `insight_rules.py`
- เพิ่ม schema ผ่าน `db.init_db()` + `_migrate()` (เพิ่มคอลัมน์อย่างเดียว และอัปเดต `docs/database_design.md` ทุกครั้ง)
- เพิ่มหน้าใหม่: `PAGE_*` + `PAGE_ORDER`/`PAGE_LABELS_TH` + `ROLE_PERMISSIONS` ใน `auth.py`, route + ไอคอน `:material/...:` ใน `Home._PAGE_SPECS`, หมวดใน `Home._SECTIONS`, และ `init_page()` ในไฟล์หน้า
- เพิ่ม action ที่เปลี่ยนข้อมูล: เรียก `audit()` ข้าง ๆ เสมอ; เพิ่มประเภทข้อมูลใหม่ใน audit log ที่ `audit.ENTITY_*` + `ENTITY_LABELS_TH`
- เพิ่มคอลัมน์ที่นำเข้า SO ได้: เพิ่ม `Field(...)` ใน `sales_orders.FIELDS` (ชื่อไทย + ชื่อสำรอง) และคอลัมน์ใน `db.SO_HEADER_COLUMNS` / `SO_LINE_COLUMNS`
- เพิ่มส่วนในรายงาน: เพิ่มข้อมูลใน `dashboard_report.Report` แล้ววาดใน `pdf_report()` / เพิ่มแถวใน `summary_rows()`
- ปรับ demo/real presets ใน `env_settings.py`
- ย้าย storage backend จาก SQLite ไป PostgreSQL เมื่อ workload โตขึ้น
