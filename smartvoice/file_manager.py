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


def extract_phone_from_filename(filename: str) -> str | None:
    """Extract a Thai phone number (10 digits starting with 0) from a filename.

    Supports formats like:
      20251225134209-1766644826.135925-0631451550-104-Inbound.wav
    Returns the phone string or None if not found.
    """
    name = os.path.splitext(filename)[0]
    match = _THAI_PHONE_RE.search(name)
    return match.group(0) if match else None
