#!/usr/bin/env bash
# SmartVoice launcher for Linux / macOS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo
echo "========================================"
echo "  SmartVoice - one-click launcher"
echo "========================================"
echo

PY_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo "Python was not found. Install Python 3.10 or 3.11 first."
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment..."
    "$PY_CMD" -m venv .venv
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

VENV_PY=".venv/bin/python"

echo "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip

echo "Installing SmartVoice dependencies. This can take a while on first run..."
"$VENV_PY" -m pip install -r requirements.txt

echo "Installing SmartVoice package..."
"$VENV_PY" -m pip install -e . --no-deps

if command -v ollama >/dev/null 2>&1; then
    echo "Starting Ollama in the background if it is not already running..."
    ollama serve >/tmp/smartvoice-ollama.log 2>&1 &
else
    echo
    echo "NOTE: Ollama is not installed or not in PATH."
    echo "Install Ollama from https://ollama.com for real LLM analysis."
fi

echo
echo "Opening SmartVoice at http://localhost:${PORT:-8501}"
echo "Keep this terminal open while using the app."
echo

if command -v open >/dev/null 2>&1; then
    open "http://localhost:${PORT:-8501}" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:${PORT:-8501}" >/dev/null 2>&1 || true
fi

exec "$VENV_PY" -m streamlit run app.py --server.port "${PORT:-8501}"
