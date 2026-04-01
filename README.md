# SmartVoice

AI-powered Call Center Analytics — transcribes Thai audio, diarizes speakers, and runs LLM quality analysis.

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | Streamlit (multi-page) |
| Database | SQLite 3 |
| STT (default) | `biodatlab/distill-whisper-th-large-v3` via `faster-whisper` / CTranslate2 |
| STT (alternative) | `transformers` หรือ `faster-whisper` — `large-v3` และโมเดลอื่น ๆ |
| Speaker Diarization | `pyannote/speaker-diarization-3.1` |
| LLM | Ollama — `scb10x/llama3.1-typhoon2-8b-instruct` |

## Project Structure

```
smartvoice/
├── app.py                        # Streamlit entry point (home page)
├── pages/                        # Streamlit multi-page
│   ├── 1_📤_Admin.py            # Upload & process audio files
│   ├── 2_📊_Dashboard.py        # Analytics dashboard
│   └── 3_👥_Customers.py        # Customer & warranty management
├── smartvoice/                   # Business logic package
│   ├── __init__.py               # Package init (loads .env)
│   ├── config.py                 # Centralized environment config
│   ├── ui_helpers.py             # Shared CSS, badges, processing launchers
│   ├── db.py                     # SQLite schema, migrations, CRUD
│   ├── file_manager.py           # Audio file saving + SHA-256 deduplication
│   ├── ollama_client.py          # Ollama/Typhoon LLM client
│   ├── prompts.py                # LLM prompt templates
│   ├── pipeline.py               # Full processing orchestration
│   ├── whisperx_client.py        # Backward-compat wrapper → stt/
│   └── stt/                      # Speech-to-Text sub-package
│       ├── __init__.py           # Public API: transcribe_diarized()
│       ├── audio.py              # Audio loading, resampling, noise reduction
│       ├── transcribe.py         # HF transformers + faster-whisper backends
│       ├── diarize.py            # Pyannote diarization + speaker assignment
│       └── orchestrator.py       # Ties audio → transcribe → diarize
├── scripts/
│   ├── seed_mock_data.py         # Seed mock customers + warranty data
│   └── generate_er_diagram.py    # Generate ER diagram PNG
├── data/                         # Runtime data (gitignored)
│   ├── models/                   # CTranslate2 converted models
│   ├── raw_audio/                # Uploaded audio files
│   └── smartvoice.db             # SQLite database (auto-created)
├── docs/
│   ├── database_design.md        # ER Diagram (Mermaid) + Data Dictionary
│   └── er_diagram.png            # ER Diagram PNG for reports
├── requirements.txt
├── .env.example
└── README.md
```

## Database Tables

| Table | คำอธิบาย |
|-------|----------|
| `calls` | บันทึกการโทร + ผลวิเคราะห์ AI |
| `customers` | ข้อมูลลูกค้า |
| `warranty_registrations` | ทะเบียนรับประกันสินค้า |
| `call_customer_links` | เชื่อมการโทรกับลูกค้า/warranty |

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
copy .env.example .env
```

แก้ไข `.env`:

```env
WHISPER_MODEL=biodatlab/distill-whisper-th-large-v3
WHISPER_BACKEND=transformers
WHISPER_DEVICE=auto
WHISPER_COMPUTE=auto
WHISPER_BEAM_SIZE=5
WHISPER_HOTWORDS=Restonic,Trade-in,หาดใหญ่,สุราษฎร์ธานี,อุทกภัย,ประกันโครงสร้าง,ภาคใต้,ทางห้าง,จัดโปร,แห้งแค่ข้างนอก,มิน่า
DENOISE_ENABLED=true
DENOISE_PROP_DECREASE=0.35
HF_TOKEN=your_huggingface_token   # ต้องขอสิทธิ์ pyannote/speaker-diarization-3.1
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
```

### 3. Start Ollama

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama serve
```

### 4. Seed mock data (optional)

```bash
.venv\Scripts\python.exe scripts/seed_mock_data.py
```

### 5. Run the app

```bash
streamlit run app.py
```

## STT Modes

| `MOCK_STT` | `WHISPER_BACKEND` | `WHISPER_MODEL` | HF_TOKEN | Mode |
|-----------|-------------------|-----------------|----------|------|
| `true` | any | any | any | Mock transcripts (fast, no GPU) |
| `false` | `transformers` | `biodatlab/...` | set | Recommended for Thai accuracy-first transcription + pyannote diarization |
| `false` | `faster-whisper` | `large-v3` หรือ native CT2 model | set | faster-whisper + pyannote diarization |
| `false` | `auto` | any | set | Auto-selects a backend, but for `biodatlab/...` accuracy work prefer `transformers` |
| `false` | any | any | empty | Transcription only (all "Speaker 0") |

## Processing Pipeline

```
Audio (.wav/.mp3)
    ↓ load + resample 16 kHz     → numpy array
    ↓ noisereduce                 → cleaned audio
    ↓ Whisper (HF or FW)         → word-level timestamps
    ↓ pyannote 3.1               → speaker labels per word
    ↓ group by speaker            → Agent / Customer segments
    ↓ Typhoon2 8B (LLM)          → JSON analysis
    ↓ SQLite                     → Streamlit UI
```

## LLM Output Fields

| Field | Description |
|-------|-------------|
| `speaker_mapping` | SPEAKER_XX → Agent/Customer |
| `topic` | หัวข้อหลักที่ลูกค้าติดต่อ |
| `customer_sentiment` | positive / neutral / negative |
| `summary` | สรุปบทสนทนา 1-2 ประโยค |
| `agent_performance` | politeness, problem_solving, overall_score (1-10) |
| `keywords` | คำสำคัญในบทสนทนา |
| `brand_mentions` | แบรนด์ที่พูดถึง |
| `platform_mentions` | แพลตฟอร์มที่พูดถึง |
| `anomaly_detected` | true / false |
| `anomaly_reason` | รายละเอียดความผิดปกติ |
