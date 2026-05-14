#!/usr/bin/env bash
# SmartVoice launcher — Linux / macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
else
    echo "⚠️  .venv not found — run 'python -m venv .venv && pip install -r requirements.txt' first"
    exit 1
fi

exec streamlit run app.py --server.port "${PORT:-8501}"
