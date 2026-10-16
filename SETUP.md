# SmartVoice — คู่มือติดตั้งและเปิดใช้งาน

คู่มือนี้สำหรับ **นักพัฒนา / IT** ที่ติดตั้งระบบครั้งแรก
สำหรับผู้ใช้งานธุรกิจ ให้ดู [`docs/user_manual.md`](docs/user_manual.md)

---

## สิ่งที่ต้องเตรียม

| รายการ | รายละเอียด |
|--------|------------|
| Python | 3.10 หรือ 3.11 |
| Disk space | ประมาณ 10 GB ขึ้นไปสำหรับ package, model, และ cache |
| Ollama | จำเป็นสำหรับ LLM analysis |
| HuggingFace token | จำเป็นสำหรับ pyannote diarization ในโหมด Real AI |
| NVIDIA GPU | ไม่บังคับ แต่ช่วยให้ STT เร็วขึ้นมาก |

ก่อนใช้ `HF_TOKEN` ให้กด accept license ของ:

1. `pyannote/speaker-diarization-3.1`
2. `pyannote/segmentation-3.0`

---

## วิธีติดตั้งที่แนะนำบน Windows

### 1. Clone โปรเจค

```bash
git clone <repo-url> smartvoice
```

### 2. ใช้ launcher ครั้งแรก

```powershell
run.bat
```

`run.bat` จะทำให้ครบชุด:

- สร้าง `.venv`
- สร้าง `.env` จาก `.env.example`
- ติดตั้ง dependencies และติดตั้ง package แบบ editable
- ตรวจ Python, PyTorch, CUDA, Ollama
- เสนอคำสั่งติดตั้ง PyTorch CUDA build ที่เหมาะกับเครื่อง
- เสนอการติดตั้ง Ollama และดาวน์โหลดโมเดลถ้ายังไม่มี
- เปิดแอปที่ `http://localhost:8501`

ถ้าต้องการติดตั้งเองแบบ manual ให้ใช้ขั้นตอนถัดไป

---

## วิธีติดตั้งแบบ Manual

### 1. สร้าง virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 2. ติดตั้ง dependency และ package

```powershell
pip install -r requirements.txt
pip install -e . --no-deps
```

> อัปเดตจากเวอร์ชันก่อน: รัน `pip install -r requirements.txt` อีกครั้ง — มีแพ็กเกจใหม่ `openpyxl` (นำเข้า SO จาก Excel), `fpdf2` และ `uharfbuzz` (รายงาน PDF ภาษาไทย) ฐานข้อมูลเดิมจะถูกเพิ่มตาราง/คอลัมน์ใหม่ให้เองตอนเปิดแอป ข้อมูลเดิมไม่เปลี่ยน

### 3. ตั้งค่า `.env`

```powershell
copy .env.example .env
```

ค่าหลักที่ควรรู้:

```env
WHISPER_MODEL=biodatlab/distill-whisper-th-large-v3
WHISPER_BACKEND=transformers
WHISPER_DEVICE=auto
WHISPER_COMPUTE=auto
MOCK_STT=false
HF_TOKEN=hf_xxxxxxxxxxxxxxxxx
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
OLLAMA_NUM_CTX=12288
CASE_RECENCY_HOURS=4.0
PROCESSING_STALE_MINUTES=180
SMARTVOICE_USERS=
DISCORD_WEBHOOK_URL=
REPORT_FONT_PATH=
```

หมายเหตุ:

- `MOCK_STT=true` ใช้โหมด demo โดยไม่เรียก STT จริง
- `CASE_RECENCY_HOURS` ใช้ auto-attach สายใหม่เข้ากับเคสเปิดล่าสุดของลูกค้าคนเดิม
- `PROCESSING_STALE_MINUTES` ใช้ reset งานที่ค้างในสถานะ `processing` หลังแอปถูกปิดกลางทาง
- `OLLAMA_NUM_CTX` ความยาว context ของ LLM (ค่าตั้งต้นของ Ollama บน GPU 16 GB คือ 4096 ซึ่งตัด prompt วิเคราะห์ทิ้ง) — ไม่ต้องใส่ก็ได้ ระบบใช้ 12288
- `DISCORD_WEBHOOK_URL` แจ้งเตือนเข้า Discord เมื่อมีคนรับ/คืน/ปิดเคส — สร้างใน Discord: ตั้งค่าช่อง → Integrations → Webhooks → Copy Webhook URL; ว่าง = ไม่ส่ง (ตั้งจากหน้า Settings ได้ และถือเป็นความลับ)
- `REPORT_FONT_PATH` ฟอนต์ภาษาไทย (.ttf) สำหรับรายงาน PDF — ว่างไว้ได้บน Windows (ใช้ Tahoma / Leelawadee อัตโนมัติ); บน Linux ติดตั้ง `fonts-thai-tlwg` หรือ Noto Sans Thai
- `SMARTVOICE_USERS` ปล่อยว่างได้ — บัญชีผู้ใช้ปกติเก็บในฐานข้อมูลและจัดการผ่านหน้า `จัดการผู้ใช้` (ดูหัวข้อ Authentication)

### 4. เปิด Ollama

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve
```

### 5. Seed mock data ถ้าต้องการ

```powershell
python scripts/seed_mock_data.py
```

### 6. เปิดแอป

```powershell
streamlit run Home.py
```

หรือใช้:

```powershell
.venv\Scripts\smartvoice
```

---

## หน้าเว็บที่มีตอนนี้

| หน้า (เมนู) | หน้าที่ |
|------|---------|
| หน้าแรก | "งานที่รอคุณ" — เคสที่ยังไม่มีคนรับ, เคสของฉัน, สายผิดปกติรุนแรง + สถานะสาย; ตรวจความพร้อมระบบ (Admin/Supervisor) |
| Dashboard — ภาพรวม / คีย์เวิร์ด แบรนด์ ช่องทาง / สายที่ผิดปกติ / ผลงานพนักงาน / รายการสาย | 5 หน้าใช้ตัวกรองร่วมกัน; ปุ่ม **ส่งออกรายงาน** (PDF, CSV สรุป, CSV รายการสาย) ทุกหน้า |
| จัดการเคส | รับเคส (คนอื่นแย่งไม่ได้), เปลี่ยนสถานะ/ปิดเคส, แจ้ง Discord |
| ลูกค้าและการรับประกัน | คลิกแถวเพื่อดูลูกค้า: ทะเบียนรับประกัน + หลักฐานการซื้อ, ใบสั่งขาย, เคส, สาย |
| ใบสั่งขาย (SO) | ค้นหา/ดูใบสั่งขาย; Admin นำเข้า Excel/CSV, เพิ่ม/แก้ไข, ซ่อน/กู้คืน |
| เพิ่ม/แก้ไขข้อมูลลูกค้า | เพิ่ม / แก้ไข / ซ่อน / กู้คืน ลูกค้าและทะเบียนรับประกัน, ยกเลิกทะเบียน (Cancel), แนบหลักฐานการซื้อ |
| อัปโหลดและประมวลผลเสียง | Upload, process, ค้นหา/กรองสาย, bulk delete, เชื่อมลูกค้า, จัดการ/รวมเคส |
| ประวัติการใช้งาน | audit log ทั้งระบบ — กรอง ค้นหา ดาวน์โหลด CSV |
| ตั้งค่าระบบ | preset Demo / Real AI, ปรับ model config, Discord webhook, ดู readiness checks |
| จัดการผู้ใช้ | เพิ่มบัญชี / เปลี่ยนบทบาท / เปิด-ปิดใช้งาน — ตั้งหรือรีเซ็ตรหัสผ่านของคนอื่นไม่ได้ และไม่มีการลบบัญชีถาวร |

ต้อง login ก่อนจึงจะเห็นหน้าใด ๆ และ sidebar จะแสดงเฉพาะหน้าที่ role นั้นมีสิทธิ์:

| Role | หน้าที่เข้าได้ |
|---|---|
| `Admin` | ทุกหน้า |
| `Supervisor` | ทุกหน้า ยกเว้น `เพิ่ม/แก้ไขข้อมูลลูกค้า` และ `จัดการผู้ใช้` (ดู SO ได้ แต่นำเข้า/แก้ไขไม่ได้) |
| `QA`, `Agent` | หน้าแรก, Dashboard ทั้ง 5 หน้า, จัดการเคส, ลูกค้าและการรับประกัน, ใบสั่งขาย (ดูอย่างเดียว) — QA รับเคสไม่ได้ |

---

## ตั้งค่า Authentication

เปิดแอปครั้งแรก ระบบจะสร้างบัญชีผู้ดูแลให้อัตโนมัติ:

| Username | Password |
|---|---|
| `admin` | `admin1234` |

ขั้นตอนหลัง login ครั้งแรก:

1. sidebar → กล่องบัญชี → `เปลี่ยนรหัสผ่าน` (คำเตือนใน sidebar จะหายไปเมื่อเปลี่ยนแล้ว)
2. sidebar → `จัดการผู้ใช้` → เพิ่มบัญชีพนักงานพร้อมกำหนด role

รหัสผ่านทั้งหมดถูกเก็บเป็น PBKDF2-SHA256 ในตาราง `users` ไม่มีการเก็บ plaintext

ผู้ดูแลระบบ**ตั้งหรือรีเซ็ตรหัสผ่านของพนักงานไม่ได้** — รหัสผ่านเป็นของเจ้าของบัญชี ถ้าพนักงานลืมรหัส ให้ปิดใช้งานบัญชีเดิมแล้วสร้างบัญชีใหม่ (ดู `docs/user_manual.md` หัวข้อ 15.1.1) ทุกการจัดการบัญชีและการเข้าสู่ระบบถูกบันทึกในหน้า `ประวัติการใช้งาน`

### บัญชีสำรองจากไฟล์ (ไม่บังคับ)

ถ้าต้องการบัญชีกู้ระบบที่ไม่ขึ้นกับฐานข้อมูล ให้สร้าง hash:

```powershell
python scripts/make_password_hash.py admin Admin
```

นำค่าที่ได้ไปใส่ใน `.env`:

```env
SMARTVOICE_USERS=admin|Admin|pbkdf2_sha256$...
```

รองรับหลาย user โดยคั่นด้วย `;` — ระบบจะตรวจบัญชีในฐานข้อมูลก่อน แล้วค่อยตกมาที่ `.env`

---

## GPU / CUDA

บน Windows ให้รัน `run.bat` ก่อน เพราะ launcher จะตรวจ CUDA และแนะนำ wheel tag ที่ตรงกับเครื่องให้เอง

ถ้าจะติดตั้งเอง ตัวอย่างรูปแบบคำสั่งคือ:

```powershell
.venv\Scripts\python.exe -m pip uninstall -y torch torchvision torchaudio
.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

เปลี่ยน `cu128` ให้ตรงกับ CUDA ที่เครื่องรองรับ

---

## Troubleshooting

### `HF_TOKEN` invalid / 401

- ตรวจว่า accept license ของ pyannote ทั้ง 2 model แล้ว
- รีสตาร์ทแอปหลังแก้ `.env`

### Ollama ยังไม่พร้อม

- เปิด `ollama serve`
- ตรวจว่ามีโมเดลที่ตั้งใน `OLLAMA_MODEL`
- หน้า Home และ Settings จะแสดง readiness checks ให้ดูได้ทันที

### CUDA ใช้ไม่ได้

- รัน `run.bat` เพื่อดู environment check
- ตรวจ `WHISPER_DEVICE`
- ถ้าเครื่องยังไม่พร้อม ใช้ `MOCK_STT=true` ชั่วคราว

### Upload แล้วไฟล์ไม่ผ่าน

- รองรับเฉพาะ `.wav` และ `.mp3`
- ไฟล์ต้องไม่เกิน 100 MB
- ถ้าเจอ `magic bytes ไม่ตรง` ให้ตรวจไฟล์หรือแปลงใหม่ด้วย `ffmpeg`

### งานค้างในสถานะ processing

- ระบบจะ reset งานเก่าที่ค้างเกิน `PROCESSING_STALE_MINUTES` ตอนเปิดหน้าใหม่
- ถ้าต้องการปิด behavior นี้ ให้ตั้ง `PROCESSING_STALE_MINUTES=0`

### ปุ่ม "รายงาน PDF" กดไม่ได้

- แปลว่าเครื่องไม่มีฟอนต์ภาษาไทย (Windows มี Tahoma อยู่แล้ว — มักเจอบน Linux)
- ติดตั้งฟอนต์ไทย หรือตั้ง `REPORT_FONT_PATH=` เป็น path ของไฟล์ `.ttf` ที่มีภาษาไทย แล้วรีสตาร์ทแอป
- ไฟล์ CSV ยังดาวน์โหลดได้ตามปกติ

### ดู log

- ไฟล์อยู่ที่ `data/logs/smartvoice.log`
- ตั้ง `SMARTVOICE_LOG_LEVEL=DEBUG` ใน `.env` เมื่อต้องการรายละเอียดเพิ่ม

---

## Test Suite

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

สถานะล่าสุดที่ยืนยันแล้ว: `492 passed` (ทดสอบเมื่อ 2026-10-16)

---

## เอกสารที่เกี่ยวข้อง

- [`README.md`](README.md)
- [`ONE_CLICK_RUN.md`](ONE_CLICK_RUN.md)
- [`docs/user_manual.md`](docs/user_manual.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/database_design.md`](docs/database_design.md)
- [`docs/OMAZZ_RELEASE_CHECKLIST.md`](docs/OMAZZ_RELEASE_CHECKLIST.md)
- [`CHANGELOG.md`](CHANGELOG.md)
