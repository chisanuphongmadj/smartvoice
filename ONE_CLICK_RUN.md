# SmartVoice one-click run guide

This project can be shared with another machine as a normal Git checkout or a ZIP file.
The launcher will create the virtual environment, install Python packages, copy `.env.example`
to `.env`, and open Streamlit automatically.

## Minimum requirements

- Windows 10/11, macOS, or Linux
- Internet access on the first run
- 10 GB or more free disk space for Python packages and AI models

On Windows, `run.bat` can offer to install Python 3.11 automatically if no supported
Python is available yet. On macOS/Linux, install Python 3.10 or 3.11 first.

For real AI analysis, also install:

- Ollama: https://ollama.com
- HuggingFace token with access to `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`

Before sending the project to another company, follow `docs/OMAZZ_RELEASE_CHECKLIST.md`.

## Windows

1. Download or clone this project.
2. Double-click `run.bat`.
3. Accept the Python 3.11 installer prompt if the machine does not already have
   Python 3.10 or 3.11.

First run can take several minutes because it may install Python, Python packages,
and AI models.
After that, double-clicking `run.bat` starts the app.

`run.bat` also prints a local environment check on startup. If it detects an NVIDIA GPU
but the current virtual environment cannot use CUDA, it prints the recommended PyTorch
reinstall commands for that machine and asks whether to install the recommended CUDA
build immediately. If Ollama or the configured Ollama model is missing, it also asks
whether to install Ollama for Windows and download the required model.

## macOS / Linux

```bash
chmod +x run.sh
./run.sh
```

## Real AI mode

After the first run creates `.env`, edit it and set:

```env
HF_TOKEN=hf_your_token_here
OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct
MOCK_STT=false
```

Then install the Ollama model once:

```bash
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
```

## Demo mode

For a machine without GPU or without HuggingFace access:

1. Open the app.
2. Go to `Settings`.
3. Click `Use Demo Laptop Mode`.
4. Restart with `run.bat`.

The app will still open, and uploads can be tested with mock transcripts.

## Packaging options

For the easiest handoff to non-technical users:

1. Zip the project folder, excluding `.venv`, `.git`, `.env`, `data/raw_audio`, `data/models`, `data/logs`, and local DB files.
2. Ask the user to unzip it.
3. Ask them to double-click `run.bat`.

For a fully self-contained installer, use Docker or PyInstaller later. Docker is usually more reliable
for this project because Torch, pyannote, CUDA, and Ollama dependencies are heavy.
