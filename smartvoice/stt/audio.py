"""Audio loading, resampling, noise reduction, and Thai text filtering."""

import re

from smartvoice.config import DENOISE_ENABLED, DENOISE_PROP_DECREASE


def load_audio_16k(file_path: str) -> tuple:
    """Load audio as mono float32 numpy array, resampled to 16 kHz."""
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(file_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(16000, sr)
        audio = resample_poly(audio, 16000 // g, sr // g).astype(np.float32)
    return audio, 16000


def denoise(audio, sr: int, log_fn):
    """Apply noise reduction on numpy array. Returns cleaned array."""
    if not DENOISE_ENABLED:
        log_fn("→ ปิด noise reduction ตาม config")
        return audio
    try:
        import numpy as np
        import noisereduce as nr
    except ImportError:
        log_fn("⚠ noisereduce ไม่ได้ติดตั้ง — ข้าม noise reduction")
        return audio
    try:
        prop_decrease = min(max(DENOISE_PROP_DECREASE, 0.0), 1.0)
        clean = nr.reduce_noise(y=audio, sr=sr, prop_decrease=prop_decrease, stationary=False)
        log_fn(f"→ ลด noise เสร็จ (prop_decrease={prop_decrease:.2f})")
        return clean.astype(np.float32)
    except Exception as e:
        log_fn(f"⚠ noise reduction ล้มเหลว ({e}) — ใช้เสียงต้นฉบับ")
        return audio


def has_thai(text: str, min_ratio: float = 0.25) -> bool:
    """Check if text contains enough Thai characters to be considered valid Thai."""
    text = text.strip()
    if not text:
        return False
    thai_chars = len(re.findall(r'[\u0E00-\u0E7F]', text))
    non_space = len(re.findall(r'\S', text))
    if non_space == 0:
        return False
    return (thai_chars / non_space) >= min_ratio
