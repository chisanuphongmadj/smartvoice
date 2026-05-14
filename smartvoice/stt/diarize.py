"""Speaker diarization using Pyannote + word-level speaker assignment."""

from smartvoice.config import HF_TOKEN
from smartvoice.stt.audio import has_thai
from smartvoice.stt.transcribe import resolve_device_compute

_diar_pipeline = None
_PAUSE_SPLIT_SEC = 0.8
_LONG_SEGMENT_SEC = 18.0
_LONG_SEGMENT_PAUSE_SPLIT_SEC = 0.35


def _normalize_speaker_label(speaker: str) -> str:
    if speaker.startswith("SPEAKER_"):
        num = speaker.replace("SPEAKER_", "").lstrip("0") or "0"
        return f"Speaker {num}"
    return speaker


def _pick_speaker_for_word(start: float, end: float, diar_turns: list[tuple[float, float, str]]) -> str:
    if not diar_turns:
        return "Speaker 0"

    best_spk = "Speaker 0"
    best_overlap = 0.0
    closest_spk = "Speaker 0"
    closest_distance = float("inf")
    word_mid = (start + end) / 2.0

    for d_start, d_end, spk in diar_turns:
        overlap = max(0.0, min(end, d_end) - max(start, d_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_spk = spk

        diar_mid = (d_start + d_end) / 2.0
        distance = abs(word_mid - diar_mid)
        if distance < closest_distance:
            closest_distance = distance
            closest_spk = spk

    chosen = best_spk if best_overlap > 0 else closest_spk
    return _normalize_speaker_label(chosen)


def _group_words_by_speaker_and_pause(words: list[dict]) -> list[dict]:
    if not words:
        return []

    output: list[dict] = []
    cur_spk = words[0].get("speaker", "Speaker 0")
    cur_words: list[str] = []
    cur_start = float(words[0].get("start", 0) or 0)
    cur_end = float(words[0].get("end", cur_start) or cur_start)

    for w in words:
        word = w.get("word", "")
        if not word:
            continue

        speaker = w.get("speaker", "Speaker 0")
        start = float(w.get("start", 0) or 0)
        end = float(w.get("end", start) or start)
        gap = start - cur_end
        seg_duration = cur_end - cur_start
        split_due_to_pause = gap > _PAUSE_SPLIT_SEC
        split_due_to_long_segment = seg_duration >= _LONG_SEGMENT_SEC and gap > _LONG_SEGMENT_PAUSE_SPLIT_SEC

        if cur_words and (speaker != cur_spk or split_due_to_pause or split_due_to_long_segment):
            text = "".join(cur_words).strip()
            if text and has_thai(text):
                output.append({"speaker": cur_spk, "text": text, "start": cur_start, "end": cur_end})
            cur_spk = speaker
            cur_words = [word]
            cur_start = start
            cur_end = end
            continue

        if not cur_words:
            cur_spk = speaker
            cur_start = start
        cur_words.append(word)
        cur_end = end

    if cur_words:
        text = "".join(cur_words).strip()
        if text and has_thai(text):
            output.append({"speaker": cur_spk, "text": text, "start": cur_start, "end": cur_end})
    return output


def diarize_words(file_path: str, all_words: list[dict], log_fn) -> list[dict]:
    """Assign a speaker label to each word using Pyannote diarization,
    then group consecutive same-speaker words into segments.
    Returns list of {"speaker", "text", "start", "end"}.
    """
    global _diar_pipeline

    if not HF_TOKEN:
        log_fn("⚠ ไม่มี HF_TOKEN — ข้าม diarization ใช้ Speaker 0 ทั้งหมด")
        return group_words_by_pause(all_words, "Speaker 0")

    log_fn("→ Diarization (Pyannote)...")
    try:
        import torch
        import soundfile as sf
        from pyannote.audio import Pipeline

        waveform_np, sample_rate = sf.read(file_path, always_2d=True)
        waveform_tensor = torch.tensor(waveform_np.T, dtype=torch.float32)

        device, _ = resolve_device_compute()

        if _diar_pipeline is None:
            log_fn("→ โหลด Pyannote pipeline...")
            _diar_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=HF_TOKEN,
            )
            _diar_pipeline = _diar_pipeline.to(torch.device(device))
        # Call-center audio is always 2-party (agent + customer). Constrain
        # the diarizer so it doesn't collapse two similar-sounding speakers
        # into one cluster, which empirically yields ~28 coarse segments for
        # a 4-min call vs. ~50+ when bounded to 2 speakers. If the call turns
        # out to be effectively mono (e.g. voicemail), min_speakers=1 keeps
        # a graceful fallback.
        diarization = _diar_pipeline({
            "waveform": waveform_tensor,
            "sample_rate": sample_rate,
        }, min_speakers=1, max_speakers=2)
        log_fn("← Diarization เสร็จ")
    except Exception as e:
        log_fn(f"⚠ Diarization ล้มเหลว ({e}) — ใช้ Speaker 0 ทั้งหมด")
        return group_words_by_pause(all_words, "Speaker 0")

    # pyannote 4.x returns DiarizeOutput dataclass; unwrap to Annotation
    annotation = getattr(diarization, "speaker_diarization", diarization)
    diar_turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]

    # Word-level speaker assignment
    for w in all_words:
        w["speaker"] = _pick_speaker_for_word(w["start"], w["end"], diar_turns)

    output = _group_words_by_speaker_and_pause(all_words)

    log_fn(f"← สร้าง {len(output)} segments (word-level diarization)")
    return output


def group_words_by_pause(words: list[dict], speaker: str,
                         pause_threshold: float = 1.0) -> list[dict]:
    """Group words into segments separated by pauses (for non-diarized output)."""
    if not words:
        return []
    output: list[dict] = []
    cur = [words[0]]
    for w in words[1:]:
        if w["start"] - cur[-1]["end"] > pause_threshold:
            text = "".join(x["word"] for x in cur).strip()
            if text and has_thai(text):
                output.append({"speaker": speaker, "text": text,
                               "start": cur[0]["start"], "end": cur[-1]["end"]})
            cur = [w]
        else:
            cur.append(w)
    if cur:
        text = "".join(x["word"] for x in cur).strip()
        if text and has_thai(text):
            output.append({"speaker": speaker, "text": text,
                           "start": cur[0]["start"], "end": cur[-1]["end"]})
    return output
