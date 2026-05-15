"""Tests for shared UI helper behavior."""

from unittest import mock

from smartvoice import ui_helpers


def test_launch_processing_does_not_start_when_ollama_unavailable():
    with mock.patch("smartvoice.ui_helpers.get_ollama_readiness", return_value=(False, "not ready")):
        with mock.patch("smartvoice.ui_helpers.db.get_call_by_id") as get_call:
            with mock.patch("smartvoice.ui_helpers.db.update_call_status") as update_status:
                ui_helpers.launch_processing(123)

    get_call.assert_not_called()
    update_status.assert_not_called()


def test_launch_processing_queue_does_not_start_when_ollama_unavailable():
    with mock.patch("smartvoice.ui_helpers.get_ollama_readiness", return_value=(False, "not ready")):
        with mock.patch("smartvoice.ui_helpers.db.get_call_by_id") as get_call:
            with mock.patch("smartvoice.ui_helpers.db.update_call_status") as update_status:
                result = ui_helpers.launch_processing_queue([1, 2, 3])

    assert result is None
    get_call.assert_not_called()
    update_status.assert_not_called()
