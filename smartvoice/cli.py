"""CLI entry point — run `smartvoice` after `pip install -e .`"""

import sys
import subprocess
from pathlib import Path


def main():
    app_path = Path(__file__).resolve().parent.parent / "Home.py"
    sys.exit(subprocess.call(["streamlit", "run", str(app_path), "--server.port", "8501"]))


if __name__ == "__main__":
    main()
