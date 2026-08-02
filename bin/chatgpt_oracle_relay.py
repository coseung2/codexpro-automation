#!/usr/bin/env python
"""Run or observe Oracle without a waiting model, then resume one Codex task."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import chatgpt_oracle_state as ORACLE_STATE
import chatgpt_oracle_watch as ORACLE_WATCH


SCHEMA = "codex.chatgpt.oracle-event-relay/v1"
THREAD_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
ALLOWED_SCRIPTS = {
    "chatgpt_oracle_dispatch.py",
    "chatgpt_oracle_comprehensive.py",
    "chatgpt_oracle_multi.py",
    "run_chatgpt_oracle.py",
    "run_chatgpt_pro.py",
    "run_pro_plan_handoff.py",
}
BUSY_MARKERS = ("already running", "active turn", "session is busy", "thread is busy", "locked")


class RelayError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).resolve()


def relay_root() -> Path:
    return codex_home() / "state" / "chatgpt-oracle" / "relays"


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_relay(relay_dir: Path) -> dict[str, Any]:
    resolved = relay_dir.resolve(strict=True)
    try:
        resolved.relative_to(relay_root().resolve(strict=True))
    except ValueError as exc:
        raise RelayError("relay directory must stay inside the Codex Oracle relay root") from exc
    payload = json.loads((resolved / "state.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise RelayError("relay state schema is invalid")
    return payload


def validate_thread_id(value: str | None) -> str:
    thread_id = str(value or os.environ.get("CODEX_THREAD_ID") or "").strip()
    if not THREAD_ID_RE.fullmatch(thread_id):
        raise RelayError("a valid CODEX_THREAD_ID is required")
    return thread_id


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def validate_oracle_command(argv: Sequence[str], *, home: Path | None = None) -> list[str]:
    command = list(argv)
    if command and command[0] == "--":
        command = command[1:]
    if len(command) < 2:
        raise RelayError("an installed Python Oracle command is required")
    executable = Path(shutil.which(command[0]) or command[0]).resolve(strict=True)
    if not re.fullmatch(r"(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?", executable.name, re.I):
        raise RelayError("relay commands must use Python directly")
    script = Path(command[1]).resolve(strict=True)
    base = (home or codex_home()).resolve(strict=True)
    roots = ((base / "bin").resolve(strict=True), (base / "skills").resolve(strict=True))
    if not _inside(script, roots) or script.name not in ALLOWED_SCRIPTS:
        raise RelayError("command script is not an installed Oracle entrypoint")
    if "--dry-run" in command[2:]:
        raise RelayError("dry-run must execute synchronously before relay registration")
    command[0] = str(executable)
    command[1] = str(script)
    return command


def create_relay(
    *,
    kind: str,
    thread_id: str,
    cwd: Path,
    command: Sequence[str] | None = None,
    run_dir: Path | None = None,
) -> Path:
    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_dir():
        raise RelayError("cwd must be an existing directory")
    root = relay_root()
    root.mkdir(parents=True, exist_ok=True)
    relay_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    directory = root / relay_id
    directory.mkdir()
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "relay_id": relay_id,
        "kind": kind,
        "status": "prepared",
        "thread_id": validate_thread_id(thread_id),
        "cwd": str(resolved_cwd),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "command": list(command or []),
        "run_dir": str(run_dir.resolve(strict=True)) if run_dir else None,
        "command_exit_code": None,
        "signal": None,
        "wake_attempts": 0,
        "wake_exit_code": None,
    }
    write_json_atomic(directory / "state.json", payload)
    return directory


def _hidden_process_kwargs(*, detached: bool = False) -> dict[str, Any]:
    if os.name != "nt":
        return {"start_new_session": True} if detached else {}
    flags = subprocess.CREATE_NO_WINDOW
    if detached:
        flags |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": flags, "startupinfo": startupinfo}


def spawn_relay(relay_dir: Path) -> int:
    daemon_stdout = (relay_dir / "daemon.stdout.log").open("ab")
    daemon_stderr = (relay_dir / "daemon.stderr.log").open("ab")
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "run", "--relay-dir", str(relay_dir)],
        stdin=subprocess.DEVNULL,
        stdout=daemon_stdout,
        stderr=daemon_stderr,
        close_fds=True,
        **_hidden_process_kwargs(detached=True),
    )
    daemon_stdout.close()
    daemon_stderr.close()
    return int(process.pid)


def run_allowed_command(payload: dict[str, Any], relay_dir: Path) -> dict[str, Any]:
    command = validate_oracle_command(payload.get("command") or [])
    with (relay_dir / "command.stdout.log").open("wb") as stdout, (
        relay_dir / "command.stderr.log"
    ).open("wb") as stderr:
        completed = subprocess.run(
            command,
            cwd=str(payload["cwd"]),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            check=False,
            **_hidden_process_kwargs(),
        )
    return {"signal": "command_exited", "command_exit_code": int(completed.returncode)}


def run_exact_watch(payload: dict[str, Any], _relay_dir: Path) -> dict[str, Any]:
    run_dir = ORACLE_WATCH.resolve_exact_run_dir(
        Path(str(payload["run_dir"])), state_root=ORACLE_WATCH.default_state_root()
    )
    signal = ORACLE_WATCH.watch_run(run_dir)
    return {"signal": signal, "command_exit_code": None}


def _codex_invocation(arguments: Sequence[str]) -> list[str]:
    configured = os.environ.get("CODEX_CLI_PATH")
    if os.name == "nt":
        located = configured or shutil.which("codex.cmd") or shutil.which("codex")
        if not located:
            raise RelayError("Codex CLI executable is unavailable")
        command_line = subprocess.list2cmdline([str(Path(located).resolve(strict=True)), *arguments])
        return [os.environ.get("ComSpec") or "cmd.exe", "/d", "/s", "/c", command_line]
    located = configured or shutil.which("codex")
    if not located:
        raise RelayError("Codex CLI executable is unavailable")
    return [str(Path(located).resolve(strict=True)), *arguments]


def wake_prompt(payload: dict[str, Any], relay_dir: Path) -> str:
    return (
        "ORACLE_EVENT_RELAY_WAKE\n"
        "A deterministic local relay observed the Oracle command or exact-run lifecycle event. "
        "This is the only wake-up signal; no model waited or reviewed in the background.\n"
        f"relay_dir: {relay_dir}\n"
        f"relay_id: {payload['relay_id']}\n"
        f"relay_kind: {payload['kind']}\n"
        f"command_exit_code: {payload.get('command_exit_code')}\n"
        "Read relay state and the exact Oracle run/workflow metadata now. If terminal output exists, "
        "the main task must directly inspect artifacts, diffs, tests, and quality. If attention or "
        "submission uncertainty is present, preserve exact ownership and follow recovery rules. "
        "Do not create a Luna tracking worker, do not resubmit, and do not treat this prompt itself "
        "as proof of task completion."
    )


def wake_thread(payload: dict[str, Any], relay_dir: Path) -> tuple[int, str]:
    command = _codex_invocation([
        "exec",
        "resume",
        "--all",
        "--json",
        str(payload["thread_id"]),
        "-",
    ])
    stderr_path = relay_dir / "wake.stderr.log"
    with (relay_dir / "wake.stdout.log").open("ab") as stdout:
        completed = subprocess.run(
            command,
            cwd=str(payload["cwd"]),
            input=wake_prompt(payload, relay_dir).encode("utf-8"),
            stdout=stdout,
            stderr=subprocess.PIPE,
            check=False,
            **_hidden_process_kwargs(),
        )
    current_stderr = bytes(completed.stderr or b"")
    with stderr_path.open("ab") as stderr:
        stderr.write(current_stderr)
    error = current_stderr.decode("utf-8", errors="replace")[-4000:]
    return int(completed.returncode), error


def execute_relay(
    relay_dir: Path,
    *,
    command_runner: Callable[[dict[str, Any], Path], dict[str, Any]] = run_allowed_command,
    watch_runner: Callable[[dict[str, Any], Path], dict[str, Any]] = run_exact_watch,
    waker: Callable[[dict[str, Any], Path], tuple[int, str]] = wake_thread,
    initial_wake_delay_seconds: float = 3.0,
    retry_window_seconds: float = 10 * 60,
) -> dict[str, Any]:
    relay_dir = relay_dir.resolve(strict=True)
    payload = read_relay(relay_dir)
    lock_path = relay_dir / "runner.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError as exc:
        raise RelayError("relay runner already owns this relay") from exc
    if payload.get("status") != "prepared":
        raise RelayError("relay is not prepared")
    payload.update({"status": "running", "updated_at": utc_now()})
    write_json_atomic(relay_dir / "state.json", payload)

    try:
        result = (
            command_runner(payload, relay_dir)
            if payload["kind"] == "command"
            else watch_runner(payload, relay_dir)
        )
    except Exception as exc:  # The task must still wake on local relay failure.
        result = {
            "signal": "relay_execution_error",
            "command_exit_code": None,
            "relay_error": f"{type(exc).__name__}: {exc}",
        }
    payload.update(result)
    payload.update({"status": "wake_pending", "updated_at": utc_now()})
    write_json_atomic(relay_dir / "state.json", payload)
    time.sleep(max(0.0, initial_wake_delay_seconds))

    deadline = time.monotonic() + retry_window_seconds
    while True:
        payload["wake_attempts"] = int(payload.get("wake_attempts") or 0) + 1
        payload.update({"status": "wake_running", "updated_at": utc_now()})
        write_json_atomic(relay_dir / "state.json", payload)
        try:
            exit_code, error = waker(payload, relay_dir)
        except Exception as exc:
            exit_code, error = 127, f"{type(exc).__name__}: {exc}"
        payload["wake_exit_code"] = exit_code
        if exit_code == 0:
            payload.update({"status": "woken", "updated_at": utc_now()})
            write_json_atomic(relay_dir / "state.json", payload)
            return payload
        busy = any(marker in error.casefold() for marker in BUSY_MARKERS)
        if not busy or time.monotonic() >= deadline:
            payload.update({"status": "wake_failed", "wake_error_tail": error[-1000:], "updated_at": utc_now()})
            write_json_atomic(relay_dir / "state.json", payload)
            return payload
        payload.update({"status": "wake_retry", "updated_at": utc_now()})
        write_json_atomic(relay_dir / "state.json", payload)
        time.sleep(5.0)


def _print_started(relay_dir: Path, pid: int) -> None:
    print(json.dumps({"ok": True, "relay_dir": str(relay_dir), "relay_pid": pid}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zero-model-wait Oracle event relay.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    command_parser = subparsers.add_parser("start-command")
    command_parser.add_argument("--thread-id")
    command_parser.add_argument("--cwd", type=Path, required=True)
    command_parser.add_argument("command", nargs=argparse.REMAINDER)

    watch_parser = subparsers.add_parser("start-watch")
    watch_parser.add_argument("--thread-id")
    watch_parser.add_argument("--cwd", type=Path, required=True)
    watch_parser.add_argument("--run-dir", type=Path, required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--relay-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.action == "run":
            result = execute_relay(args.relay_dir)
            return 0 if result["status"] == "woken" else 4
        thread_id = validate_thread_id(args.thread_id)
        if args.action == "start-command":
            command = validate_oracle_command(args.command)
            directory = create_relay(kind="command", thread_id=thread_id, cwd=args.cwd, command=command)
        else:
            run_dir = ORACLE_WATCH.resolve_exact_run_dir(
                args.run_dir, state_root=ORACLE_WATCH.default_state_root()
            )
            directory = create_relay(kind="watch", thread_id=thread_id, cwd=args.cwd, run_dir=run_dir)
        _print_started(directory, spawn_relay(directory))
        return 0
    except (RelayError, ORACLE_STATE.OracleStateError, ORACLE_WATCH.WatchError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
