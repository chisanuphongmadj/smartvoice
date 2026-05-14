# SmartVoice — คู่มือติดตั้งและเปิดใช้งาน

คู่มือนี้สำหรับ **นักพัฒนา / IT** ติดตั้งระบบครั้งแรก
สำหรับ **ผู้ใช้งานทั่วไป** ให้ดู [`docs/user_manual.md`](docs/user_manual.md)

---

## 📋 สิ่งที่ต้องเตรียม

| รายการ | เวอร์ชัน / ข้อมูล | ลิงก์ |
|--------|-------------------|-------|
| **Python** | 3.10 หรือ 3.11 (แนะนำ 3.11) | https://www.python.org/downloads/ |
| **NVIDIA GPU + CUDA** | CUDA 12.x (เร็วกว่ามาก) — CPU ได้แต่ช้า | https://developer.nvidia.com/cuda-downloads |
| **Ollama** | 0.3.0+ | https://ollama.com |
| **HuggingFace Token** | ต้อง accept license 2 models | https://huggingface.co/settings/tokens |
| **Disk space** | ~10 GB (โมเดล + audio cache) | — |

### HuggingFace Token — ต้องกด Accept License

ก่อนสร้าง token ให้เข้าไป **ยอมรับเงื่อนไข** 2 โมเดลนี้ก่อน:

1. [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
2. [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

จากนั้นสร้าง **Read token** ที่ https://huggingface.co/settings/tokens

---

## 🚀 ขั้นตอนติดตั้ง

### 1. Clone และเข้าโฟลเดอร์

```bash
git clone <repo-url> smartvoice
cd smartvoice
```

### 2. สร้างและเปิด Virtual Environment

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 4. แก้ torchaudio ให้ตรงกับ CUDA (สำคัญถ้ามี GPU)

```bash
pip uninstall torchcodec -y
pip install torchaudio==2.10.0+cu128 --index-url https://download.pytorch.org/whl/cu128 --no-deps
```

> เปลี่ยน `cu128` ตามเวอร์ชัน CUDA ที่ติดตั้ง — ถ้าไม่มี GPU ข้ามขั้นนี้ แล้วตั้ง `MOCK_STT=true` ใน `.env`

### 5. ติดตั้งโปรเจคแบบ editable

```bash
pip install -e . --no-deps
```

### 6. ตั้งค่า `.env`

```powershell
# Windows
copy .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

เปิดไฟล์ `.env` ใส่อย่างน้อย:

```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxxx    # จาก HuggingFace (จำเป็น)
WHISPER_MODEL=biodatlab/distill-whisper-th-large-v3
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
```

**สำหรับทดลองระบบแบบไม่ต้อง GPU:** ตั้ง `MOCK_STT=true` เพื่อข้าม STT จริง ใช้ transcript ตัวอย่างแทน

### 7. ติดตั้งและรัน Ollama

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve                     # เปิด Ollama server ใน terminal แยก
```

### 8. (Optional) Seed Mock Data สำหรับทดลอง

ถ้ายังไม่มี data ของจริง รันคำสั่งนี้เพื่อใส่ลูกค้าและ warranty ตัวอย่าง:

```bash
python scripts/seed_mock_data.py
```

---

## ▶ วิธีเปิดโปรแกรม

### Windows

ดับเบิลคลิก **`run.bat`** หรือพิมพ์:

```powershell
.venv\Scripts\activate
streamlit run app.py
```

### Linux / macOS

```bash
chmod +x run.sh    # ครั้งแรกเท่านั้น
./run.sh
```

### หรือใช้คำสั่ง `smartvoice`

```bash
.venv\Scripts\smartvoice     # Windows
.venv/bin/smartvoice         # Linux/Mac
```

เปิดเบราว์เซอร์ไปที่ **http://localhost:8501**

---

## 🗂 โครงสร้างหน้าเว็บ

| หน้า | หน้าที่ |
|------|---------|
| 🏠 **Home** | ภาพรวม, stats เร็ว |
| 📤 **Admin** | อัปโหลดไฟล์เสียง, สั่ง Process, ดูสถานะ, จัดการเคส |
| 📊 **Dashboard** | กราฟ Sentiment, Intent, Brand, Agent Performance |
| 👥 **Customers** | ค้นหาลูกค้า, Warranty lookup |

---

## 🔧 Troubleshooting

### ❌ `HF_TOKEN` invalid / 401 Unauthorized
- ตรวจว่าได้กด **Accept** บนหน้า model แล้วทั้ง 2 รุ่น (ดู §1)
- Token ต้องเป็น **Read** หรือ **Write** — ไม่ใช่ fine-grained ที่จำกัด
- รีสตาร์ท Streamlit หลังแก้ `.env`

### ❌ CUDA out of memory
- ลดไฟล์ audio ให้สั้นลง หรือ
- ตั้ง `WHISPER_COMPUTE=int8` ใน `.env` (ใช้ memory น้อยกว่า)
- ลดไฟล์ที่ process พร้อมกันเหลือทีละ 1

### ❌ Ollama: `connection refused`
- ตรวจว่า `ollama serve` รันอยู่ (ต้องเปิด terminal แยก)
- ตรวจว่าไม่มีโปรแกรมอื่นใช้ port 11434
- ดึงโมเดลอีกครั้ง: `ollama pull scb10x/llama3.1-typhoon2-8b-instruct`

### ❌ `No module named 'smartvoice'`
- รัน `pip install -e . --no-deps` อีกครั้งใน venv ที่ activate อยู่

### ❌ Upload ไฟล์แล้วขึ้น "magic bytes ไม่ตรง"
- ไฟล์อาจเสียหาย — ลอง convert ด้วย ffmpeg:
  ```bash
  ffmpeg -i input.mp3 -ar 16000 output.wav
  ```

### 📋 ดู Log
- ไฟล์ log ถูกเก็บที่ `data/logs/smartvoice.log` (หมุนเวียนที่ 5 MB, เก็บ 3 ไฟล์)
- ปรับระดับ log: ตั้ง `SMARTVOICE_LOG_LEVEL=DEBUG` ใน `.env`

---

## 🔁 การรันครั้งถัดไป

หลังติดตั้งเสร็จครั้งแรก ครั้งต่อ ๆ ไปแค่:

```bash
# 1. เปิด Ollama ใน terminal แยก
ollama serve

# 2. เปิดโปรแกรม
run.bat           # Windows
./run.sh          # Linux/Mac
```

---

## 📚 เอกสารอื่น

- [`README.md`](README.md) — ภาพรวมโปรเจค
- [`docs/user_manual.md`](docs/user_manual.md) — คู่มือผู้ใช้ธุรกิจ
- [`docs/architecture.md`](docs/architecture.md) — โครงสร้างระบบ + Data Flow
- [`docs/database_design.md`](docs/database_design.md) — ER Diagram + Data Dictionary
- [`CHANGELOG.md`](CHANGELOG.md) — ประวัติการเปลี่ยนแปลง
