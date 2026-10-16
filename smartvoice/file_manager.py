import hashlib
import os
import re
from datetime import datetime

AUDIO_DIR = os.path.join("data", "raw_audio")
ALLOWED_EXTENSIONS = {".wav", ".mp3"}
MAX_FILE_SIZE_MB = 100  # ~1 hour of 16kHz mono WAV

# Magic bytes for audio content-type sniffing
# WAV: "RIFF....WAVE" / MP3: "ID3" tag or 0xFFFB/0xFFF3/0xFFF2 frame sync
_WAV_SIG = b"RIFF"
_MP3_SIGS = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")


def ensure_audio_dir() -> None:
    os.makedirs(AUDIO_DIR, exist_ok=True)


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def is_allowed_extension(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


def sniff_audio_type(file_bytes: bytes) -> str | None:
    """Return 'wav' or 'mp3' if bytes match known audio magic signatures, else None."""
    if not file_bytes or len(file_bytes) < 4:
        return None
    head = file_bytes[:12]
    if head.startswith(_WAV_SIG) and b"WAVE" in head:
        return "wav"
    if any(head.startswith(sig) for sig in _MP3_SIGS):
        return "mp3"
    return None


def validate_upload(file_bytes: bytes, filename: str) -> tuple[bool, str]:
    """Validate uploaded audio: extension, size, magic bytes.

    Returns (is_valid, error_message). Empty message when valid.
    """
    if not file_bytes:
        return False, "ไฟล์ว่างเปล่า"
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, f"ไฟล์ใหญ่เกิน {MAX_FILE_SIZE_MB} MB (ปัจจุบัน {size_mb:.1f} MB)"
    if not is_allowed_extension(filename):
        return False, "รองรับเฉพาะไฟล์ .wav หรือ .mp3"
    sniffed = sniff_audio_type(file_bytes)
    if sniffed is None:
        return False, "ไฟล์ไม่ใช่ไฟล์เสียง WAV/MP3 ที่ถูกต้อง (magic bytes ไม่ตรง)"
    return True, ""


def sanitize_filename(filename: str) -> str:
    """Strip path separators and dangerous chars — keep basename only."""
    # Remove any path component and disallow traversal
    base = os.path.basename(filename).replace("\\", "/").split("/")[-1]
    # Remove control chars and path-unfriendly symbols
    cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base)
    return cleaned or "unnamed.wav"


def _standard_filename(file_hash: str, ext: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = file_hash[:8]
    return f"{timestamp}_{short_hash}{ext}"


def save_audio_file(file_bytes: bytes, filename: str, file_hash: str = "") -> str:
    ensure_audio_dir()
    _, ext = os.path.splitext(filename.lower())
    if file_hash:
        standard_name = _standard_filename(file_hash, ext)
    else:
        standard_name = filename
    dest_path = os.path.join(AUDIO_DIR, standard_name)
    base, fext = os.path.splitext(standard_name)
    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(AUDIO_DIR, f"{base}_{counter}{fext}")
        counter += 1
    with open(dest_path, "wb") as f:
        f.write(file_bytes)
    return dest_path


# Thai phone: 0 followed by 9 digits (mobile 06x/08x/09x or landline 02x/03x/04x/05x/07x)
_THAI_PHONE_RE = re.compile(r"(?<![\d])0\d{9}(?![\d])")


def remove_audio_file(path: str | None) -> bool:
    """Delete a stored audio file. Returns False when it exists but can't be
    removed (e.g. open in a media player on Windows) — never raises, so one
    locked file can't stop a bulk delete halfway."""
    if not path or not os.path.exists(path):
        return True
    try:
        os.remove(path)
    except OSError:
        return False
    return True


# ── Proof-of-purchase files (warranty registrations) ─────────────────────
PROOF_DIR = os.path.join("data", "warranty_proofs")
MAX_PROOF_SIZE_MB = 10
_PROOF_SIGS = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"%PDF": ".pdf"}


def sniff_proof_type(file_bytes: bytes) -> str | None:
    """'.jpg' / '.png' / '.pdf' by content, not by the name the user gave it."""
    for sig, ext in _PROOF_SIGS.items():
        if file_bytes.startswith(sig):
            return ext
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return ".webp"
    return None


def save_proof_file(file_bytes: bytes) -> tuple[str | None, str | None]:
    """Store a receipt/slip image or PDF. Returns (path, error_message).

    Files are named by their SHA-256, so uploading the same receipt twice
    keeps one copy. Old proofs are never removed — the audit log points at them.
    """
    if not file_bytes:
        return None, "ไฟล์ว่างเปล่า"
    if len(file_bytes) > MAX_PROOF_SIZE_MB * 1024 * 1024:
        return None, f"ไฟล์ใหญ่เกิน {MAX_PROOF_SIZE_MB} MB"
    ext = sniff_proof_type(file_bytes)
    if not ext:
        return None, "รองรับเฉพาะรูป JPG / PNG / WEBP หรือไฟล์ PDF"
    os.makedirs(PROOF_DIR, exist_ok=True)
    path = os.path.join(PROOF_DIR, compute_file_hash(file_bytes) + ext)
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(file_bytes)
    return path, None


def extract_phone_from_filename(filename: str) -> str | None:
    """Extract a Thai phone number (10 digits starting with 0) from a filename.

    Supports formats like:
      20251225134209-1766644826.135925-0631451550-104-Inbound.wav
    Returns the phone string or None if not found.
    """
    name = os.path.splitext(filename)[0]
    match = _THAI_PHONE_RE.search(name)
    return match.group(0) if match else None


def extract_direction_from_filename(filename: str) -> str | None:
    """Detect call direction from CDR-style filenames.

    Filenames produced by the recording system end with `-Inbound.wav` or
    `-Outbound.wav`. Returns "inbound" / "outbound" / None (when the suffix
    is missing — e.g. manually renamed files).
    """
    if not filename:
        return None
    lower = filename.lower()
    if "inbound" in lower:
        return "inbound"
    if "outbound" in lower:
        return "outbound"
    return None


def extract_agent_code_from_filename(filename: str) -> str | None:
    """Extract the agent (extension) code from a CDR-style filename.

    Example layouts produced by Omazz's recording system:
      Outbound: 20251104173706-1762252614.105999-104-0819979336-Outbound.wav
      Inbound:  20251225134209-1766644826.135925-0631451550-104-Inbound.wav

    The agent extension is always a short numeric segment (2-5 digits)
    distinct from:
      • the 14-digit timestamp prefix
      • a 10-digit Thai phone number starting with "0"
    """
    if not filename:
        return None
    name = os.path.splitext(filename)[0]
    for seg in name.split("-"):
        seg = seg.strip()
        if not seg.isdigit():
            continue
        if len(seg) == 14:                     # timestamp prefix
            continue
        if len(seg) == 10 and seg.startswith("0"):  # Thai phone
            continue
        if 2 <= len(seg) <= 5:
            return seg
    return None


def extract_call_time_from_filename(filename: str) -> datetime | None:
    """When the call actually happened, from the CDR filename's leading
    YYYYMMDDHHMMSS (the phone system's local time).

    `calls.created_at` is the upload time, not the call time — this is the
    one to show staff. None when the name has no valid timestamp.
    """
    match = re.match(r"(\d{14})", os.path.basename(filename or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None
