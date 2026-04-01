import warnings as _warnings

# ── Suppress pyannote warnings ───────────────────────────────────────────
_warnings.filterwarnings("ignore", category=UserWarning, module="pyannote")

# ── Load .env ────────────────────────────────────────────────────────────
from dotenv import load_dotenv as _load_dotenv
_load_dotenv()
