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
CASE_RECENCY_HOURS=4.0
PROCESSING_STALE_MINUTES=180
SMARTVOICE_USERS=
```

หมายเหตุ:

- `MOCK_STT=true` ใช้โหมด demo โดยไม่เรียก STT จริง
- `CASE_RECENCY_HOURS` ใช้ auto-attach สายใหม่เข้ากับเคสเปิดล่าสุดของลูกค้าคนเดิม
- `PROCESSING_STALE_MINUTES` ใช้ reset งานที่ค้างในสถานะ `processing` หลังแอปถูกปิดกลางทาง
- `SMARTVOICE_USERS` ถ้าว่าง ระบบจะใช้ demo/audit login; ถ้าตั้งค่าแล้วจะเปิด login แบบ password

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

| หน้า | หน้าที่ |
|------|---------|
| Home | สรุปจำนวนสาย + `Deployment readiness` |
| Admin | Upload, process, ค้นหา/กรองสาย, bulk delete, เชื่อมลูกค้า, จัดการ/รวมเคส |
| Dashboard | KPI, charts, anomaly, agent performance พร้อมหลักฐานคะแนน QA, case summary |
| Customers | ดูลูกค้า, warranty, เคส, และสายที่เชื่อมไว้ |
| Settings | preset Demo / Real AI, ปรับ model config, ดู readiness checks |

หน้า `Settings` ต้อง login ก่อน และจำกัดให้ `Admin` หรือ `Supervisor`

---

## ตั้งค่า Authentication

สร้าง hash:

```powershell
python scripts/make_password_hash.py admin Admin
```

นำค่าที่ได้ไปใส่ใน `.env`:

```env
SMARTVOICE_USERS=admin|Admin|pbkdf2_sha256$...
```

รองรับหลาย user โดยคั่นด้วย `;`

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

### ดู log

- ไฟล์อยู่ที่ `data/logs/smartvoice.log`
- ตั้ง `SMARTVOICE_LOG_LEVEL=DEBUG` ใน `.env` เมื่อต้องการรายละเอียดเพิ่ม

---

## Test Suite

```powershell
& ".venv\Scripts\python.exe" -m pytest tests\ --ignore=tests\test_config.py -q
```

สถานะล่าสุดที่ยืนยันแล้ว: `145 passed` (ทดสอบเมื่อ 2026-05-20)

---

## เอกสารที่เกี่ยวข้อง

- [`README.md`](README.md)
- [`ONE_CLICK_RUN.md`](ONE_CLICK_RUN.md)
- [`docs/user_manual.md`](docs/user_manual.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/database_design.md`](docs/database_design.md)
- [`docs/OMAZZ_RELEASE_CHECKLIST.md`](docs/OMAZZ_RELEASE_CHECKLIST.md)
- [`CHANGELOG.md`](CHANGELOG.md)
