# SmartVoice one-click run guide

คู่มือนี้ใช้ตอนส่งโปรเจคให้เครื่องอื่นหรือเตรียมเครื่อง demo แบบเร็วที่สุด

## Minimum requirements

- Windows 10/11, macOS, หรือ Linux
- Internet access ในการรันครั้งแรก
- พื้นที่ว่างอย่างน้อย 10 GB สำหรับ Python packages และ AI models

บน Windows: `run.bat` สามารถเสนอติดตั้ง Python 3.11 ให้อัตโนมัติได้ถ้ายังไม่มี
สำหรับ macOS/Linux: ติดตั้ง Python 3.10 หรือ 3.11 ก่อน

สำหรับ Real AI mode ยังต้องมี:

- Ollama
- HuggingFace token ที่เข้าถึง `pyannote/speaker-diarization-3.1` และ `pyannote/segmentation-3.0`

ก่อนส่งโปรเจคให้ภายนอก ให้ทำตาม [`docs/OMAZZ_RELEASE_CHECKLIST.md`](docs/OMAZZ_RELEASE_CHECKLIST.md)

## Windows

1. ดาวน์โหลดหรือ clone โปรเจค
2. ดับเบิลคลิก `run.bat`
3. ตอบรับ prompt ติดตั้ง Python 3.11 ถ้าเครื่องยังไม่มี Python 3.10 หรือ 3.11

รอบแรกจะใช้เวลาหลายนาที (อาจติดตั้ง Python, Python packages และ AI models)
หลังจากนั้น ดับเบิลคลิก `run.bat` เพื่อเปิดแอปได้เลย

รอบแรก launcher จะ:

- สร้าง `.venv`
- ติดตั้ง dependencies
- สร้าง `.env`
- ตรวจ Python / PyTorch / CUDA / Ollama
- เสนอการติดตั้ง CUDA-enabled PyTorch, Ollama, และโมเดลที่ขาด
- เปิดแอปที่ `http://localhost:8501`

## macOS / Linux

```bash
chmod +x run.sh
./run.sh
```

## Real AI mode

หลัง launcher สร้าง `.env` แล้ว ให้ตั้งอย่างน้อย:

```env
MOCK_STT=false
HF_TOKEN=hf_your_token_here
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
```

ติดตั้งโมเดล Ollama ครั้งเดียว:

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
```

เปิดหน้า Home แล้วขยาย `Deployment readiness` เพื่อตรวจสถานะระบบ

## Demo mode

ถ้าเครื่องไม่มี GPU หรือยังไม่มี HuggingFace access:

1. Login ใน sidebar
2. เข้า `Settings`
3. เลือก `Use Demo Laptop Mode`
4. Restart แอป

ในโหมดนี้ระบบยังเปิดใช้งาน UI และ flow upload ได้ โดยใช้ mock transcript แทน STT จริง

## Authentication

ถ้าต้องการ password login แทน demo/audit login:

```bash
python scripts/make_password_hash.py admin Admin
```

จากนั้นนำผลลัพธ์ไปใส่ใน `.env`:

```env
SMARTVOICE_USERS=admin|Admin|pbkdf2_sha256$...
```

## Packaging options

ก่อน zip โปรเจค ให้ตัดสิ่งเหล่านี้ออก:

- `.venv`
- `.git`
- `.env`
- `data/raw_audio`
- `data/models`
- `data/logs`
- local DB เช่น `data/smartvoice.db`
- `smartvoice.egg-info` และ `*.egg-info`
- temporary reports เช่น `_anomaly_report.txt`

ถ้าต้องการ installer แบบ self-contained จริง ๆ ให้พิจารณา Docker หรือ PyInstaller ภายหลัง โดย Docker มักเสถียรกว่าสำหรับ stack ที่มี Torch, pyannote, CUDA, และ Ollama
