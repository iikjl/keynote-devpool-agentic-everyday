"""Watch a DW state file for phase transitions and emit events.

Composites write `agents/<dw_id>/dw_state.json` as they progress through
phases (plan, build, test, review, ...). This module polls that file in a
background thread alongside the running workflow and invokes a callback on
each transition into `running`, `success`, or `failed`. Used by `dw_runner.py`
to post per-phase comments back to the source issue / PR.
"""

import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal, Optional

from state import get_state_path, load_state

EventKind = Literal["start", "success", "failed"]
PhaseEventCallback = Callable[[str, EventKind, Optional[float]], None]

POLL_INTERVAL_SECONDS = 2.0


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _duration_seconds(
    started: Optional[str], completed: Optional[str]
) -> Optional[float]:
    s = _parse_iso(started)
    c = _parse_iso(completed)
    if s and c:
        return (c - s).total_seconds()
    return None


def watch_state_file(
    dw_id: str,
    on_event: PhaseEventCallback,
    stop_event: threading.Event,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Poll the state file and dispatch events for each phase transition.

    Tracks the last-seen status for every phase. On any change to `running`,
    `success`, or `failed`, fires `on_event(phase_name, kind, duration_seconds)`.
    Duration is only set for terminal events (success/failed). Runs until
    `stop_event` is set; one final poll is performed after stop so phases
    that completed during shutdown are still reported.
    """
    state_path = Path(get_state_path(dw_id))
    last_status: dict[str, str] = {}

    def poll_once() -> None:
        if not state_path.exists():
            return
        state = load_state(dw_id)
        if state is None:
            return
        for phase_name, phase in state.phases.items():
            prev = last_status.get(phase_name)
            current = phase.status
            if prev == current:
                continue
            last_status[phase_name] = current
            if current == "running":
                on_event(phase_name, "start", None)
            elif current == "success":
                duration = _duration_seconds(phase.started_at, phase.completed_at)
                on_event(phase_name, "success", duration)
            elif current == "failed":
                duration = _duration_seconds(phase.started_at, phase.completed_at)
                on_event(phase_name, "failed", duration)

    while not stop_event.is_set():
        try:
            poll_once()
        except Exception:
            pass
        stop_event.wait(poll_interval)

    try:
        poll_once()
    except Exception:
        pass


def run_with_phase_watch(
    cmd: list[str],
    dw_id: str,
    on_event: PhaseEventCallback,
    cwd: Optional[Path] = None,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> int:
    """Run `cmd` to completion while a watcher thread polls the state file.

    Returns the workflow's exit code. The watcher thread is signalled to stop
    as soon as the workflow exits and is joined before this function returns.
    """
    stop_event = threading.Event()
    watcher = threading.Thread(
        target=watch_state_file,
        args=(dw_id, on_event, stop_event, poll_interval),
        daemon=True,
    )
    watcher.start()
    try:
        result = subprocess.run(cmd, cwd=cwd)
        return result.returncode
    finally:
        stop_event.set()
        watcher.join(timeout=poll_interval * 2 + 1)


__all__ = [
    "EventKind",
    "PhaseEventCallback",
    "run_with_phase_watch",
    "watch_state_file",
]
