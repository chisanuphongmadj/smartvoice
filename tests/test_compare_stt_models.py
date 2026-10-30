"""scripts/compare_stt_models.py — transcribes stored audio per model, never writes the DB."""

import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from smartvoice import db
from smartvoice.stt import transcribe

_SPEC = importlib.util.spec_from_file_location(
    "compare_stt_models", Path(__file__).resolve().parent.parent / "scripts" / "compare_stt_models.py"
)
compare = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(compare)


class TestLoadCalls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # Windows: the DB may still be open
        self.db_path = os.path.join(self.tmp.name, "t.db")
        self._env = mock.patch.dict(os.environ, {"DB_PATH": self.db_path})
        self._env.start()
        db.init_db()
        audio = os.path.join(self.tmp.name, "a.wav")
        Path(audio).write_bytes(b"RIFF")
        self.done = db.insert_call("a.wav", "ha", audio)
        db.update_call_status(self.done, "done")
        gone = db.insert_call("gone.wav", "hg", os.path.join(self.tmp.name, "gone.wav"))
        db.update_call_status(gone, "done")                       # audio file removed
        db.insert_call("b.wav", "hb", audio)                      # not processed

    def tearDown(self):
        self._env.stop()
        self.tmp.cleanup()

    def test_only_processed_calls_whose_audio_still_exists(self):
        self.assertEqual([c["id"] for c in compare.load_calls(self.db_path)], [self.done])

    def test_the_database_is_opened_read_only(self):
        uri = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro"
        with mock.patch.object(compare.sqlite3, "connect", wraps=sqlite3.connect) as connect:
            compare.load_calls(self.db_path)
        connect.assert_called_once_with(uri, uri=True)


class TestMetrics(unittest.TestCase):
    def test_known_mistake_is_not_also_counted_as_the_brand(self):
        hits = compare.domain_hits("ที่นอนโอมาสนา กับ ที่นอน Omazz ของโลตัส")
        self.assertEqual((hits["โอมาสนา"], hits["Omazz"], hits["ที่นอน"], hits["โลตัส"]), (1, 1, 2, 1))

    def test_cer_ignores_spaces_and_counts_edits(self):
        self.assertEqual(compare.cer("สวัสดี ค่ะ", "สวัสดีค่ะ"), 0)
        self.assertAlmostEqual(compare.cer("สวัสดีคะ", "สวัสดีค่ะ"), 1 / 9)
        self.assertEqual(compare.edit_distance("kitten", "sitting"), 3)

    def test_transcript_metrics(self):
        m = compare.transcript_metrics("[00:00] ที่นอน abc", 60)
        self.assertEqual(m["chars_per_min"], len("[00:00]ที่นอนabc"))
        self.assertEqual(m["domain_terms"], "ที่นอน 1")
        self.assertEqual(m["known_errors"], "—")


class TestRunModel(unittest.TestCase):
    def test_each_model_transcribes_whole_segments_and_is_unloaded(self):
        calls = [{"id": 7, "filename": "a.wav", "file_path": "a.wav"}]
        audio = {7: (np.zeros(16000 * 30, dtype=np.float32), 16000)}
        seen = []

        def fake_hf(samples, sr, log_fn):
            seen.append((transcribe.WHISPER_MODEL, transcribe._split_segments_to_words([{"word": "x"}, 1])))
            return [{"word": "สวัสดีค่ะ ที่นอนโลตัส", "start": 0.0, "end": 3.0}]

        real_split, real_model = transcribe._split_segments_to_words, transcribe.WHISPER_MODEL
        with mock.patch.object(transcribe, "transcribe_hf", side_effect=fake_hf), \
             mock.patch.object(transcribe, "unload_model") as unload, \
             mock.patch.object(compare, "_cuda", return_value=None):
            run = compare.run_model("new/whisper", calls, audio, progress=lambda _: None)
        transcribe.WHISPER_MODEL = real_model

        # warm-up + one call, both with the new model and segment splitting switched off
        self.assertEqual(seen, [("new/whisper", [{"word": "x"}, 1])] * 2)
        self.assertIs(transcribe._split_segments_to_words, real_split)
        self.assertEqual(unload.call_count, 2)
        row = run["rows"][0]
        self.assertEqual(row["text"], "[00:00] สวัสดีค่ะ ที่นอนโลตัส")
        self.assertEqual((row["audio_seconds"], run["domain_total"]), (30.0, 2))

    def test_a_model_can_run_without_the_domain_word_prompt(self):
        calls = [{"id": 7, "filename": "a.wav", "file_path": "a.wav"}]
        audio = {7: (np.zeros(16000, dtype=np.float32), 16000)}
        prompts = []

        def fake_hf(samples, sr, log_fn):
            prompts.append(transcribe._hf_prompt_ids(object()))
            return []

        real_prompt, real_model = transcribe._hf_prompt_ids, transcribe.WHISPER_MODEL
        with mock.patch.object(transcribe, "transcribe_hf", side_effect=fake_hf), \
             mock.patch.object(transcribe, "unload_model"), \
             mock.patch.object(compare, "_cuda", return_value=None):
            run = compare.run_model("typhoon/large", calls, audio, progress=lambda _: None, use_prompt=False)
        transcribe.WHISPER_MODEL = real_model

        self.assertEqual(prompts, [None, None])
        self.assertIs(transcribe._hf_prompt_ids, real_prompt)
        self.assertEqual(run["model"], "typhoon/large (no prompt)")

    def test_report_scores_against_references_and_shows_every_transcript(self):
        def run(model, text):
            row = {"call_id": 7, "filename": "a.wav", "text": text, "seconds": 3.0, "audio_seconds": 60.0,
                   "rtf": 0.05, **compare.transcript_metrics(text, 60)}
            return {"model": model, "rows": [row], "load_seconds": 1, "peak_vram": "2.0 GB",
                    "total_seconds": 3.0, "rtf": 0.05, "domain_total": 1, "errors_total": 0}

        runs = [run("old", "ที่นอนโอมาสนา"), run("new", "ที่นอนโอมาซ")]
        compare.score_runs(runs, {7: "ที่นอนโอมาซ"})
        self.assertEqual(runs[1]["rows"][0]["cer"], 0)
        self.assertGreater(runs[0]["cer"], 0)
        report = compare.render_markdown(runs, "data/x.db", {7: "ที่นอนโอมาซ"})
        self.assertIn("### สาย 7 (01:00)", report)
        self.assertIn("| CER |", report)
        self.assertIn("ที่นอนโอมาสนา", report)
        self.assertIn("<code>new</code>", report)


if __name__ == "__main__":
    unittest.main()
