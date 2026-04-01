import unittest

from smartvoice.stt.diarize import (
    _group_words_by_speaker_and_pause,
    _pick_speaker_for_word,
)
from smartvoice.stt.transcribe import _hotwords_text


class TestDiarizationHelpers(unittest.TestCase):
    def test_pick_speaker_prefers_overlap(self):
        diar_turns = [
            (0.0, 1.0, "SPEAKER_00"),
            (1.0, 2.0, "SPEAKER_01"),
        ]

        speaker = _pick_speaker_for_word(1.2, 1.6, diar_turns)

        self.assertEqual(speaker, "Speaker 1")

    def test_pick_speaker_uses_closest_turn_when_no_overlap(self):
        diar_turns = [
            (0.0, 1.0, "SPEAKER_00"),
            (3.0, 4.0, "SPEAKER_01"),
        ]

        speaker = _pick_speaker_for_word(2.1, 2.2, diar_turns)

        self.assertEqual(speaker, "Speaker 1")

    def test_group_words_by_speaker_and_pause_splits_on_pause(self):
        words = [
            {"speaker": "Speaker 0", "word": "สวัสดี", "start": 0.0, "end": 0.4},
            {"speaker": "Speaker 0", "word": "ค่ะ", "start": 0.41, "end": 0.6},
            {"speaker": "Speaker 0", "word": "พอดี", "start": 1.7, "end": 2.0},
            {"speaker": "Speaker 0", "word": "สอบถาม", "start": 2.01, "end": 2.4},
        ]

        result = _group_words_by_speaker_and_pause(words)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "สวัสดีค่ะ")
        self.assertEqual(result[1]["text"], "พอดีสอบถาม")

    def test_group_words_by_speaker_and_pause_splits_long_segment(self):
        words = [
            {"speaker": "Speaker 0", "word": "หนึ่ง", "start": 0.0, "end": 0.2},
            {"speaker": "Speaker 0", "word": "สอง", "start": 18.1, "end": 18.3},
            {"speaker": "Speaker 0", "word": "สาม", "start": 18.8, "end": 19.0},
        ]

        result = _group_words_by_speaker_and_pause(words)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "หนึ่ง")
        self.assertEqual(result[1]["text"], "สองสาม")

    def test_hotwords_text_contains_domain_terms(self):
        hotwords = _hotwords_text()

        self.assertIn("Restonic", hotwords)
        self.assertIn("Trade-in", hotwords)
        self.assertIn("หาดใหญ่", hotwords)
        self.assertIn("โปรราคาพิเศษ", hotwords)
        self.assertIn("ภาคใต้", hotwords)
        self.assertIn("ทางห้าง", hotwords)


if __name__ == "__main__":
    unittest.main()
