import hashlib
import os
import shutil
from datetime import datetime

AUDIO_DIR = os.path.join("data", "raw_audio")
ALLOWED_EXTENSIONS = {".wav", ".mp3"}


def ensure_audio_dir() -> None:
    os.makedirs(AUDIO_DIR, exist_ok=True)


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def is_allowed_extension(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


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


def delete_audio_file(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)
