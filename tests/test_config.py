"""Tests for centralized configuration."""

import os
import unittest
from unittest import mock
import numpy as np
import torch
import tempfile


class TestConfig(unittest.TestCase):
    def test_defaults_loaded(self):
        from smartvoice.config import (
            WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE,
            OLLAMA_BASE_URL, OLLAMA_MODEL, DB_PATH,
        )
        # Defaults should be non-empty strings
        self.assertIsInstance(WHISPER_MODEL, str)
        self.assertTrue(len(WHISPER_MODEL) > 0)
        self.assertIn(WHISPER_DEVICE, ("auto", "cpu", "cuda"))
        self.assertIn(WHISPER_COMPUTE, ("auto", "float16", "int8"))
        self.assertTrue(OLLAMA_BASE_URL.startswith("http"))
        self.assertIsInstance(OLLAMA_MODEL, str)
        self.assertIsInstance(DB_PATH, str)

    def test_mock_stt_is_bool(self):
        from smartvoice.config import MOCK_STT
        self.assertIsInstance(MOCK_STT, bool)


class TestAudioHelpers(unittest.TestCase):
    def test_has_thai_positive(self):
        from smartvoice.stt.audio import has_thai
        self.assertTrue(has_thai("สวัสดีครับ"))
        self.assertTrue(has_thai("สวัสดี hello"))

    def test_has_thai_negative(self):
        from smartvoice.stt.audio import has_thai
        self.assertFalse(has_thai("hello world"))
        self.assertFalse(has_thai(""))
        self.assertFalse(has_thai("   "))

    def test_has_thai_ratio_threshold(self):
        from smartvoice.stt.audio import has_thai
        # Very low Thai ratio — should fail default threshold
        self.assertFalse(has_thai("a" * 100 + "ก"))


class TestTranscribeHelpers(unittest.TestCase):
    def test_is_standard_model(self):
        from smartvoice.stt.transcribe import is_standard_model, _STANDARD_MODELS
        # If current model is in standard set, it should return True
        from smartvoice.config import WHISPER_MODEL
        result = is_standard_model()
        self.assertEqual(result, WHISPER_MODEL in _STANDARD_MODELS)

    def test_resolve_device_compute(self):
        from smartvoice.stt.transcribe import resolve_device_compute
        device, compute = resolve_device_compute()
        self.assertIn(device, ("cpu", "cuda"))
        self.assertIn(compute, ("float16", "int8"))

    def test_hf_prompt_ids_returns_torch_tensor(self):
        from smartvoice.stt.transcribe import _hf_prompt_ids

        class FakeTokenizer:
            def get_prompt_ids(self, text, return_tensors="np"):
                self.last_return_tensors = return_tensors
                return np.array([1, 2, 3], dtype=np.int64)

        tokenizer = FakeTokenizer()
        prompt_ids = _hf_prompt_ids(tokenizer)

        self.assertEqual(tokenizer.last_return_tensors, "pt")
        self.assertTrue(torch.is_tensor(prompt_ids))
        self.assertEqual(prompt_ids.dtype, torch.long)
        self.assertEqual(prompt_ids.tolist(), [1, 2, 3])

    def test_hf_prompt_ids_truncates_long_prompt(self):
        from smartvoice.stt.transcribe import _hf_prompt_ids

        class FakeTokenizer:
            def get_prompt_ids(self, text, return_tensors="np"):
                return np.arange(200, dtype=np.int64)

        prompt_ids = _hf_prompt_ids(FakeTokenizer(), max_prompt_tokens=96)

        self.assertTrue(torch.is_tensor(prompt_ids))
        self.assertEqual(prompt_ids.numel(), 96)


class TestOrchestratorHelpers(unittest.TestCase):
    def test_select_backend_auto_prefers_transformers_for_nonstandard_model(self):
        from smartvoice.stt.orchestrator import _select_backend

        with mock.patch("smartvoice.stt.orchestrator.WHISPER_BACKEND", "auto"):
            with mock.patch("smartvoice.stt.orchestrator.is_standard_model", return_value=False):
                self.assertEqual(_select_backend(), "transformers")

    def test_looks_incomplete_transcript_flags_poor_coverage(self):
        from smartvoice.stt.orchestrator import _looks_incomplete_transcript

        words = [
            {"word": "สวัสดี", "start": 0.0, "end": 0.4},
            {"word": "ค่ะ", "start": 0.5, "end": 0.7},
            {"word": "สอบถาม", "start": 14.0, "end": 14.4},
        ]

        self.assertTrue(_looks_incomplete_transcript(words, 120.0))

    def test_looks_incomplete_transcript_accepts_reasonable_coverage(self):
        from smartvoice.stt.orchestrator import _looks_incomplete_transcript

        words = [
            {"word": "สวัสดี", "start": 0.0, "end": 0.4},
            {"word": "ค่ะ", "start": 0.5, "end": 0.7},
            {"word": "พอดี", "start": 32.0, "end": 32.3},
            {"word": "สอบถาม", "start": 63.0, "end": 63.4},
            {"word": "เพิ่มเติม", "start": 91.0, "end": 91.5},
        ]

        self.assertFalse(_looks_incomplete_transcript(words, 100.0))

    def test_explicit_transformers_backend_does_not_fallback_to_faster_whisper(self):
        from smartvoice.stt.orchestrator import _real_transcribe_diarized

        audio = np.zeros(16000, dtype=np.float32)
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"00")
            tmp.flush()
            with mock.patch("smartvoice.stt.orchestrator.WHISPER_BACKEND", "transformers"):
                with mock.patch("smartvoice.stt.orchestrator.load_audio_16k", return_value=(audio, 16000)):
                    with mock.patch("smartvoice.stt.orchestrator.denoise", side_effect=lambda data, sr, log_fn: data):
                        with mock.patch("smartvoice.stt.orchestrator.transcribe_hf", side_effect=RuntimeError("boom")):
                            with mock.patch("smartvoice.stt.orchestrator.transcribe_fw") as fw_mock:
                                with self.assertRaises(RuntimeError):
                                    _real_transcribe_diarized(tmp.name)
                                fw_mock.assert_not_called()


class TestDiarizeGrouping(unittest.TestCase):
    def test_group_words_by_pause_basic(self):
        from smartvoice.stt.diarize import group_words_by_pause
        words = [
            {"word": "สวัสดี", "start": 0.0, "end": 0.5},
            {"word": "ครับ", "start": 0.5, "end": 0.8},
            # pause > 1.0s
            {"word": "ขอบคุณ", "start": 2.0, "end": 2.5},
            {"word": "ค่ะ", "start": 2.5, "end": 2.8},
        ]
        result = group_words_by_pause(words, "Speaker 0")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "Speaker 0")
        self.assertIn("สวัสดี", result[0]["text"])
        self.assertIn("ขอบคุณ", result[1]["text"])

    def test_group_words_empty(self):
        from smartvoice.stt.diarize import group_words_by_pause
        self.assertEqual(group_words_by_pause([], "Speaker 0"), [])


class TestDB(unittest.TestCase):
    def test_init_db_idempotent(self):
        from smartvoice import db
        # Should not raise even when called multiple times
        db.init_db()
        db.init_db()


if __name__ == "__main__":
    unittest.main()
