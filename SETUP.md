# SmartVoice — วิธีติดตั้งและเปิดโปรเจค

## สิ่งที่ต้องมีก่อน

| รายการ | ลิงก์ |
|--------|-------|
| Python 3.10+ | https://www.python.org/downloads/ |
| NVIDIA GPU + CUDA 12.x | https://developer.nvidia.com/cuda-downloads |
| Ollama | https://ollama.com |
| HuggingFace Token | https://huggingface.co/settings/tokens |

> **HF Token** ต้องขอ access โมเดล [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) ด้วย

---

## ขั้นตอนติดตั้ง

### 1. สร้าง Virtual Environment

```bash
python -m venv .venv
```

### 2. เปิดใช้งาน venv

```bash
# Windows (PowerShell)
.venv\Scripts\activate

# Windows (CMD)
.venv\Scripts\activate.bat
```

### 3. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 4. แก้ dependency ที่มีปัญหา (สำคัญ)

```bash
pip uninstall torchcodec -y
pip install torchaudio==2.10.0+cu128 --index-url https://download.pytorch.org/whl/cu128 --no-deps
```

### 5. ติดตั้งโปรเจคแบบ editable (สำหรับคำสั่ง `smartvoice`)

```bash
pip install -e . --no-deps
```

### 6. ตั้งค่า `.env`

```bash
copy .env.example .env
```

เปิดไฟล์ `.env` แล้วใส่ค่า:

```env
WHISPER_MODEL=biodatlab/distill-whisper-th-large-v3
HF_TOKEN=hf_xxxxxxxxxx    # ใส่ token จาก HuggingFace
```

ค่าอื่น ๆ ใช้ default ได้เลย

### 7. ติดตั้งและรัน Ollama

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve
```

---

## วิธีเปิดโปรเจค

เลือกวิธีใดวิธีหนึ่ง:

### วิธี 1 — ดับเบิลคลิก (ง่ายสุด)

ดับเบิลคลิกไฟล์ **`run.bat`** ในโฟลเดอร์โปรเจค

### วิธี 2 — พิมพ์คำสั่งใน Terminal

```bash
.venv\Scripts\activate
streamlit run app.py
```

### วิธี 3 — ใช้คำสั่ง smartvoice

```bash
.venv\Scripts\smartvoice
```

---

เปิด Browser ไปที่ **http://localhost:8501** แล้วเริ่มใช้งานได้เลย

## โครงสร้างหน้าเว็บ

| หน้า | หน้าที่ |
|------|---------|
| **Admin** | อัปโหลดไฟล์เสียง, สั่ง Process, ดูสถานะ |
| **Dashboard** | กราฟ Sentiment, Intent, สถิติรวม |
| **Customers** | จัดการลูกค้า, Warranty, เชื่อมกับการโทร |

---

## การรันครั้งถัดไป

ไม่ต้องติดตั้งใหม่ — แค่:

1. เปิด Ollama (`ollama serve`)
2. ดับเบิลคลิก `run.bat` หรือพิมพ์ `streamlit run app.py`
