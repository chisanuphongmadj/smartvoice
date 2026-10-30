"""scripts/compare_llm_models.py — re-runs the analyses per model, never writes the DB."""

import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from smartvoice import db, ollama_client

_SPEC = importlib.util.spec_from_file_location(
    "compare_llm_models", Path(__file__).resolve().parent.parent / "scripts" / "compare_llm_models.py"
)
compare = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(compare)


def _result(**overrides):
    base = {
        "summary": "ลูกค้าแจ้งผ้าขาด",
        "topic": "แจ้งปัญหาสินค้า",
        "topic_detail": "ผ้าขาด/ผ้าหุ้มชำรุด",
        "sentiment": "negative",
        "sentiment_reason": "ไม่พอใจ — ลูกค้าพูดว่า: \"ผ้าขาด\"",
        "agent_performance": json.dumps({"overall_score": 4, "next_action": "ส่งช่างไปดู"}, ensure_ascii=False),
        "anomaly_detected": False,
        "anomaly_reason": "",
        "anomaly_severity": "",
    }
    base.update(overrides)
    return base


class TestLoadCalls(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._env = mock.patch.dict(os.environ, {"DB_PATH": self.db_path})
        self._env.start()
        db.init_db()
        self.done = db.insert_call("a.wav", "ha", "/a.wav")
        db.update_call_results(call_id=self.done, transcript="Agent: สวัสดีค่ะ", summary="", sentiment="neutral",
                               topic="อื่นๆ")
        db.insert_call("b.wav", "hb", "/b.wav")  # not processed

    def tearDown(self):
        self._env.stop()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_only_processed_calls_with_a_transcript(self):
        calls = compare.load_calls(self.db_path)
        self.assertEqual([c["id"] for c in calls], [self.done])
        self.assertEqual(calls[0]["transcript"], "Agent: สวัสดีค่ะ")

    def test_the_database_is_opened_read_only(self):
        uri = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro"
        with mock.patch.object(compare.sqlite3, "connect", wraps=sqlite3.connect) as connect:
            compare.load_calls(self.db_path)
        connect.assert_called_once_with(uri, uri=True)
        conn = sqlite3.connect(uri, uri=True)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("UPDATE calls SET summary = 'x'")
        conn.close()


class TestObserveAndRules(unittest.TestCase):
    def test_observe_counts_requests_and_bad_json_then_restores(self):
        real_chat, real_extract = ollama_client.chat, ollama_client.extract_json
        log = compare.RequestLog()
        with mock.patch.object(ollama_client, "chat", return_value='{"a": 1}'):
            with compare.observe(log):
                ollama_client.extract_json(ollama_client.chat("s", "u"))
                with self.assertRaises(ValueError):
                    ollama_client.extract_json("no json here")
        self.assertEqual((log.requests, log.failures, log.raw), (1, 1, [{"a": 1}]))
        self.assertIs(ollama_client.extract_json, real_extract)
        self.assertIs(ollama_client.chat, real_chat)

    def test_invented_quote_and_unverified_anomaly_are_counted(self):
        raw = [
            {"customer_quote": "คำที่ลูกค้าไม่ได้พูด", "sentiment": "negative"},
            {"anomaly_detected": True, "category": "A1"},
        ]
        rejected = compare.rule_rejections(raw, _result(sentiment_reason="ไม่พอใจ"))
        self.assertEqual(len(rejected), 2)

    def test_grounded_answers_are_not_counted(self):
        raw = [{"customer_quote": "ผ้าขาด"}, {"anomaly_detected": False}]
        self.assertEqual(compare.rule_rejections(raw, _result()), [])


class TestRunAndReport(unittest.TestCase):
    def test_run_model_uses_the_model_and_reports_per_call(self):
        calls = [{"id": 1, "filename": "a.wav", "transcript": "Customer: ผ้าขาด"}]
        seen_models = []

        def fake_analyze(transcript):
            seen_models.append(os.environ["OLLAMA_MODEL"])
            ollama_client.chat("s", "u")
            return _result()

        with mock.patch.dict(os.environ, {}), \
             mock.patch.object(compare, "_ollama", return_value={}), \
             mock.patch.object(ollama_client, "chat", return_value="{}"), \
             mock.patch.object(ollama_client, "analyze_transcript", side_effect=fake_analyze):
            run = compare.run_model("new-model", calls, progress=lambda _: None)

        self.assertEqual(seen_models, ["new-model"])
        self.assertEqual(run["requests"], 1)
        self.assertEqual(run["rows"][0]["topic_detail"], "ผ้าขาด/ผ้าหุ้มชำรุด")
        self.assertEqual(run["rows"][0]["qa_score"], 4)

    def test_report_shows_agreement_and_every_call_side_by_side(self):
        def run(model, sentiment):
            row = {"call_id": 7, "filename": "a.wav", **compare.summarize_result(_result(sentiment=sentiment)),
                   "seconds": 3.0, "rejected": ""}
            return {"model": model, "rows": [row], "load_seconds": 1, "memory": "8 GB", "total_seconds": 3,
                    "avg_seconds": 3, "requests": 5, "json_failures": 0, "rule_rejections": 0}

        runs = [run("old", "negative"), run("new", "neutral")]
        report = compare.render_markdown(runs, "data/x.db")
        self.assertIn("อารมณ์ลูกค้า 0/1", report)
        self.assertIn("เรื่อง 1/1", report)
        self.assertIn("### สาย 7", report)
        self.assertIn("| `old` | `new` |", report)


if __name__ == "__main__":
    unittest.main()
