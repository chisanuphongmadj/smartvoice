# Changelog

All notable changes to SmartVoice are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.4.0] — 2026-09-17 — หน้าเพิ่มข้อมูล, soft delete, audit log และนโยบายบัญชี

### Added — หน้าเพิ่มข้อมูล (Admin เท่านั้น)
- หน้าใหม่ `pages/6_➕_Data_Entry.py` 3 แท็บ: **ลูกค้า** / **ทะเบียนรับประกัน** (แต่ละแท็บมี เพิ่มใหม่ + แก้ไข/ลบ พร้อมช่องค้นหา + ตาราง 10 รายการล่าสุด) และ **รายการที่ซ่อนไว้** (กู้คืน)
- `smartvoice/customer_entry.py` — กติกาทั้งหมดแยกจาก Streamlit จึงเทสต์ได้: normalize เบอร์ (ตัดขีด/วงเล็บ/เว้นวรรค/เลขไทย), กันเบอร์และเลขทะเบียนซ้ำ (ตอนแก้ไขไม่นับตัวเอง), คำนวณวันหมดประกันจากวันที่ซื้อ + จำนวนเดือน (clamp วันสิ้นเดือน), ช่องว่างบันทึกเป็น NULL
- `db.update_customer()` / `db.update_warranty()` — แก้เฉพาะคอลัมน์ใน whitelist (`id` / `created_at` แก้ไม่ได้) และย้ายทะเบียนไปลูกค้าคนอื่นได้
- ข้อความยืนยันเก็บใน session_state จึงไม่ถูก `st.rerun()` ล้างก่อนผู้ใช้อ่าน

### Added — Audit log ทั้งระบบ
- ตารางใหม่ `audit_log` แบบ **append-only** — ไม่มีโค้ดส่วนใด UPDATE หรือ DELETE แถว
- โมดูลใหม่ `smartvoice/audit.py` — คำศัพท์กลาง (action/entity + ป้ายภาษาไทย), `record()` ที่ไม่ raise (log ล้มไม่ทำให้งานผู้ใช้หาย), `redact()` ตัดค่ารหัสผ่าน/token, `diff_fields()` เก็บ `{field: [ก่อน, หลัง]}` เฉพาะค่าที่เปลี่ยนจริง; `ui_helpers.audit()` เติมผู้ใช้จาก session ให้
- บันทึก: เข้าสู่ระบบ / เข้าสู่ระบบไม่สำเร็จ / ออกจากระบบ, เปลี่ยนรหัสผ่านตัวเอง, สร้างบัญชี / เปลี่ยนบทบาท / เปิด-ปิดบัญชี, ลูกค้าและทะเบียน (เพิ่ม/แก้ไข/ซ่อน/กู้คืน), อัปโหลดและลบสาย, เชื่อมลูกค้าแบบ manual, เปลี่ยนสถานะ/หัวข้อ/รวมเคส, บันทึกค่า Settings และปุ่ม preset
- หน้าใหม่ `pages/7_📜_Audit_Log.py` (Admin + Supervisor) — กรองตามประเภท / การกระทำ / ผู้ใช้, ค้นหา, ดาวน์โหลด CSV (UTF-8 BOM เปิดใน Excel ภาษาไทยไม่เพี้ยน)

### Changed — ไม่ลบข้อมูลจริง (soft delete)
- **ลูกค้าและทะเบียนรับประกันไม่ถูกลบออกจากฐานข้อมูลอีกต่อไป** — "ลบ" คือประทับ `deleted_at` / `deleted_by` แถวยังอยู่ครบและกู้คืนได้
- `soft_delete_customer()` ซ่อนลูกค้าพร้อมทะเบียนของเขา (ติดธง `hidden_with_customer = 1`) โดย**ไม่แตะ**สาย เคส และการเชื่อมสาย; `restore_customer()` กู้คืนเฉพาะทะเบียนที่มีธงนั้น — ทะเบียนที่ Admin ซ่อนแยกไว้ยังคงซ่อน (ไม่ใช้ `deleted_at` ที่ตรงกันเป็นตัวจับคู่ เพราะซ่อนสองครั้งในวินาทีเดียวกันจะชนกัน — เทสต์จับได้ระหว่างพัฒนา)
- กู้คืนทะเบียนไม่ได้ถ้าลูกค้าเจ้าของยังถูกซ่อน
- ทุกฟังก์ชันอ่านมี `include_deleted=False` เป็นค่าเริ่มต้น; `phone` / `registration_no` เป็น UNIQUE แถวที่ซ่อนจึงยังจองค่าไว้ — ระบบบอกให้ "กู้คืน" แทนที่จะ error ตอน insert
- auto-link จากเบอร์ในชื่อไฟล์จะไม่ link กับลูกค้าที่ถูกซ่อน

### Changed — นโยบายบัญชีผู้ใช้
- **ผู้ดูแลระบบตั้งหรือรีเซ็ตรหัสผ่านของพนักงานไม่ได้** — ลบฟอร์มรีเซ็ตและ `auth.reset_password()` ทิ้ง รหัสผ่านตั้งได้ผ่าน `auth.change_password()` ซึ่งบังคับกรอกรหัสเดิมเท่านั้น
- **ไม่มีปุ่มลบบัญชีถาวร** — `audit_log` อ้างถึงบัญชีเหล่านั้น ใช้ปิดใช้งาน (ย้อนกลับได้) แทน
- ย้าย **เปลี่ยนรหัสผ่าน** จากหน้าแรกไปไว้ในกล่องบัญชีบน sidebar — ใช้ได้จากทุกหน้า

### Changed — ป้ายใน UI เป็นคำ ไม่ใช่ไอคอน
- เอา emoji ออกจากทุกป้ายที่ผู้ใช้เห็น: หัวข้อหน้า, ปุ่ม, แท็บ, expander, ตัวกรอง, การ์ด KPI, เมนู sidebar และไอคอนแท็บเบราว์เซอร์
- ไอคอนที่เคยแทนความหมายเปลี่ยนเป็นคำ: ความรุนแรง → รุนแรง / ปานกลาง / เล็กน้อย, sentiment → Positive / Neutral / Negative, anomaly → พบ / ปกติ, สถานะเคส → เปิด / ติดตาม / ปิด, การจับคู่ → จับคู่อัตโนมัติ / จับคู่เอง, สถานะบัญชี → ใช้งาน / ปิดใช้งาน
- สถานะสายใช้ชุดคำเดียวกันทุกหน้า (การ์ด KPI, ตัวกรอง, หัวข้อแถว, หน้าแรก, หน้า Customers): รอประมวลผล / กำลังประมวลผล / เสร็จแล้ว / ผิดพลาด
- หัวข้อแถวในหน้า Admin: `ไฟล์: … — สถานะ: เสร็จแล้ว • เบอร์: … • วันที่: … • ผู้อัปโหลด: …`
- เก็บลูกศร `→` และ `↳` ไว้ เพราะสื่อความหมาย ไม่ใช่ของประดับ

### Fixed
- **หน้าแรกช้า** — เคยดึงสายทั้งตาราง (`get_all_calls()` = `SELECT *` พร้อม transcript) เพื่อนับตัวเลข 4 ใบ และรัน readiness checks (network ~2.6 วินาที) ทุก rerun แม้ expander พับอยู่ → ใช้ `count_calls_by_status()` + `@st.cache_data(ttl=300)` พร้อมปุ่ม "ตรวจสอบใหม่" — **ที่ 5,000 สาย: 2,895 ms → 213 ms, หน่วยความจำ ~57 MB → 0.4 MB**
- **สรุปบทสนทนาถูกตัดกลางคำ** ในหน้า Customers — โค้ดตัดที่ 100 ตัวอักษร ภาษาไทยไม่มีเว้นวรรคจึงตัดกลางคำเสมอ และโดนทุกสาย (summary จริงยาว 130–328 ตัวอักษร) → แสดงเต็มในบรรทัดของตัวเอง
- **หน้าจัดการผู้ใช้บันทึกทับข้อมูลผิดบัญชี** — ช่องแก้ไขใช้ widget key คงที่ Streamlit จึงจำค่าของบัญชีก่อนหน้าไว้หลังสลับบัญชี → key ผูกกับ id ของบัญชี (audit log เป็นตัวที่ทำให้เห็นบั๊กนี้)

### Database
- `customers`: เพิ่ม `deleted_at`, `deleted_by`
- `warranty_registrations`: เพิ่ม `deleted_at`, `deleted_by`, `hidden_with_customer`
- ตารางใหม่ `audit_log`
- migration อัตโนมัติตอนเปิดแอป — ทดสอบกับ schema เก่าจริงแล้ว ข้อมูลเดิมยังอยู่ครบและถือว่าใช้งานอยู่ (`deleted_at IS NULL`)

### Tests
- 240 → 305 tests (100% pass) — รวมเทสต์ที่ fail ถ้า: มีการรีเซ็ตรหัสผ่านโดย Admin หรือปุ่มลบบัญชีกลับมา, มีหน้าที่เปลี่ยนข้อมูลโดยไม่ผ่าน audit trail, มีไอคอนกลับเข้ามาในป้าย UI, หน้าแรกกลับไปโหลดทั้งตาราง หรือรัน readiness checks แบบไม่ cache, และมีการตัด summary ภาษาไทยด้วยจำนวนตัวอักษร

### Docs
- อัปเดตเอกสารทั้งชุดให้ตรงกับ v1.4.0: user_manual (หัวข้อใหม่สำหรับหน้าเพิ่มข้อมูลและประวัติการใช้งาน, FAQ, คำศัพท์, ภาคผนวก), database_design (ตาราง `users` และ `audit_log` ใน ER diagram + data dictionary), architecture (soft delete + audit trail, security model), SETUP, README, ONE_CLICK_RUN, release checklist, CLAUDE.md และ AGENTS.md

### Known limitations
- การลบ "สาย" ในหน้า Admin ยังลบไฟล์และแถวจริง (มีบันทึกใน audit log ว่าใครลบ)
- Admin ยังเป็นคนตั้งรหัสผ่านตั้งต้นตอนสร้างบัญชี — ยังไม่มีการบังคับเปลี่ยนรหัสตอนล็อกอินครั้งแรก
- session ผูกกับ Streamlit — refresh หน้า (F5) = ออกจากระบบ

---

## [1.3.0] — 2026-08-21 — Real login + role-based access control

### Added — Authentication
- ตาราง `users` ใน SQLite (username unique แบบ case-insensitive, display_name, role, PBKDF2 hash, is_active, last_login_at) + CRUD ครบใน `db.py`
- หน้า **เข้าสู่ระบบ** เต็มหน้าจอ — ยังไม่ login = ไม่มี sidebar และเข้าหน้าใดไม่ได้เลย
- Bootstrap admin อัตโนมัติเมื่อยังไม่มีบัญชีใดในระบบ (`admin` / `admin1234`) พร้อมคำเตือนค้างใน sidebar + หน้า readiness จนกว่าจะเปลี่ยนรหัสผ่าน
- หน้าใหม่ `pages/5_👤_Users.py` (Admin เท่านั้น) — เพิ่ม / แก้บทบาท / เปิด-ปิดใช้งาน / รีเซ็ตรหัสผ่าน / ลบบัญชี
- `🔐 บัญชีของฉัน` บนหน้าแรก — ผู้ใช้ทุก role เปลี่ยนรหัสผ่านตัวเองได้
- Brute-force guard: รหัสผิดครบ 5 ครั้ง ล็อกฟอร์ม login 60 วินาที
- Guard rails ในหน้าจัดการผู้ใช้: ต้องเหลือ Admin ที่ใช้งานได้ ≥ 1 บัญชีเสมอ (`auth.would_remove_last_admin()`), และลดสิทธิ์/ลบบัญชีตัวเองไม่ได้

### Added — Role-based navigation
- `auth.ROLE_PERMISSIONS` — matrix สิทธิ์ต่อหน้าในที่เดียว พร้อม `can_access()` / `visible_pages()` / `normalize_role()`
- `Home.py` เปลี่ยนเป็น router ที่ใช้ `st.navigation()` สร้างเมนูจากสิทธิ์ของ role ที่ login อยู่ — **หน้าที่ไม่มีสิทธิ์จะไม่ปรากฏใน sidebar เลย** และพิมพ์ URL ตรง ๆ ก็เด้งกลับหน้าแรก
- `ui_helpers.init_page(page_key)` — server-side guard ประจำทุกหน้า (defense in depth)

| Role | Home | Admin | Dashboard | Customers | Settings | จัดการผู้ใช้ |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Supervisor | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| QA | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Agent | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |

### Changed
- **ลบ demo login ทิ้ง** — เดิมถ้าไม่ตั้ง `SMARTVOICE_USERS` ผู้ใช้พิมพ์ชื่อและ**เลือก role เองได้** (พนักงานเลือก Admin ได้) ตอนนี้ role มาจากบัญชีที่เก็บไว้เท่านั้น
- `SMARTVOICE_USERS` ใน `.env` ลดบทบาทเป็นบัญชีสำรอง — ระบบตรวจฐานข้อมูลก่อน แล้วค่อยตกมาที่ `.env`
- `normalize_role()` map ค่าที่ไม่รู้จักเป็น `Agent` (สิทธิ์ต่ำสุด) — ค่า role เพี้ยนใน DB/.env ยกระดับสิทธิ์ไม่ได้
- หน้า Settings เลิกใช้ `if role in {...}` แบบเขียนเอง เปลี่ยนมาใช้ `init_page(PAGE_SETTINGS)`
- Preflight check "Authentication" เปลี่ยนเป็นเตือนเมื่อบัญชี `admin` ยังใช้รหัสผ่านเริ่มต้น

### Database
- `init_db()` เพิ่มตาราง `users` (`CREATE TABLE IF NOT EXISTS` — ไม่กระทบข้อมูลเดิม)

### Known limitation
- Session ผูกกับ Streamlit session — refresh หน้าเว็บ (F5) = ออกจากระบบ (ยังไม่มี cookie/JWT)

### Tests
- 209 → 240 tests (100% pass) — ครอบคลุม role matrix, DB-first authentication, บัญชีที่ถูกปิดใช้งาน, bootstrap admin, last-admin protection, และ regression test ที่ fail ถ้ามีหน้าใหม่ที่ไม่ได้ผูก permission

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
