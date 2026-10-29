"""Stop button for background processing (smartvoice.processing_control).

Covers the control itself, the two DB helpers behind the Admin live panel,
process_call honouring a stop, and the queue putting unstarted calls back.
"""

import importlib
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

from smartvoice import db, ollama_client, pipeline, processing_control, ui_helpers
from smartvoice.processing_control import ProcessingCancelled


def _reset_control():
    # Module state is process-wide; make sure no test leaks a run into the next.
    while processing_control.is_running():
        processing_control.finish()
    processing_control.clear_run()


class TestControl(unittest.TestCase):
    def setUp(self):
        _reset_control()

    def tearDown(self):
        _reset_control()

    def test_stop_without_a_running_job_does_nothing(self):
        self.assertFalse(processing_control.request_stop())
        processing_control.check()  # no raise

    def test_stop_raises_at_the_next_checkpoint(self):
        processing_control.begin([1, 2])
        self.assertTrue(processing_control.request_stop())
        with self.assertRaises(ProcessingCancelled):
            processing_control.check()

    def test_cancellation_is_not_swallowed_by_except_exception(self):
        # The STT/LLM code falls back on `except Exception`; a stop must pass through.
        processing_control.begin([1])
        processing_control.request_stop()
        with self.assertRaises(ProcessingCancelled):
            try:
                processing_control.check()
            except Exception:
                self.fail("ProcessingCancelled was caught by except Exception")

    def test_finishing_the_last_job_clears_the_stop_but_keeps_the_run_list(self):
        processing_control.begin([1, 2])
        processing_control.request_stop()
        processing_control.finish()
        self.assertFalse(processing_control.is_running())
        self.assertFalse(processing_control.stop_requested())
        self.assertEqual(processing_control.run_call_ids(), [1, 2])

    def test_a_new_run_starts_with_a_fresh_list(self):
        processing_control.begin([1, 2])
        processing_control.finish()
        processing_control.begin([3])
        self.assertEqual(processing_control.run_call_ids(), [3])

    def test_a_job_started_during_a_run_joins_it(self):
        processing_control.begin([1, 2])
        processing_control.begin([2, 5])
        self.assertEqual(processing_control.run_call_ids(), [1, 2, 5])
        processing_control.finish()
        self.assertTrue(processing_control.is_running())

    def test_clear_run_is_ignored_while_running(self):
        processing_control.begin([1])
        processing_control.clear_run()
        self.assertEqual(processing_control.run_call_ids(), [1])
        processing_control.finish()
        processing_control.clear_run()
        self.assertEqual(processing_control.run_call_ids(), [])

    def test_uninterruptible_block_ignores_the_stop(self):
        processing_control.begin([1])
        processing_control.request_stop()
        with processing_control.uninterruptible():
            processing_control.check()  # no raise
        with self.assertRaises(ProcessingCancelled):
            processing_control.check()

    def test_state_survives_the_module_being_imported_again(self):
        # Streamlit's file watcher drops project modules from sys.modules when a
        # .py file changes; the page then imports a fresh copy while the queue
        # thread keeps the old one. A running queue was reported as stuck.
        processing_control.begin([7])
        saved = sys.modules.pop("smartvoice.processing_control")
        try:
            fresh = importlib.import_module("smartvoice.processing_control")
            self.assertIsNot(fresh, saved)
            self.assertTrue(fresh.is_running())
            self.assertEqual(fresh.run_call_ids(), [7])
            self.assertTrue(fresh.request_stop())
            with self.assertRaises(saved.ProcessingCancelled):  # same class
                fresh.check()
        finally:
            sys.modules["smartvoice.processing_control"] = saved

    def test_ollama_chat_checks_before_sending(self):
        processing_control.begin([1])
        processing_control.request_stop()
        with mock.patch("smartvoice.ollama_client.requests.post") as post:
            with self.assertRaises(ProcessingCancelled):
                ollama_client.chat("system", "user")
        post.assert_not_called()


class _DBCase(unittest.TestCase):
    def setUp(self):
        _reset_control()
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._env = mock.patch.dict(os.environ, {"DB_PATH": self.db_path})
        self._env.start()
        db.init_db()

    def tearDown(self):
        _reset_control()
        self._env.stop()
        try:
            os.remove(self.db_path)
        except OSError:
            pass


class TestDBHelpers(_DBCase):
    def test_reset_only_touches_processing_rows_and_clears_the_error(self):
        processing = db.insert_call("a.wav", "ha", "/a.wav")
        done = db.insert_call("b.wav", "hb", "/b.wav")
        db.update_call_status(processing, "processing", error_msg="old")
        db.update_processing_step(processing, "step")
        db.update_call_status(done, "done")

        self.assertEqual(db.reset_calls_to_uploaded([processing, done]), 1)

        a = db.get_call_by_id(processing)
        self.assertEqual(a["status"], "uploaded")
        self.assertIsNone(a["error_msg"])  # a stopped call didn't fail
        self.assertIsNone(a["processing_step"])
        self.assertEqual(db.get_call_by_id(done)["status"], "done")
        self.assertEqual(db.reset_calls_to_uploaded([]), 0)

    def test_progress_rows_follow_the_queue_order_and_skip_transcripts(self):
        first = db.insert_call("a.wav", "ha", "/a.wav")
        second = db.insert_call("b.wav", "hb", "/b.wav")
        rows = db.get_calls_progress([second, first, 9999])
        self.assertEqual([r["id"] for r in rows], [second, first])
        self.assertNotIn("transcript", rows[0])
        self.assertEqual(db.get_calls_progress([]), [])


_ANALYSIS = {"summary": "สรุป", "sentiment": "neutral", "topic": "สอบถามข้อมูล"}


class TestProcessCallStop(_DBCase):
    def test_stop_during_stt_puts_the_call_back_in_the_queue(self):
        cid = db.insert_call("a.wav", "ha", "/a.wav")
        processing_control.begin([cid])

        def fake_stt(path, step_callback=None):
            processing_control.request_stop()
            step_callback("→ chunk 2/10")
            return []

        with mock.patch.object(pipeline, "_transcribe_diarized", side_effect=fake_stt):
            with self.assertRaises(ProcessingCancelled):
                pipeline.process_call(cid)

        call = db.get_call_by_id(cid)
        self.assertEqual(call["status"], "uploaded")
        self.assertIsNone(call["error_msg"])

    def test_stop_while_saving_still_finishes_the_call(self):
        cid = db.insert_call("a.wav", "ha", "/a.wav")
        processing_control.begin([cid])

        def assign_case_then_llm(call_id, analysis):
            # Case matching asks Ollama — a stop pressed now must not leave a
            # saved call without its case.
            processing_control.request_stop()
            processing_control.check()

        with mock.patch.object(pipeline, "_transcribe_diarized", return_value=[]), \
             mock.patch.object(pipeline.ollama_client, "cleanup_transcript", side_effect=lambda c: c), \
             mock.patch.object(pipeline.ollama_client, "correct_speakers", side_effect=lambda c: c), \
             mock.patch.object(pipeline.ollama_client, "analyze_transcript", return_value=dict(_ANALYSIS)), \
             mock.patch.object(pipeline, "_auto_assign_case", side_effect=assign_case_then_llm) as assign:
            pipeline.process_call(cid)

        assign.assert_called_once()
        self.assertEqual(db.get_call_by_id(cid)["status"], "done")


class TestQueueStop(_DBCase):
    def _wait_for_queue(self):
        deadline = time.time() + 5
        while processing_control.is_running() and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(processing_control.is_running())

    def test_stopping_the_queue_requeues_the_calls_that_never_started(self):
        ids = [db.insert_call(f"{n}.wav", f"h{n}", f"/{n}.wav") for n in range(3)]

        def stop_on_first(call_id):
            processing_control.request_stop()
            db.reset_calls_to_uploaded([call_id])  # what process_call does
            raise ProcessingCancelled()

        with mock.patch("smartvoice.ui_helpers.get_ollama_readiness", return_value=(True, "")), \
             mock.patch.object(ui_helpers.pipeline, "process_call", side_effect=stop_on_first) as run:
            queued = ui_helpers.launch_processing_queue(ids)
            self._wait_for_queue()

        self.assertEqual(queued, ids)
        run.assert_called_once_with(ids[0])
        self.assertEqual([db.get_call_by_id(i)["status"] for i in ids], ["uploaded"] * 3)
        # The queue can be started again afterwards.
        self.assertFalse(ui_helpers._queue_running)

    def test_a_finished_queue_leaves_its_results_alone(self):
        ids = [db.insert_call(f"{n}.wav", f"h{n}", f"/{n}.wav") for n in range(2)]

        with mock.patch("smartvoice.ui_helpers.get_ollama_readiness", return_value=(True, "")), \
             mock.patch.object(ui_helpers.pipeline, "process_call",
                               side_effect=lambda cid: db.update_call_status(cid, "done")):
            ui_helpers.launch_processing_queue(ids)
            self._wait_for_queue()

        self.assertEqual([db.get_call_by_id(i)["status"] for i in ids], ["done", "done"])
        self.assertEqual(processing_control.run_call_ids(), ids)


if __name__ == "__main__":
    unittest.main()
