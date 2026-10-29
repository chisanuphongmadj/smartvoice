"""Stop button for background processing + the list of calls in the current run.

Processing runs in daemon threads inside the Streamlit process (see
`ui_helpers.launch_processing*`), so this state is plain module memory shared
by every browser session: one person pressing "หยุด" stops the run for all.

Stopping is cooperative — a thread can't be killed safely in Python. The
pipeline calls `check()` at its checkpoints (every pipeline step, every STT
progress message, every Ollama request) and `check()` raises
`ProcessingCancelled` once a stop was requested. The call in progress then goes
back to 'uploaded', and so do the queued calls that never started.

No Streamlit import, so it is unit-testable.
"""

from __future__ import annotations

import sys
import threading
import types
from contextlib import contextmanager


class _Cancelled(BaseException):
    """Raised at a checkpoint after the user pressed stop.

    A BaseException (like KeyboardInterrupt) on purpose: the STT and LLM code
    is full of `except Exception` fallbacks that would otherwise swallow the
    stop and carry on with the next backend or the next request.
    """


def _shared_state() -> types.ModuleType:
    """State that survives this module being imported again.

    When any project .py file changes, Streamlit's file watcher drops every
    project module from sys.modules, so the page imports a fresh copy of this
    module while the running thread still holds the old one. Both must see the
    same run, or the page reports a running queue as stuck. The holder lives
    under a name outside the `smartvoice.` package, which the watcher leaves alone.
    """
    holder = sys.modules.get("_smartvoice_processing_state")
    if holder is None:
        holder = types.ModuleType("_smartvoice_processing_state")
        holder.lock = threading.Lock()
        holder.stop = threading.Event()
        holder.local = threading.local()
        holder.active_jobs = 0
        holder.run_ids = []
        holder.cancelled = _Cancelled
        sys.modules["_smartvoice_processing_state"] = holder
    return holder


_state = _shared_state()
ProcessingCancelled = _state.cancelled


def begin(call_ids: list[int]) -> None:
    """A background job starts on `call_ids`.

    The first job of a run clears the previous run's list and any old stop
    request; a job started while another is running joins the same run.
    """
    with _state.lock:
        if _state.active_jobs == 0:
            _state.stop.clear()
            _state.run_ids = []
        _state.active_jobs += 1
        _state.run_ids.extend(cid for cid in call_ids if cid not in _state.run_ids)


def finish() -> None:
    """A background job ended (done, failed or stopped).

    The run's list is kept so the page can still show what the run produced.
    """
    with _state.lock:
        _state.active_jobs = max(0, _state.active_jobs - 1)
        if _state.active_jobs == 0:
            _state.stop.clear()


def request_stop() -> bool:
    """Ask every running job to stop at its next checkpoint. False = nothing was running."""
    with _state.lock:
        if _state.active_jobs == 0:
            return False
        _state.stop.set()
        return True


def is_running() -> bool:
    with _state.lock:
        return _state.active_jobs > 0


def stop_requested() -> bool:
    return _state.stop.is_set()


def run_call_ids() -> list[int]:
    """Calls of the current (or the last finished) run, in the order they were queued."""
    with _state.lock:
        return list(_state.run_ids)


def clear_run() -> None:
    """Forget the last run's list (the page's "ปิด" button). Ignored while a run is going."""
    with _state.lock:
        if _state.active_jobs == 0:
            _state.run_ids = []


def check() -> None:
    """Checkpoint: raise ProcessingCancelled if a stop was requested."""
    if _state.stop.is_set() and not getattr(_state.local, "shielded", False):
        raise ProcessingCancelled()


@contextmanager
def uninterruptible():
    """Checkpoints inside this block don't stop — for saving results.

    Once a call's results are written it must also get its case, otherwise a
    stop between the two leaves a 'done' call with no case.
    """
    previous = getattr(_state.local, "shielded", False)
    _state.local.shielded = True
    try:
        yield
    finally:
        _state.local.shielded = previous
