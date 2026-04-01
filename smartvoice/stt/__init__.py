"""STT sub-package — Speech-to-Text with diarization.

Public API:
    transcribe_diarized(file_path, step_callback) -> list[dict]
"""

from smartvoice.stt.orchestrator import transcribe_diarized  # noqa: F401
