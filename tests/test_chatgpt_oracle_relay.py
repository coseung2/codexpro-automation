import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import chatgpt_oracle_relay as relay  # noqa: E402


THREAD_ID = "019fbd08-1d19-7530-a854-f27636bfb91b"


def installed_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home = tmp_path / ".codex"
    script = home / "bin" / "chatgpt_oracle_dispatch.py"
    script.parent.mkdir(parents=True)
    (home / "skills").mkdir()
    script.write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home, script


def test_validate_command_accepts_only_installed_oracle_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    command = relay.validate_oracle_command([sys.executable, str(script), "--mode", "orchestrator"], home=home)
    assert Path(command[1]) == script.resolve()
    outside = tmp_path / "chatgpt_oracle_dispatch.py"
    outside.write_text("", encoding="utf-8")
    with pytest.raises(relay.RelayError, match="installed Oracle entrypoint"):
        relay.validate_oracle_command([sys.executable, str(outside)], home=home)


def test_validate_command_rejects_dry_run_and_arbitrary_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    with pytest.raises(relay.RelayError, match="dry-run"):
        relay.validate_oracle_command([sys.executable, str(script), "--dry-run"], home=home)
    with pytest.raises(relay.RelayError, match="Python directly"):
        relay.validate_oracle_command([str(script), "ignored"], home=home)


def test_execute_relay_waits_without_model_then_wakes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    command = relay.validate_oracle_command([sys.executable, str(script)], home=home)
    directory = relay.create_relay(
        kind="command", thread_id=THREAD_ID, cwd=cwd, command=command
    )
    calls: list[str] = []

    def command_runner(payload: dict, relay_dir: Path) -> dict:
        calls.append("oracle")
        assert payload["status"] == "running"
        return {"signal": "command_exited", "command_exit_code": 0}

    def waker(payload: dict, relay_dir: Path) -> tuple[int, str]:
        calls.append("wake")
        assert payload["status"] == "wake_running"
        assert "ORACLE_EVENT_RELAY_WAKE" in relay.wake_prompt(payload, relay_dir)
        return 0, ""

    result = relay.execute_relay(
        directory,
        command_runner=command_runner,
        waker=waker,
        initial_wake_delay_seconds=0,
    )
    assert calls == ["oracle", "wake"]
    assert result["status"] == "woken"
    assert result["wake_attempts"] == 1
    assert result["command_exit_code"] == 0


def test_relay_state_contains_no_oracle_output_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    directory = relay.create_relay(
        kind="command",
        thread_id=THREAD_ID,
        cwd=cwd,
        command=relay.validate_oracle_command([sys.executable, str(script)], home=home),
    )

    def command_runner(_payload: dict, relay_dir: Path) -> dict:
        (relay_dir / "command.stdout.log").write_text("PRIVATE_ORACLE_RESULT", encoding="utf-8")
        return {"signal": "command_exited", "command_exit_code": 0}

    result = relay.execute_relay(
        directory,
        command_runner=command_runner,
        waker=lambda _payload, _directory: (0, ""),
        initial_wake_delay_seconds=0,
    )
    state_text = (directory / "state.json").read_text(encoding="utf-8")
    prompt = relay.wake_prompt(result, directory)
    assert "PRIVATE_ORACLE_RESULT" not in state_text
    assert "PRIVATE_ORACLE_RESULT" not in prompt


def test_oracle_launch_failure_still_attempts_one_wake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    directory = relay.create_relay(
        kind="command",
        thread_id=THREAD_ID,
        cwd=cwd,
        command=relay.validate_oracle_command([sys.executable, str(script)], home=home),
    )
    wake_calls = []

    def fail(_payload: dict, _directory: Path) -> dict:
        raise OSError("launch failed")

    def wake(payload: dict, _directory: Path) -> tuple[int, str]:
        wake_calls.append(payload["signal"])
        return 0, ""

    result = relay.execute_relay(
        directory,
        command_runner=fail,
        waker=wake,
        initial_wake_delay_seconds=0,
    )
    assert wake_calls == ["relay_execution_error"]
    assert result["status"] == "woken"
    assert result["relay_error"] == "OSError: launch failed"


def test_duplicate_relay_runner_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    directory = relay.create_relay(
        kind="command",
        thread_id=THREAD_ID,
        cwd=cwd,
        command=relay.validate_oracle_command([sys.executable, str(script)], home=home),
    )
    (directory / "runner.lock").write_text("owned", encoding="utf-8")
    with pytest.raises(relay.RelayError, match="already owns"):
        relay.execute_relay(directory, initial_wake_delay_seconds=0)


def test_wake_uses_codex_exec_resume_with_prompt_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    directory = relay.create_relay(
        kind="command",
        thread_id=THREAD_ID,
        cwd=cwd,
        command=relay.validate_oracle_command([sys.executable, str(script)], home=home),
    )
    payload = relay.read_relay(directory)
    payload.update({"signal": "command_exited", "command_exit_code": 0})
    captured = {}

    class Completed:
        returncode = 0
        stderr = b""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return Completed()

    monkeypatch.setattr(relay, "_codex_executable", lambda: "codex.exe")
    monkeypatch.setattr(relay.subprocess, "run", fake_run)
    exit_code, _error = relay.wake_thread(payload, directory)
    assert exit_code == 0
    assert captured["command"] == [
        "codex.exe", "exec", "resume", "--all", "--json", THREAD_ID, "-"
    ]
    assert b"ORACLE_EVENT_RELAY_WAKE" in captured["input"]


def test_relay_state_is_bound_to_valid_thread_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, script = installed_tree(tmp_path, monkeypatch)
    cwd = tmp_path / "project"
    cwd.mkdir()
    with pytest.raises(relay.RelayError, match="CODEX_THREAD_ID"):
        relay.create_relay(
            kind="command",
            thread_id="not-a-thread",
            cwd=cwd,
            command=relay.validate_oracle_command([sys.executable, str(script)], home=home),
        )
