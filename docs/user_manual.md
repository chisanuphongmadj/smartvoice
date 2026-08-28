# SmartVoice — คู่มือการใช้งานฉบับสมบูรณ์

> **สำหรับ:** ผู้ดูแล Call Center, QA Supervisor, IT Administrator ของบริษัท Omazz
> **เวอร์ชันเอกสาร:** 1.2.0
> **อัปเดตล่าสุด:** 27 พฤษภาคม 2569
> **เวอร์ชันระบบ:** SmartVoice 1.2.0 (Post-delivery feedback round 1)

---

## สารบัญ

1. [ภาพรวมระบบ](#1-ภาพรวมระบบ)
2. [คุณค่าทางธุรกิจสำหรับ Omazz](#2-คุณค่าทางธุรกิจสำหรับ-omazz)
3. [ความต้องการของระบบ](#3-ความต้องการของระบบ)
4. [การติดตั้งและตั้งค่าครั้งแรก](#4-การติดตั้งและตั้งค่าครั้งแรก)
5. [การเข้าสู่ระบบและ Role](#5-การเข้าสู่ระบบและ-role)
6. [หน้า Home — ภาพรวมและสถานะระบบ](#6-หน้า-home--ภาพรวมและสถานะระบบ)
7. [หน้า Admin — อัปโหลดและประมวลผล](#7-หน้า-admin--อัปโหลดและประมวลผล)
8. [หน้า Dashboard — Analytics](#8-หน้า-dashboard--analytics)
9. [หน้า Customers — ลูกค้าและทะเบียนรับประกัน](#9-หน้า-customers--ลูกค้าและทะเบียนรับประกัน)
10. [หน้า Settings — ตั้งค่าระบบ](#10-หน้า-settings--ตั้งค่าระบบ)
11. [Workflow ตามบทบาท](#11-workflow-ตามบทบาท)
12. [กลไก AI ภายในระบบ](#12-กลไก-ai-ภายในระบบ)
13. [การจัดการเชิง Operations](#13-การจัดการเชิง-operations)
14. [Domain Knowledge ที่ระบบเข้าใจ](#14-domain-knowledge-ที่ระบบเข้าใจ)
15. [คำถามที่พบบ่อยและการแก้ปัญหา](#15-คำถามที่พบบ่อยและการแก้ปัญหา)
16. [คำศัพท์](#16-คำศัพท์)
17. [ภาคผนวก](#17-ภาคผนวก)

---

## 1. ภาพรวมระบบ

**SmartVoice** คือระบบ AI Call Center Analytics สำหรับสายภาษาไทย ออกแบบเฉพาะสำหรับธุรกิจที่นอน/เฟอร์นิเจอร์ในเครือ Omazz (Restonic, Lotus, Slumberland, Dunlopillo)

ระบบรับไฟล์เสียง `.wav` หรือ `.mp3` แล้วทำงาน 4 ขั้นตอนหลัก:

1. **ถอดเสียง** เป็นข้อความภาษาไทยด้วย Whisper STT
2. **แยกผู้พูด** (Agent / Customer) ด้วย Pyannote diarization + Thai-domain rules
3. **วิเคราะห์ด้วย LLM** 4 มิติ:
   - Summary / Topic / Topic Detail / Keywords / Brand Mentions / Platform Mentions
   - Customer Sentiment (positive / neutral / negative) พร้อมเหตุผล
   - Agent Quality Assurance (Politeness + Problem Solving) พร้อมหลักฐาน
   - Anomaly Detection (เคสที่ต้อง escalate)
4. **จัดกลุ่มเคส** อัตโนมัติด้วย recency + LLM topic matching

ผลลัพธ์ทั้งหมดเก็บใน SQLite local และแสดงผ่าน Streamlit dashboard

### 1.1 Architecture สรุป

```
[Audio .wav/.mp3]
       │
       ├── validate + dedup (SHA-256)
       ├── extract phone / direction / agent code จาก filename
       │
       ▼
[Whisper STT] ──► [Pyannote Diarization]
       │                 │
       └────────┬────────┘
                ▼
[Speaker Correction: Multi-pass — LLM + Thai rules]
                │
                ▼
[LLM Analysis × 4 calls (sequential)]
                │
                ▼
[SQLite Database]
                │
                ▼
[Streamlit Dashboard] ← Auto Case Assignment
```

### 1.2 Tech Stack

| ส่วน | เทคโนโลยี |
|------|----------|
| UI | Streamlit (multi-page) |
| Database | SQLite 3 |
| STT (default) | `biodatlab/distill-whisper-th-large-v3` (Thai-tuned) ผ่าน HuggingFace transformers |
| STT (alternative) | `faster-whisper` กับ `large-v3` / `large-v3-turbo` |
| Speaker Diarization | `pyannote/speaker-diarization-3.1` |
| LLM | Ollama + `scb10x/llama3.1-typhoon2-8b-instruct` (Thai-tuned) |
| Language | Python 3.10+ |

### 1.3 ข้อจำกัดของระบบ

- รันแบบ **local single-node app** เท่านั้น (ไม่รองรับ multi-user concurrent processing เกิน 1 thread)
- **ต้องมี Ollama** รันอยู่บน machine เดียวกัน (หรือ remote URL) สำหรับ Real AI mode
- **ต้องมี HuggingFace token** สำหรับ pyannote diarization
- **GPU แนะนำมาก** สำหรับ production load (CPU mode ใช้งานได้แต่ช้ามาก ~10× audio length)
- ภาษาที่รองรับ: **ไทยเป็นหลัก** (Whisper + LLM ทั้งคู่ tune ภาษาไทย)
- รองรับไฟล์เสียง: `.wav` และ `.mp3` ขนาดไม่เกิน 100 MB/ไฟล์

---

## 2. คุณค่าทางธุรกิจสำหรับ Omazz

SmartVoice ออกแบบมาเพื่อตอบโจทย์เฉพาะของ Call Center ในอุตสาหกรรมที่นอน:

| คุณค่า | วิธีที่ระบบมอบให้ |
|---|---|
| **ลดเวลาฟังสายเอง** | ทุกสายมีสรุป + tagged transcript ดูได้ในไม่กี่วินาที |
| **ตรวจคุณภาพ Agent** | คะแนน Politeness + Problem Solving พร้อมหลักฐานคำพูดจริง (audit-ready) |
| **ติดตามเคสลูกค้า** | สายของลูกค้าคนเดียวกันถูกรวมเป็นเคสอัตโนมัติ ไม่ต้องค้นเอง |
| **กระจาย Next Action** | LLM ระบุว่าใครต้องทำอะไรต่อ (Agent / ฝ่ายบัญชี / QC / จัดส่ง) |
| **เจอเรื่องที่ต้อง escalate** | Anomaly Detection แยกเรื่อง "ขู่ฟ้อง / ขอหัวหน้า / safety issue" ออกจาก complaint ปกติ |
| **เห็นภาพรวม** | Dashboard แสดง trend, brand mention, ปัญหายอดนิยม |
| **ตอบ Compliance** | บันทึก `uploaded_by` + `uploaded_by_role` ทุกไฟล์เพื่อ audit |
| **เจาะลึกประเภทความเสียหาย** | Drill-down chart แยก "แจ้งปัญหาสินค้า" เป็น ผ้าขาด / เตียงหัก / สปริงยุบ ฯลฯ |
| **กรองตามทิศทางสาย** | แยก Inbound (ลูกค้าโทรเข้า) vs Outbound (เจ้าหน้าที่โทรออก) ได้ |
| **กรองตาม Agent** | ดูผลงานของพนักงานแต่ละคนได้แยกตามรหัส Agent |

---

## 3. ความต้องการของระบบ

### 3.1 Hardware

| สถานการณ์ | สเปคแนะนำ |
|---|---|
| **Demo / Mock** | CPU 4 core + RAM 8 GB ก็พอ — ใช้ transcript จำลอง ไม่รัน STT จริง |
| **Real AI — CPU only** | CPU 8 core + RAM 16 GB — ทำงานได้แต่ ~10× audio length per call |
| **Real AI — GPU (production)** | NVIDIA GPU 8+ GB VRAM + RAM 16 GB — เร็ว ~0.3× audio length |
| **Storage** | SSD 50+ GB (model weights ~5 GB + audio + DB) |

GPU ที่ทดสอบแล้ว: NVIDIA RTX 3060 / 3070 / 3080 / 4070 / 4080 / 5070 Ti ขึ้นไป

### 3.2 Software

| โปรแกรม | เวอร์ชัน |
|---|---|
| Windows | 10 / 11 (พัฒนาและทดสอบบน Windows) |
| Python | 3.10 หรือ 3.11 |
| FFmpeg | จำเป็น (สำหรับโหลด `.mp3`) |
| Ollama | v0.1.30+ |
| CUDA Toolkit | 12.x (เฉพาะกรณีใช้ GPU) |

### 3.3 Network

- ครั้งแรกที่ติดตั้ง: ต้องมีอินเทอร์เน็ตเพื่อ download model weights (~5 GB)
- รันงานปกติ: **ไม่ต้องใช้อินเทอร์เน็ต** (model ทั้งหมดรัน local)
- ยกเว้น: ถ้าตั้ง `OLLAMA_BASE_URL` ชี้ไป Ollama Cloud จะต้องมี net ตลอด

### 3.4 ข้อมูลที่ระบบสร้าง

- ฐานข้อมูล: `data/smartvoice.db` (SQLite — backup ได้ด้วยการ copy ไฟล์)
- ไฟล์เสียง: `data/raw_audio/` (กันซ้ำด้วย SHA-256)
- โมเดล AI: `data/models/` (cache CT2-converted models)
- Log: `data/logs/smartvoice.log` (rotating)

---

## 4. การติดตั้งและตั้งค่าครั้งแรก

### 4.1 One-Click Installation (แนะนำ)

```powershell
# ที่โฟลเดอร์โปรเจกต์
run.bat
```

`run.bat` จะ:
1. สร้าง Python virtual environment `.venv\` (ถ้ายังไม่มี)
2. ติดตั้ง dependencies ทั้งหมด
3. สร้าง `.env` จาก `.env.example` (ถ้ายังไม่มี)
4. ตรวจ CUDA / Ollama
5. เปิดเบราว์เซอร์ไปที่ `http://localhost:8501`

ครั้งแรก ใช้เวลา ~10-15 นาที (download model)

### 4.2 ติดตั้ง Manual

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e . --no-deps
copy .env.example .env
streamlit run Home.py
```

### 4.3 ตั้งค่า Ollama

```bash
# ติดตั้ง Ollama จาก https://ollama.com/download

# Pull โมเดลที่ระบบใช้
ollama pull scb10x/llama3.1-typhoon2-8b-instruct

# เริ่ม service (ปกติทำงานเป็น background อัตโนมัติ)
ollama serve
```

### 4.4 ตั้งค่า HuggingFace Token

จำเป็นสำหรับ pyannote diarization (ถอด speaker)

1. สมัครบัญชีที่ https://huggingface.co/
2. ขออนุญาตเข้าถึง `pyannote/speaker-diarization-3.1` (Accept terms)
3. สร้าง access token ที่ `Settings → Access Tokens`
4. ใส่ใน `.env`:
   ```
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
   ```
   หรือใส่ผ่านหน้า Settings ในแอป

### 4.5 ตรวจความพร้อมระบบ

เปิดหน้า Home → กดขยาย "Deployment readiness" จะแสดง check list:

- ✅ Ollama reachable
- ✅ Ollama model available
- ✅ HuggingFace token present
- ✅ GPU detected (ถ้ามี)
- ✅ Whisper model cached
- ✅ Database initialized

ถ้ามีรายการเป็น ❌ ให้แก้ตามคำแนะนำก่อนเริ่ม process

---

## 5. การเข้าสู่ระบบและ Role

### 5.1 Login

เปิดแอปแล้วจะเจอหน้า **เข้าสู่ระบบ** เต็มหน้าจอ — ยังไม่มี sidebar และเข้าหน้าอื่นไม่ได้จนกว่าจะ login สำเร็จ

- ระบบตรวจ username + password กับ hash แบบ PBKDF2-SHA256 เสมอ (ไม่มีโหมดพิมพ์ชื่อเข้าเองแล้ว)
- **role มาจากบัญชีที่เก็บไว้เท่านั้น** ผู้ใช้เลือก role เองไม่ได้
- ใส่รหัสผิดครบ 5 ครั้ง ระบบจะล็อกช่อง login 60 วินาที
- refresh หน้าเว็บ (F5) = ออกจากระบบ เพราะ session ผูกกับ browser session ของ Streamlit

**เข้าใช้งานครั้งแรก:** ถ้ายังไม่มีบัญชีใดในระบบ แอปจะสร้างบัญชีเริ่มต้นให้อัตโนมัติ

| Username | Password |
|---|---|
| `admin` | `admin1234` |

> ⚠️ sidebar และหน้า readiness จะขึ้นเตือนตลอดจนกว่าจะเปลี่ยนรหัสผ่าน — เปลี่ยนได้ที่ **sidebar → กล่องบัญชี → 🔐 เปลี่ยนรหัสผ่าน** (ใช้ได้จากทุกหน้า)

### 5.2 การสร้างและจัดการผู้ใช้

login ด้วย role **Admin** แล้วเข้าหน้า **👤 จัดการผู้ใช้** ใน sidebar:

- **เพิ่มผู้ใช้ใหม่** — username (a-z 0-9 . _ - อย่างน้อย 3 ตัว), ชื่อที่แสดง, บทบาท, รหัสผ่าน (อย่างน้อย 8 ตัว)
- **แก้ไขบัญชี** — เปลี่ยนชื่อที่แสดง / บทบาท / ปิด-เปิดการใช้งาน
- **รีเซ็ตรหัสผ่าน** ให้พนักงานที่ลืมรหัส
- **ลบบัญชี** (ต้องติ๊กยืนยันก่อน)

ข้อจำกัดที่ระบบบังคับให้เอง:

- ต้องเหลือบัญชี Admin ที่เปิดใช้งานอย่างน้อย 1 บัญชีเสมอ
- ลดสิทธิ์ / ปิดใช้งาน / ลบบัญชีของตัวเองไม่ได้
- ผู้ใช้ที่ถูกปิดใช้งาน login ไม่ได้ทันที

**ทางเลือกสำรอง (`.env`)** — ถ้าอยากตั้งบัญชีจากไฟล์แทน (เช่นบัญชีสำรองไว้กู้ระบบ) ยังใช้ `SMARTVOICE_USERS` ได้:

```powershell
python scripts\make_password_hash.py admin Admin
```

จะได้ผลลัพธ์รูปแบบ:
```
admin|Admin|pbkdf2_sha256$260000$xxxxxx$yyyyyyyyy...
```

นำไปใส่ใน `.env` คั่นหลายผู้ใช้ด้วย `;`:

```env
SMARTVOICE_USERS=admin|Admin|pbkdf2_sha256$...;qa1|Supervisor|pbkdf2_sha256$...
```

ระบบจะตรวจบัญชีในฐานข้อมูลก่อนเสมอ แล้วค่อยตกมาที่ `.env` — บัญชีจาก `.env` เปลี่ยนรหัสผ่านผ่านหน้าเว็บไม่ได้

### 5.3 บทบาทผู้ใช้ (Roles)

| Role | หน้าแรก | Admin | Dashboard | Customers | Settings | จัดการผู้ใช้ |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| **Admin** (ผู้ดูแลระบบ) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Supervisor** (หัวหน้างาน) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **QA** (ฝ่ายควบคุมคุณภาพ) | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| **Agent** (พนักงานรับสาย) | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |

หน้าที่ role ไม่มีสิทธิ์จะ **ไม่ปรากฏใน sidebar เลย** และถ้าพิมพ์ URL ตรง ๆ (เช่น `/admin`) ระบบจะเด้งกลับหน้าแรก — เพราะ `Home.py` สร้างเมนูจาก `auth.visible_pages(role)` และทุกหน้ายังมี `init_page(PAGE_*)` ตรวจซ้ำอีกชั้นบน server

บทบาทที่ระบบไม่รู้จักจะถูกลดเป็น `Agent` (สิทธิ์ต่ำสุด) โดยอัตโนมัติ

### 5.4 Audit Trail

ทุกไฟล์ที่ upload จะถูกบันทึก `uploaded_by` (ชื่อ login) และ `uploaded_by_role` ลงในฐานข้อมูล สามารถดูได้ใน Admin → expander ของแต่ละสาย

---

## 6. หน้า Home — ภาพรวมและสถานะระบบ

### 6.1 ส่วนประกอบ

```
┌─ Title bar ─────────────────────────────────┐
│ 🎙️ Thai Call Analytics                       │
│ AI-powered Call Center Analytics for...     │
├─────────────────────────────────────────────┤
│ ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐         │
│ │Total│  │Done │  │Proc.│  │Pend.│         │
│ │  X  │  │  Y  │  │  Z  │  │  W  │         │
│ └─────┘  └─────┘  └─────┘  └─────┘         │
├─────────────────────────────────────────────┤
│ 👈 เลือกหน้าจาก sidebar เพื่อเริ่มใช้งาน        │
├─────────────────────────────────────────────┤
│ ▶ Deployment readiness                      │
│   (กดขยายเพื่อดู preflight checks)            │
└─────────────────────────────────────────────┘
```

### 6.2 KPI Card ทั้ง 4 ใบ

- **Total Calls** — จำนวนสายทั้งหมดในระบบ
- **Done** — สายที่ประมวลผลเสร็จแล้ว
- **Processing** — สายที่กำลังประมวลผล
- **Pending** — สายที่อัปโหลดแล้วยังไม่ได้กด process

### 6.3 Deployment readiness

แสดง preflight check ของระบบทั้งหมด ใช้เพื่อ:
- ตรวจก่อนเริ่มงานครั้งแรกของวัน
- ตรวจหลังเปลี่ยน Settings
- Troubleshoot เมื่อ process fail

---

## 7. หน้า Admin — อัปโหลดและประมวลผล

หน้าหลักของผู้ดูแล แบ่งเป็น 3 section

### 7.1 Section 1 — Upload Audio Files

**รูปแบบชื่อไฟล์ที่แนะนำ (CDR pattern):**

```
YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.wav
```

ตัวอย่าง:
- `20251104173706-1762252614.105999-104-0819979336-Outbound.wav`
- `20251225134209-1766644826.135925-0631451550-104-Inbound.wav`

ระบบจะดึงข้อมูลเหล่านี้จาก filename อัตโนมัติ:

| ข้อมูล | วิธีดึง | ใช้ทำอะไร |
|---|---|---|
| **เบอร์โทรลูกค้า** | regex หาเลข 10 หลักขึ้นต้น 0 | auto-link กับลูกค้า/warranty ในฐานข้อมูล |
| **ทิศทางสาย** | suffix `-Inbound.wav` หรือ `-Outbound.wav` | filter ในตารางสาย |
| **รหัส Agent** | segment ตัวเลข 2-5 หลัก (ไม่ใช่ timestamp ไม่ใช่เบอร์) | คอลัมน์ Agent ใน Agent Performance |
| **วันเวลาโทรจริง** | 14 ตัวแรก `YYYYMMDDHHMMSS` | (เก็บใน filename) |

**ขั้นตอน Upload:**

1. Drag-drop หรือ Browse ไฟล์ `.wav` / `.mp3`
2. ระบบตรวจ:
   - นามสกุลถูกต้อง
   - magic bytes ตรงกับ wav/mp3
   - ขนาดไม่เกิน 100 MB
3. คำนวณ SHA-256 → ถ้าไฟล์ซ้ำในระบบจะแจ้งและไม่ insert ใหม่
4. เซฟไฟล์ + insert row ใน `calls` table พร้อม `uploaded_by` / `uploaded_by_role`
5. ดึงเบอร์จาก filename → ถ้าพบลูกค้าในระบบจะ link ทันที (`matched_by='auto_phone'`)

### 7.2 Section 2 — Process Calls

แสดง KPI 4 ใบ (Pending / Processing / Done / Errors) ที่ใช้ **SQL aggregate** (`COUNT(*) GROUP BY status`) — ตัวเลขแม่นเสมอแม้ตารางจะใหญ่ระดับหมื่นแถว

**ปุ่ม "▶ Process All Pending":**

- ใช้งานได้เมื่อ Ollama พร้อมและมีสาย pending
- กดแล้วระบบจะ queue ทุก pending call ทำทีละ 1 เป็น background daemon thread
- ระหว่าง process หน้าจะ refresh ทุก 3 วินาที แสดง step ปัจจุบัน เช่น:
  - "ถอดเสียงและแยกผู้พูด..."
  - "ตรวจแก้ transcript..."
  - "แก้ speaker turn..."
  - "วิเคราะห์บทสนทนา..."
  - "บันทึกผล / จัดกลุ่มเคส"

**ปุ่ม "🧹 ล้างเคสค้าง"** (แสดงเมื่อพบ orphan case)

ใช้ลบเคสที่ไม่มีสายชี้มาแล้ว (เกิดจากการลบไฟล์เสียงก่อนหน้า)

### 7.3 Section 3 — Individual Call Actions

ตารางสายแต่ละไฟล์ พร้อมเครื่องมือกรอง

#### 7.3.1 ขอบเขตการโหลด (Load Limit)

dropdown แรกของ section นี้ — เลือกจำนวนสายที่จะโหลดเข้ามาแสดง:

| ตัวเลือก | เหมาะกับ |
|---|---|
| 100 สายล่าสุด | ดูงานวันนี้ |
| 200 สายล่าสุด (default) | ดูงานสัปดาห์นี้ |
| 500 / 1,000 / 5,000 ล่าสุด | reporting รายเดือน |
| ทั้งหมด | analytics ระดับ raw data (ช้าเมื่อข้อมูลเยอะ) |

**สำคัญ:** KPI cards ด้านบน (Pending/Processing/Done/Errors) แสดงตัวเลขรวมทั้งระบบเสมอ ไม่ได้ขึ้นกับ load limit นี้

#### 7.3.2 Toolbar ค้นหา + กรอง

| เครื่องมือ | ใช้ทำอะไร |
|---|---|
| 🔍 ช่องค้นหา | ค้นจากชื่อไฟล์ / เบอร์ / ผู้ upload |
| Radio สถานะ | ทั้งหมด / Pending / Processing / Done / Error |
| Radio ทิศทาง | ทั้งหมด / 📥 Inbound / 📤 Outbound |
| Dropdown เรียง | ใหม่→เก่า / เก่า→ใหม่ / ตามสถานะ |

filter ทุกอันทำงานพร้อมกันได้ — ตัวเลขด้านล่างจะแสดงว่ากรองเหลือกี่รายการจากทั้งหมด

#### 7.3.3 Bulk Actions

- **☑ Select All (ที่กรองอยู่):** เลือกทุกแถวที่อยู่ใน filter ปัจจุบัน
- **☐ Deselect All:** ยกเลิกเลือกทั้งหมด
- **🗑 Delete Selected (N):** ลบทั้งไฟล์ในดิสก์และ record ใน DB

⚠️ การลบไม่สามารถกู้คืนได้

#### 7.3.4 Individual Call Card

แต่ละแถวคือ expander มีหัวข้อรูปแบบ:

```
🎵 [filename]  —  🟢 DONE  📞 0819979336  •  📅 2026-05-20  •  👤 Admin Name
```

กดขยายจะเห็น:

- ✓ Checkbox เลือก
- ข้อมูล: customer phone, uploader, dates, status, transcript size
- ปุ่ม Process / Re-process / Delete
- (ถ้า done) Tagged transcript, สรุป, Analysis JSON
- (ถ้า done + มีเคส) ลิงก์ไปดูเคส
- ปุ่ม "เชื่อมลูกค้าด้วยตนเอง" ถ้าระบบหาไม่เจอจาก phone

#### 7.3.5 Pagination

แสดงครั้งละ 20 แถว — กด "⬇ แสดงเพิ่ม" เพื่อขยายขอบเขต ภายใน load limit ที่เลือกไว้

---

## 8. หน้า Dashboard — Analytics

### 8.1 Filter Panel (กดขยายเริ่มต้น)

| Filter | ตัวเลือก |
|---|---|
| **Date range** | เลือกช่วงวันที่ตามจริง |
| **Intent / Topic** | dropdown ตามค่าใน DB |
| **Sentiment** | All / positive / neutral / negative |
| **จำนวนสายที่โหลด** | 100 / 500 / 1,000 (default) / 5,000 / ทั้งหมด |

Dashboard เน้น analytics — default 1,000 ล่าสุด ให้ chart มี signal มากพอ

### 8.2 KPI 4 ใบ

- **Total Calls** ในช่วงที่กรอง
- **Positive 😊** จำนวนสาย sentiment บวก
- **Neutral 😐** กลาง
- **Negative 😠** ลบ

### 8.3 Sentiment Distribution

แท่งกราฟ 3 แท่ง (positive / neutral / negative) สีตาม semantic mapping:
- 🟢 เขียวมิ้นต์ = positive
- ⚪ สเลทเทาฟ้า = neutral
- 🔴 แดงนวล = negative

### 8.4 Topic / Intent Distribution

แท่งกราฟแนวนอน เรียงจากมากไปน้อย แสดง topic หลักของแต่ละสาย

หมวด topic ที่ระบบใช้ (controlled vocabulary):

| Topic | ความหมาย |
|---|---|
| สอบถามข้อมูลสินค้า | ถามเรื่องสินค้า/รุ่น/วัสดุ/คุณสมบัติ |
| สอบถามการจัดส่ง | ถามสถานะจัดส่ง/ระยะเวลา/พื้นที่จัดส่ง |
| แจ้งปัญหาสินค้า | สินค้าชำรุด/เสียหาย/ไม่ตรงปก/น้ำท่วม |
| ร้องเรียนบริการ | ไม่พอใจการบริการ/พนักงาน/ขั้นตอน |
| สอบถามประกัน/Warranty | เงื่อนไขประกัน/เคลม/ระยะเวลา |
| คืน/เปลี่ยน/Trade-in | ขอคืน/เปลี่ยนสินค้า/Trade-in |
| สอบถามโปรโมชั่น | ถามโปร/ส่วนลด/ราคาพิเศษ |
| ติดตามเคส | ติดตามเรื่องที่แจ้งไว้ |
| อื่นๆ | ไม่เข้าหมวดใดข้างต้น |

#### 8.4.1 Drill-down: ประเภทความเสียหายภายใน "แจ้งปัญหาสินค้า"

ใต้กราฟ Topic หลัก จะมี chart ย่อย (โทนแดง) แสดงเฉพาะสายที่ topic = "แจ้งปัญหาสินค้า" แยกตาม **topic_detail** (Omazz feedback)

vocabulary ของ topic_detail:

| ประเภท | ตัวอย่างคำที่พบ |
|---|---|
| ผ้าขาด/ผ้าหุ้มชำรุด | ผ้าหุ้ม, ปลอก, ผ้าฉีก, ผ้าหลุดลุ่ย |
| เตียง/โครงหัก | โครงเตียง, ขาเตียง, หัวเตียงหัก |
| สปริง/ฟองน้ำยุบ | ที่นอนยุบเป็นแอ่ง, สปริงโผล่, ฟองน้ำเสียรูป |
| เปื้อน/รอยขีดข่วน | คราบ, รอยขีด, รอยถลอก |
| ความชื้น/น้ำท่วม | เชื้อรา, ความชื้น, น้ำท่วม, อับชื้น |
| ขนาด/สเปคผิด | ขนาดไม่ตรง, รุ่นผิด, สี/วัสดุไม่ตรงปก |
| อื่นๆ | นอกเหนือ 6 หมวด |

chart นี้แสดงเฉพาะเมื่อ scope ที่กรองมีสาย product-issue อยู่

### 8.5 Issue Keywords

word cloud-style แท่งกราฟแสดง 15 keyword ยอดนิยมที่ LLM สกัดจากสายในช่วงที่กรอง (เช่น "ที่นอน", "คืนเงิน", "หมอนเบ็ด", "จัดส่ง")

### 8.6 Brand Mentions

แท่งกราฟแสดงแบรนด์ที่ถูกพูดถึงทั้งหมด รวมถึง:
- แบรนด์ในเครือ Omazz: Omazz, Restonic, Lotus/โลตัส, Slumberland, Dunlopillo
- คู่แข่ง: Sealy, Therapedic, King Koil, Simmons, Serta, Stearns & Foster, Synda, Satin (เพื่อ competitive intelligence)

### 8.7 Platform / Channel Mentions

แสดงช่องทางที่ลูกค้าพูดถึง: Shopee, Lazada, TikTok Shop, LINE, Facebook, หน้าร้าน/ห้าง/ช็อป, เว็บไซต์, โทรศัพท์

### 8.8 Anomaly Detection

แสดง 2 KPI card:
- **🔺 Anomaly Calls** — จำนวนสายที่ถูก flag
- **✅ Normal Calls** — สายปกติ

ถ้ามี anomaly จะแสดงตารางพร้อม:
- Filename / Date / Phone
- Anomaly Reason (พร้อม quoted evidence จาก transcript)
- Severity (low / medium / high)

### 8.9 Top 3 Issues

แท่งกราฟแสดง 3 issues ที่พบบ่อยที่สุดในสายที่:
- Sentiment = negative **หรือ**
- Anomaly = detected

ใช้สำหรับ identify "ปัญหาหลัก" ของช่วงเวลานี้

### 8.10 Agent Performance

ส่วนสำคัญสำหรับ QA Supervisor

#### 8.10.1 KPI 3 ใบ

- **Avg Agent Score / 10** — ค่าเฉลี่ยรวมของทุกแถว
- **Best 🏆** — แถวคะแนนสูงสุด (filename หรือชื่อเคส)
- **Needs Improvement 📋** — แถวคะแนนต่ำสุด

#### 8.10.2 Filter Row

| Filter | ใช้ทำอะไร |
|---|---|
| 🔍 ค้นหา | เบอร์ / ชื่อไฟล์ / Subject เคส / Next Action |
| **Agent** (dropdown) | กรองตามรหัสพนักงาน เช่น 102, 104 — ดึงจาก filename |
| กรองตามคะแนน | ทั้งหมด / < 6 (ต้องปรับปรุง) / 6-7.9 (พอใช้) / ≥ 8 (ดี) |
| แถวต่อหน้า | 10 / 25 / 50 / 100 |

#### 8.10.3 ตาราง Agent Performance

| คอลัมน์ | คำอธิบาย |
|---|---|
| **สาย / เคส** | filename หรือ "📂 เคส #N — subject (N สาย)" |
| **Agent** | รหัส Agent (เช่น 104) — ถ้าเคสมีหลาย Agent จะเป็น "102, 104" |
| **Politeness** | คะแนน 0-5 (จาก LLM) |
| **หลักฐาน Politeness** | quote จาก transcript ระบุ "ทำได้: ..." / "ไม่ได้: ..." |
| **Problem Solving** | คะแนน 0-5 |
| **หลักฐาน Problem Solving** | quote จาก transcript |
| **Score** | Politeness + Problem Solving = 0-10 (progress bar) |
| **Next Action 📌** | งานที่ต้องทำต่อ |
| **ผู้รับผิดชอบ 👤** | Agent คนเดิม / ฝ่ายบัญชี / ฝ่าย QC / ฝ่ายจัดส่ง / หัวหน้าทีม |

**สำคัญ:**
- ถ้าเคส `closed` → Next Action จะเป็น "— เคสปิดแล้ว"
- คะแนน Politeness + Problem Solving ถูก clamp ให้อยู่ช่วง 1-5 ใน backend
- `overall_score` คำนวณใน Python (ไม่ trust LLM ตอบโดยตรง)
- หลักฐานทั้งสองถูก sanitize ลบข้อความที่ดูเหมือน copy ตัวอย่างจาก prompt

### 8.11 Case Management Summary

KPI 4 ใบ:
- Total Cases
- 🟢 เปิด (Open)
- 🟡 ติดตาม (Follow-up)
- 🔴 ปิด (Closed)

ใต้นั้นแสดงตาราง cases พร้อม search/filter:
- Subject
- Customer name + phone
- จำนวนสาย
- Status
- Last update
- ปุ่มไปดูรายละเอียดใน Customers

### 8.12 ตารางสรุปทุกสาย (Bottom Table)

ดู raw data ของทุกสายในช่วงที่กรอง — ใช้สำหรับ export, audit, deep dive

---

## 9. หน้า Customers — ลูกค้าและทะเบียนรับประกัน

### 9.1 Tab "👤 ลูกค้า"

- ตารางลูกค้าทั้งหมด
- ค้นหาด้วยชื่อ หรือเบอร์
- **เลือกลูกค้า 1 คน** → ขยายดู:
  - ข้อมูลทั่วไป (ชื่อ, เพศ, วันเกิด, เบอร์, อีเมล, ที่อยู่)
  - **ทะเบียนรับประกัน** ของลูกค้านั้น (รุ่นที่นอน, ขนาด, ระยะเวลา warranty, วันที่ซื้อ, ช่องทาง)
  - **เคส** ของลูกค้านั้น (เปิด, follow_up, closed) — ขยายดูสายในเคส
  - **สายที่เชื่อมไว้แต่ยังไม่มีเคส** (ปกติเป็นสายที่ pipeline ยังไม่ได้ assign case)

### 9.2 Tab "🛡 ทะเบียนรับประกัน"

- ตารางทะเบียนรับประกันทั้งระบบ
- ค้นหาด้วย: ชื่อลูกค้า, เบอร์, เลขทะเบียน, Serial, แบรนด์, รุ่น
- กรองด้วย:
  - **แบรนด์** (multi-select)
  - **ช่องทางซื้อ** (multi-select)
  - **หมวดหมู่** (multi-select)
- แสดง 4 KPI:
  - ทั้งหมด
  - แบรนด์หลัก (top brand ใน scope)
  - ช่องทางหลัก
  - หมวดหมู่หลัก

---

## 10. หน้า Settings — ตั้งค่าระบบ

> เข้าได้เฉพาะ role `Admin` หรือ `Supervisor`

### 10.1 Quick Mode (ปุ่ม preset)

| ปุ่ม | ทำอะไร |
|---|---|
| **Use Demo Laptop Mode** | ตั้ง `MOCK_STT=true`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE=int8` — สำหรับ demo บน laptop ที่ไม่มี GPU |
| **Use Real AI Mode** | ตั้งค่ามาตรฐานเต็มชุดสำหรับ production: biodatlab + transformers + auto + auto |

### 10.2 Current Mode

แสดงสถานะปัจจุบัน:
- STT mode: Demo / Mock หรือ Real AI
- HF token mask (เช่น `hf_xxxxx...xxxx`)

### 10.3 Demo & AI Settings

#### 10.3.1 Demo mode toggle

เปิด/ปิด `MOCK_STT` — ตอนเปิด ระบบจะใช้ transcript จำลอง (สำหรับ demo บน laptop ที่ไม่มี GPU)

#### 10.3.2 Real AI section

- **HuggingFace token** (password field) — สำหรับ pyannote
- **Clear saved HuggingFace token** checkbox
- **Ollama base URL** — default `http://localhost:11434`
- **Ollama model** — ใส่ชื่อโมเดล Ollama อิสระ (default `scb10x/llama3.1-typhoon2-8b-instruct`)

#### 10.3.3 Speech model section

แสดง GPU detection banner ก่อน:
- 🚀 **ถ้ามี GPU:** แสดงชื่อ GPU เช่น "NVIDIA GeForce RTX 5070 Ti — เลือก device=cuda ได้"
- ⚠️ **ถ้าไม่มี GPU:** ซ่อน option `cuda` จาก Device dropdown อัตโนมัติ และแนะนำใช้ device=cpu + compute=int8

มี caption เตือน:

> 💡 เปลี่ยน Whisper model → ระบบจะปรับ Backend / Device / Compute เป็นค่าแนะนำให้อัตโนมัติ (หลังจากนั้นปรับเองได้)

**Auto-recommend combo per model:**

| Whisper model | Backend แนะนำ | Device | Compute |
|---|---|---|---|
| `biodatlab/distill-whisper-th-large-v3` | transformers | auto | auto |
| `large-v3` | faster-whisper | auto | auto |
| `large-v3-turbo` | faster-whisper | auto | auto |

เมื่อผู้ใช้เลือกโมเดล ระบบจะตั้ง Backend/Device/Compute ให้อัตโนมัติทันที (สามารถปรับเองทีหลังได้)

#### 10.3.4 Save Settings + Validation

หลังกด Save:
1. เขียนค่าลง `.env` แบบ atomic
2. แสดง success message + เตือนให้ restart
3. รัน combo validation:
   - 🔴 **Error:** combo ที่จะ crash แน่ ๆ (เช่น cuda แต่ไม่มี GPU)
   - 🟡 **Warning:** combo ไม่ดีแต่ใช้ได้ (เช่น cpu + float16)
   - 🔵 **Info:** combo ใช้ได้แต่ต้องรู้ side effect (เช่น faster-whisper + biodatlab → ต้องแปลง CT2)

⚠️ **ต้อง restart แอป** เพื่อให้ทุก module โหลด env ใหม่ — Streamlit ไม่ reload module โดยอัตโนมัติเมื่อ env เปลี่ยน

### 10.4 Readiness Checks

ส่วนล่างสุดของหน้า — แสดง preflight check เหมือนใน Home แต่รัน real-time

---

## 11. Workflow ตามบทบาท

### 11.1 ผู้ดูแล Call Center (Daily Operator)

**กิจวัตรประจำวัน:**

```
08:00 — เปิดแอป → Home → ดู KPI งานค้างจากเมื่อวาน
08:15 — Admin → Upload ไฟล์เสียงของวันก่อน (drag-drop ทั้ง folder)
08:30 — กด "▶ Process All Pending" → ปล่อยรันใน background
       → ทำงานอื่นรอ (ระบบจะแจ้งเมื่อเสร็จ)
14:00 — กลับมา Admin → Filter "Done" + วันนี้ → ดูสายที่เสร็จ
14:30 — Dashboard → ดู Anomaly Calls วันนี้ → escalate ถ้ามี
17:00 — สรุปงานวัน → export ตารางจาก Dashboard ถ้าต้องการ
```

### 11.2 QA Supervisor (Weekly QA)

**กิจวัตรรายสัปดาห์:**

```
Mon AM — Dashboard → ตั้ง Date range "7 วันที่แล้ว"
       → ดู Agent Performance
       → Filter Agent ทีละคน → ดูคะแนน Politeness / Problem Solving
       → เลือกแถวคะแนน < 6 → ฟังสายจริง + อ่าน evidence
       → บันทึก feedback แต่ละ Agent
Mon PM — Dashboard → Top 3 Issues + Issue Keywords
       → ระบุ trend สัปดาห์นี้
       → ประชุมทีมแก้ปัญหา
```

### 11.3 IT Administrator (System Owner)

**กิจวัตรรายเดือน:**

```
- ตรวจ data/logs/smartvoice.log มี error pattern หรือไม่
- Backup data/smartvoice.db (copy file)
- ตรวจ disk usage ของ data/raw_audio/
- อัปเดต Ollama model ถ้ามี version ใหม่:
    ollama pull scb10x/llama3.1-typhoon2-8b-instruct
- ดู Settings → Readiness Checks → แก้ rogue check
- ลบไฟล์เก่าที่ไม่ใช้แล้ว (ทำผ่าน Admin → Filter + Delete Selected)
```

---

## 12. กลไก AI ภายในระบบ

### 12.1 STT — Speech to Text

ใช้ 2 backend ได้:

**transformers (default)** — เหมาะกับโมเดล HF อย่าง `biodatlab/distill-whisper-th-large-v3`
- ทำงานได้ทันทีบน HF model ทุกตัว
- ใช้ chunk 15 วินาที + initial prompt ภาษาไทย
- กรอง hallucination จาก URL/promo/ฟุตบอลออก

**faster-whisper** — เหมาะกับโมเดลมาตรฐาน `large-v3`, `large-v3-turbo`
- เร็วกว่า transformers ~2-3 เท่า
- ถ้าใส่โมเดล non-standard ระบบจะแปลงเป็น CT2 ครั้งแรก (5-10 นาที, cache ไว้)
- มี VAD (Voice Activity Detection) + hotwords

ทั้งสอง backend มี **automatic fallback** — ถ้า primary fail ระบบจะลอง backend อื่นโดยอัตโนมัติ

### 12.2 Diarization + Speaker Correction

Pyannote ทำ diarization → ระบบ correction หลายชั้น:

```
1. Split mega-chunks ที่ Whisper return (>30s) เป็น 15s chunks
2. ระบุ Agent vs Customer ด้วย LLM
3. Override ด้วย deterministic Thai rules:
   • คุณลูกค้า, ทางบริษัท, พลอย, สวัสดีค่ะ [บริษัท] → Agent
   • พี่ + verb, ติดตามเรื่อง, ขอเลื่อนวัน, ได้ไหมลูก → Customer
4. 9 splitter functions แยก turn ผสม Q&A
5. Stabilize sandwich turns (A-B-A pattern)
6. Override อีกรอบหลัง split
7. Merge adjacent same-speaker
8. Enforce role rules (Agent ต้องเริ่มสาย ฯลฯ)
9. Cleanup transcript ด้วย LLM (text polish)
10. ทำซ้ำ step 2-8 รอบ 2
11. Domain normalization + dedup drops
```

ขั้นตอนนี้ป้องกันปัญหาที่ pyannote หรือ LLM แยก speaker ผิด — ระบบ override ด้วย Thai-specific cues ที่ deterministic

### 12.3 LLM Analysis (4 calls)

ทำงาน sequential ไม่ใช่ parallel:

| Call | สิ่งที่ทำ | Output fields |
|---|---|---|
| 1 | Extraction | summary, topic, topic_detail, keywords, brand_mentions, platform_mentions |
| 2 | Sentiment | sentiment (positive/neutral/negative), sentiment_reason |
| 3 | Agent QA | politeness, politeness_evidence, problem_solving, problem_solving_evidence, overall_score, next_action, next_action_owner |
| 4 | Anomaly | anomaly_detected, anomaly_reason, anomaly_severity |

แยกเพราะ:
- context window ของ LLM 8B model จำกัด
- งานคนละแนวคิด → prompt แยกช่วยให้คะแนนแม่นขึ้น
- ถ้า call ใด fail สามารถ fallback empty dict ได้โดยไม่กระทบ call อื่น

### 12.4 Auto Case Assignment

ลำดับการตัดสินใจ:

```
1. ถ้าไม่มีลูกค้าผูกกับสาย → skip
2. หาเคสเปิด/follow-up ของลูกค้านี้
3. ถ้าไม่มี → สร้างเคสใหม่ทันที
4. ถ้ามี:
   a. ดูสายล่าสุดในเคสนั้น — ห่างจากปัจจุบัน < CASE_RECENCY_HOURS (default 4h)?
      → YES: attach ทันที (recency short-circuit, ไม่ถาม LLM)
      → NO: ไปขั้นต่อไป
   b. ส่ง topic + summary ของสายใหม่ + เคสเปิดทั้งหมด → ให้ LLM ตัดสิน
   c. ถ้า LLM ตอบ "match เคส X" → attach
   d. ถ้า LLM ตอบ "ไม่ match" → สร้างเคสใหม่
5. ถ้า attach กับเคสเดิม → เปลี่ยน status เป็น follow_up
```

Recency short-circuit ทำให้ระบบไม่เสียเวลาเรียก LLM สำหรับเคสที่เป็น follow-up ชัดเจน

---

## 13. การจัดการเชิง Operations

### 13.1 Re-processing สายเดิม

เมื่อต้องการรัน analysis ใหม่ (เช่น ปรับ prompt แล้ว) ทำได้ 2 วิธี:

**วิธี A — Re-process ในแอป:**
- Admin → กดขยาย card ของสาย → ปุ่ม "Re-process"
- ระบบจะ rerun pipeline ทั้งหมดสำหรับสายนั้น

**วิธี B — Bulk re-process ผ่าน DB:**
ยังไม่มี UI — ต้อง update DB ตรง:
```sql
UPDATE calls SET status = 'uploaded' WHERE id IN (...)
```
แล้วกด "Process All Pending"

### 13.2 Backfill Scripts

**`scripts/scrub_existing_next_actions.py`** — ลบ prompt-example placeholder ที่หลุดเข้า `agent_performance` เก่า

```powershell
# dry-run (default — แสดงผลที่จะแก้)
python scripts\scrub_existing_next_actions.py

# apply
python scripts\scrub_existing_next_actions.py --apply
```

**`scripts/backfill_topic_detail.py`** — re-classify topic_detail ของสายเก่าที่ topic="แจ้งปัญหาสินค้า" แต่ยังไม่มี detail

```powershell
# dry-run
python scripts\backfill_topic_detail.py

# apply
python scripts\backfill_topic_detail.py --apply

# จำกัดแค่ N สาย (สำหรับทดสอบ)
python scripts\backfill_topic_detail.py --limit 5 --apply
```

Script จะใช้ LLM-only (ไม่รัน STT ซ้ำ) — เร็วกว่า re-process เต็มรูปแบบมาก

### 13.3 การลบข้อมูล

- **ลบทีละสาย:** Admin → expander → ปุ่ม Delete
- **ลบหลายสาย:** Admin → Select All / กาเลือก → "🗑 Delete Selected (N)"
- **ลบ orphan cases:** Admin → ปุ่ม "🧹 ล้างเคสค้าง" (แสดงเมื่อมี orphan)

ลบไม่กู้คืนได้ — backup `data/smartvoice.db` ก่อนทำการลบจำนวนมาก

### 13.4 Recovery จาก processing ที่ค้าง

ถ้าแอปถูกปิดกลางทาง ระบบจะ:
1. ตอนเปิดแอปครั้งหน้า → reset สายที่ status='processing' นานเกิน `PROCESSING_STALE_MINUTES` (default 180) กลับเป็น 'uploaded'
2. แสดงในตาราง Admin → กด Process ใหม่ได้

### 13.5 Audit Trail

ทุกแถวใน `calls` มี:
- `uploaded_by` — ชื่อ login ของผู้ upload
- `uploaded_by_role` — role ขณะ upload
- `created_at` — เวลา upload
- `updated_at` — เวลา process เสร็จ

ใช้สำหรับ compliance / สืบสวน

---

## 14. Domain Knowledge ที่ระบบเข้าใจ

### 14.1 Brand Recognition

**ในเครือ Omazz:**
Omazz, Restonic, Lotus / โลตัส, Slumberland, Dunlopillo

**คู่แข่งที่ tracking:**
Sealy, Therapedic, King Koil, Simmons, Serta, Stearns & Foster, Synda, Satin

### 14.2 Anomaly Categories

ระบบแยก "anomaly" (ต้อง escalate) ออกจาก "negative sentiment" (ลูกค้าไม่พอใจปกติ)

| Category | ต้องเจอ keyword | Severity |
|---|---|---|
| **A1 ขู่ฟ้อง** | ฟ้อง, ทนาย, ดำเนินคดี, ศาล, แจ้งความ | high |
| **A2 ขู่ร้องเรียน** | สคบ., ร้องเรียน, กระทรวง, เพจ, สื่อ | high |
| **A3 ขอหัวหน้า** | ขอคุยกับหัวหน้า, ขอสายผู้จัดการ | medium |
| **A4 คำหยาบ** | คำด่าจริง (ไม่ใช่แค่น้ำเสียง) | low |
| **B Agent ผิดระเบียบ** | quote คำพูดจริงของ Agent | high |
| **C Safety / Legal** | เชื้อรา, สารเคมี, บาดเจ็บ, ค่าเสียหาย + จำนวนเงิน | medium-low |

ทุก flag ต้องมี **quote จาก transcript** ประกอบเป็นหลักฐาน

### 14.3 Common STT Errors

ที่ Whisper มักพลาดและระบบ post-process ช่วย:

| Whisper พูดผิด | ความจริงคือ |
|---|---|
| โอมาสนา / โอมาส | Omazz |
| โนโลตัส / โลตัสน้อย | โลตัส (Lotus) |
| ฟิวทู | Future (รุ่นที่นอน) |
| ที่โน่น / ทีเนี่ย | ที่นอน |
| Restonic ทับศัพท์ผิด | Restonic |
| เลขโทรศัพท์ไทย-อังกฤษปน | ใช้ phone regex ดึงตอน upload |

### 14.4 Speaker Cues (Thai-specific)

| Pattern | Role |
|---|---|
| `สวัสดีค่ะ [บริษัท]` | Agent (เปิดสาย) |
| `ทาง(บริษัท\|เรา\|เจ้าหน้าที่)` | Agent |
| `คุณลูกค้า` | Agent (เรียกอีกฝ่าย) |
| `พลอย\|พอย + verb` | Agent (พนักงานเรียกตัวเอง) |
| `พี่ + verb` (self-ref) | Customer |
| `(ลูก\|น้อง)` (vocative) | Customer (เรียกพนักงาน) |
| `ติดตามเรื่อง...ส่ง` | Customer |
| `ขอเลื่อนวัน` | Customer |

---

## 15. คำถามที่พบบ่อยและการแก้ปัญหา

### 15.1 ไม่เห็นเมนู Settings / Admin ใน sidebar

**สาเหตุ:** บัญชีที่ login อยู่เป็น role `Agent` หรือ `QA` ซึ่งไม่มีสิทธิ์เข้าสองหน้านี้ ระบบจึงซ่อนเมนูออกทั้งหมด (ดูตารางสิทธิ์ในหัวข้อ 5.3)

**แก้:** ให้ Admin เข้าหน้า **👤 จัดการผู้ใช้** แล้วเปลี่ยน role ของบัญชีนั้นเป็น `Supervisor` หรือ `Admin` จากนั้นให้ผู้ใช้ logout แล้ว login ใหม่

### 15.1.1 ลืมรหัสผ่าน

ให้ Admin เข้าหน้า **👤 จัดการผู้ใช้** → เลือกบัญชี → **รีเซ็ตรหัสผ่าน**

ถ้าลืมรหัสของบัญชี Admin ทุกบัญชี ให้เพิ่มบัญชีสำรองผ่าน `SMARTVOICE_USERS` ใน `.env` (หัวข้อ 5.2) แล้ว restart แอป

### 15.2 ประมวลผลไม่ได้ — "Ollama not ready"

**สาเหตุ:** Ollama service ไม่ทำงาน หรือไม่มีโมเดล

**แก้:**
```powershell
# ตรวจ Ollama service
curl http://localhost:11434/api/tags

# ถ้าไม่ตอบ ให้เริ่ม service
ollama serve

# ตรวจว่ามี model
ollama list

# ถ้าไม่มี ให้ pull
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
```

### 15.3 ประมวลผลไม่ได้ — "HF token missing"

**สาเหตุ:** ไม่ได้ตั้ง HF token หรือ token หมดอายุ

**แก้:** Settings → ใส่ HF token ใหม่ → Save → restart แอป

### 15.4 ประมวลผลแล้ว Speaker ผิดเพี้ยน

**สาเหตุที่เป็นไปได้:**
1. Audio quality แย่ (มี noise มาก)
2. มีคนพูดทับกัน
3. ไฟล์ mono ที่ผสม Agent + Customer ในช่องเดียว

**แก้:**
- ระบบมี deterministic rules ที่ overrride LLM อยู่แล้ว แต่ถ้ายังผิด ให้:
1. ตรวจ tagged transcript ในหน้า Admin
2. รายงาน issue พร้อม filename เพื่อ debug

### 15.5 Process แล้ว stuck ที่ "processing"

**สาเหตุ:** แอปถูกปิด/restart กลางทาง

**แก้:** ระบบจะ auto-reset เมื่อค้างเกิน `PROCESSING_STALE_MINUTES` (default 180 นาที) — รออัตโนมัติหรือแก้ใน DB ตรง

### 15.6 Dashboard โหลดช้ามาก

**สาเหตุ:** load limit ตั้งเป็น "ทั้งหมด" และ DB มีหลายพันแถว

**แก้:**
- Dashboard → Filter → "จำนวนสายที่โหลด" → เลือก 1,000 หรือน้อยกว่า
- ใช้ Date range filter เสริม

### 15.7 ใส่ Whisper model แล้ว backend/device ผิด

**สาเหตุ:** ระบบ auto-recommend ค่า แต่บางครั้ง user ต้องการ override

**แก้:** หลังเลือก model แล้ว ปรับ Backend/Device/Compute เองได้ ระบบจะเก็บค่าที่ user เลือกล่าสุดเสมอ

### 15.8 ไม่พบ GPU ทั้งที่เครื่องมี

**สาเหตุ:**
- CUDA driver ไม่ตรงกับ PyTorch
- PyTorch installed without CUDA support
- GPU ถูกใช้โดย process อื่น

**แก้:**
```powershell
# ตรวจ CUDA ใน PyTorch
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

ถ้า return `False` ให้ติดตั้ง PyTorch ที่มี CUDA:
```powershell
pip uninstall torch torchaudio
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 15.9 LLM ตอบ JSON ผิด → analysis ว่าง

**สาเหตุ:** Typhoon-8B บางครั้งตอบ malformed JSON

**แก้:**
- ระบบมี `extract_json()` ที่ทนทาน + fallback empty dict
- ถ้าเจอบ่อย ให้ re-process สายนั้น
- Workaround: ใช้ Demo mode ทดสอบว่า pipeline ปกติแน่นอน

### 15.10 ดู log ที่ไหน

`data/logs/smartvoice.log` (rotating — เก่ามาก backup เป็น `.log.1`, `.log.2`)

```powershell
# ดู log สด
Get-Content data\logs\smartvoice.log -Wait -Tail 50
```

### 15.11 Backup ข้อมูล

```powershell
# ปิดแอปก่อน
copy data\smartvoice.db data\backup\smartvoice_2026-05-27.db

# Backup ทั้ง data folder
robocopy data backup\data /MIR
```

### 15.12 Reset ข้อมูลทั้งหมด

```powershell
# ปิดแอปก่อน
del data\smartvoice.db
del /q data\raw_audio\*

# เปิดแอปใหม่ — ระบบจะสร้าง DB เปล่า
streamlit run Home.py
```

⚠️ ลบไม่กู้คืน — backup ก่อนทุกครั้ง

---

## 16. คำศัพท์

| คำ | ความหมาย |
|---|---|
| **STT** | Speech-to-Text — ถอดเสียงเป็นข้อความ |
| **Whisper** | OpenAI's STT model — ระบบใช้ทั้ง biodatlab Thai-tuned และ standard |
| **Diarization** | การแยกผู้พูด (who spoke when) |
| **Pyannote** | Library ทำ diarization |
| **LLM** | Large Language Model — ระบบใช้ Typhoon-8B ผ่าน Ollama |
| **Ollama** | Local LLM runtime — รัน LLM บนเครื่องของผู้ใช้ |
| **Typhoon-8B** | Thai-tuned LLM พัฒนาโดย SCB10X |
| **Topic** | หัวข้อหลักของสาย (9 หมวด) |
| **Topic Detail** | ประเภทความเสียหายภายในหมวด "แจ้งปัญหาสินค้า" (7 ประเภท) |
| **Agent QA** | การประเมินคุณภาพการบริการของ Agent (Politeness + Problem Solving) |
| **Evidence** | quote จาก transcript ที่สนับสนุนคะแนน QA |
| **Anomaly** | สายที่ต้อง escalate (ไม่ใช่แค่ negative sentiment) |
| **Case** | กลุ่มของหลายสายที่เป็นเรื่องเดียวกันของลูกค้าคนเดียวกัน |
| **Recency Short-circuit** | กฎที่ attach สายใหม่กับเคสเดิมถ้าโทรภายใน 4 ชม. |
| **Inbound** | สายลูกค้าโทรเข้า |
| **Outbound** | สายเจ้าหน้าที่โทรออก |
| **CDR** | Call Detail Record — รูปแบบ filename ที่ระบบของ Omazz สร้าง |
| **CT2** | CTranslate2 — quantization format สำหรับ faster-whisper |
| **VRAM** | GPU memory |
| **Audit Trail** | บันทึกใครทำอะไรเมื่อไหร่ |

---

## 17. ภาคผนวก

### 17.1 Environment Variables Reference

ทั้งหมดตั้งได้ใน `.env`:

| Variable | Default | คำอธิบาย |
|---|---|---|
| `MOCK_STT` | `false` | ใช้ transcript จำลอง (สำหรับ demo) |
| `WHISPER_MODEL` | `biodatlab/distill-whisper-th-large-v3` | Whisper model name |
| `WHISPER_BACKEND` | `transformers` | `transformers` / `faster-whisper` / `auto` |
| `WHISPER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `WHISPER_COMPUTE` | `auto` | `auto` / `float16` / `int8` |
| `HF_TOKEN` | _(empty)_ | HuggingFace token |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL ของ Ollama service |
| `OLLAMA_MODEL` | `scb10x/llama3.1-typhoon2-8b-instruct` | LLM model name |
| `CASE_RECENCY_HOURS` | `4.0` | window สำหรับ recency short-circuit |
| `SMARTVOICE_USERS` | _(empty)_ | บัญชีสำรองจากไฟล์ (ปกติใช้หน้า จัดการผู้ใช้ แทน) |
| `PROCESSING_STALE_MINUTES` | `180` | reset สายค้างเกิน N นาที |
| `DB_PATH` | `data/smartvoice.db` | path ของ SQLite |
| `MAX_FILE_SIZE_MB` | `100` | จำกัดขนาดไฟล์ upload |

### 17.2 CDR Filename Pattern

```
YYYYMMDDHHMMSS-CALLID.NNN-{AGENT|PHONE}-{PHONE|AGENT}-{Inbound|Outbound}.ext
```

| ส่วน | ขนาด | ตัวอย่าง |
|---|---|---|
| `YYYYMMDDHHMMSS` | 14 หลัก | `20251104173706` |
| `CALLID.NNN` | numeric + . + numeric | `1762252614.105999` |
| `AGENT` | 2-5 หลัก | `104` |
| `PHONE` | 10 หลักขึ้นต้น 0 | `0819979336` |
| `Inbound/Outbound` | literal | `Outbound` |
| `ext` | `.wav` หรือ `.mp3` | `.wav` |

**Outbound** Agent มาก่อน Phone:
```
20251104173706-1762252614.105999-104-0819979336-Outbound.wav
                                  ↑   ↑
                                Agent Phone
```

**Inbound** Phone มาก่อน Agent:
```
20251225134209-1766644826.135925-0631451550-104-Inbound.wav
                                  ↑          ↑
                                Phone      Agent
```

### 17.3 Database Schema สรุป

5 tables หลัก:

| Table | คอลัมน์สำคัญ |
|---|---|
| `calls` | id, filename, file_hash, transcript, summary, sentiment, topic, **topic_detail**, agent_performance, keywords, brand_mentions, platform_mentions, anomaly_*, status, customer_phone, case_id, uploaded_by, uploaded_by_role, created_at, updated_at |
| `customers` | id, first_name, last_name, phone (unique), email, gender, date_of_birth, address, subdistrict, district, city_province, country, postcode, created_at |
| `warranty_registrations` | id, registration_no (unique), customer_id (FK), category, brand, model, size, sku, serial_no, warranty_period_months, date_of_purchase, date_of_delivery, purchase_channel, order_number, expiry_date |
| `call_customer_links` | id, call_id (FK), customer_id (FK), warranty_id (FK), matched_by ('auto_phone' / 'manual') |
| `cases` | id, customer_id (FK), subject, status ('open'/'follow_up'/'closed') |

ดูรายละเอียดเต็มที่ [docs/database_design.md](database_design.md)

### 17.4 Performance Benchmark

ทดสอบกับ audio 3 นาที, ขนาด ~3 MB:

| Hardware | Mode | เวลาต่อสาย |
|---|---|---|
| RTX 3060 (12GB) + i7-12700 | GPU | ~25 วินาที |
| RTX 5070 Ti (16GB) + i9-13900 | GPU | ~12 วินาที |
| ไม่มี GPU + i7-12700 | CPU (int8) | ~3-5 นาที |
| ไม่มี GPU + ใน Demo Mode | Mock | ~3 วินาที |

### 17.5 ไฟล์เอกสารอื่นที่เกี่ยวข้อง

| ไฟล์ | เนื้อหา |
|---|---|
| [README.md](../README.md) | ภาพรวมโปรเจกต์ + tech stack |
| [SETUP.md](../SETUP.md) | คู่มือติดตั้งเชิงลึก + troubleshooting |
| [ONE_CLICK_RUN.md](../ONE_CLICK_RUN.md) | คู่มือ launcher สำหรับเครื่อง demo |
| [CHANGELOG.md](../CHANGELOG.md) | ประวัติ release ทั้งหมด |
| [docs/architecture.md](architecture.md) | สถาปัตยกรรม + data flow |
| [docs/database_design.md](database_design.md) | ER diagram + data dictionary ฉบับเต็ม |
| [docs/OMAZZ_RELEASE_CHECKLIST.md](OMAZZ_RELEASE_CHECKLIST.md) | Checklist ก่อนส่งมอบ |

### 17.6 ติดต่อทีมพัฒนา

สำหรับ:
- รายงาน bug
- ขอ feature ใหม่
- คำถามทาง technical

ติดต่อผ่านช่องทางที่ตกลงกับ Omazz

---

**จบเอกสาร**

> เอกสารนี้สอดคล้องกับ SmartVoice v1.2.0 — ฟีเจอร์อาจเปลี่ยนแปลงในเวอร์ชันถัดไป กรุณาตรวจ CHANGELOG.md สำหรับการเปลี่ยนแปลงล่าสุด
