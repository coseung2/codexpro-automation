import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import chatgpt_oracle_state as state  # noqa: E402
import chatgpt_oracle_watch as watcher  # noqa: E402


def make_run(tmp_path: Path, *, status: str = "running", pid: int | None = None) -> Path:
    run_dir = tmp_path / "projects" / "project-a" / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    output = run_dir / "output.md"
    payload = {
        "schema": state.STATE_SCHEMA,
        "run_id": run_dir.name,
        "status": status,
        "exit_code": None,
        "transport_status": "pending",
        "task_outcome": "pending",
        "terminal_harvested": False,
        "session_authority": "live",
        "artifact_sha256": None,
        "artifacts": {"output": str(output)},
        "host_watchdog": {"oracle_process_pid": pid},
    }
    state.write_json_atomic(run_dir / "state.json", payload)
    return run_dir


def test_resolve_exact_run_rejects_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    outside = make_run(tmp_path / "outside")
    with pytest.raises(watcher.WatchError, match="inside the Oracle projects state root"):
        watcher.resolve_exact_run_dir(outside, state_root=root)


def test_resolve_exact_run_rejects_identity_mismatch(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    payload = state.load_state(run_dir / "state.json")
    payload["run_id"] = "other-run"
    state.write_json_atomic(run_dir / "state.json", payload)
    with pytest.raises(watcher.WatchError, match="run_id"):
        watcher.resolve_exact_run_dir(run_dir, state_root=tmp_path / "projects")


def test_immediate_terminal_signal_reports_metadata_without_reading_output(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, status="complete")
    payload = state.load_state(run_dir / "state.json")
    payload.update({
        "exit_code": 0,
        "transport_status": "complete",
        "task_outcome": "executed",
        "terminal_harvested": True,
        "session_authority": "terminal",
        "artifact_sha256": "abc123",
    })
    Path(payload["artifacts"]["output"]).write_text("secret result", encoding="utf-8")
    state.write_json_atomic(run_dir / "state.json", payload)
    result = watcher.watch_run(run_dir, timeout_seconds=1, poll_interval_seconds=0.01)
    assert result["signal"] == "complete"
    assert result["artifact_exists"] is True
    assert result["artifact_sha256"] == "abc123"
    assert "secret result" not in json.dumps(result)


@pytest.mark.parametrize("_attempt", range(10))
def test_waiter_wakes_on_attention_transition(tmp_path: Path, _attempt: int) -> None:
    run_dir = make_run(tmp_path)

    def transition() -> None:
        time.sleep(0.03)
        payload = state.load_state(run_dir / "state.json")
        payload.update({"status": "attention_required", "exit_code": 1})
        state.write_json_atomic(run_dir / "state.json", payload)

    thread = threading.Thread(target=transition)
    thread.start()
    result = watcher.watch_run(run_dir, timeout_seconds=1, poll_interval_seconds=0.01)
    thread.join()
    assert result["signal"] == "attention_required"
    assert result["exit_code"] == 1


def test_process_disappearance_is_a_signal_after_grace(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, pid=424242)
    ticks = iter((0.0, 0.0, 0.2, 0.2))
    result = watcher.watch_run(
        run_dir,
        timeout_seconds=10,
        poll_interval_seconds=0.01,
        process_grace_seconds=0.1,
        monotonic=lambda: next(ticks),
        sleep=lambda _: None,
        pid_probe=lambda _: False,
    )
    assert result["signal"] == "process_disappeared"
    assert result["oracle_process_alive"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process API contract")
def test_windows_process_probe_recognizes_current_process() -> None:
    assert watcher.process_is_alive(os.getpid()) is True


def test_timeout_is_explicit_and_does_not_mutate_state(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    before = (run_dir / "state.json").read_bytes()
    result = watcher.watch_run(run_dir, timeout_seconds=0.02, poll_interval_seconds=0.01)
    assert result["signal"] == "observer_timeout"
    assert (run_dir / "state.json").read_bytes() == before
