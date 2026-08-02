#!/usr/bin/env python
"""Block without model polling until one exact Oracle run changes lifecycle."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import chatgpt_oracle_state as STATE


WAKE_STATUSES = {"complete", "failed", "attention_required", "abandoned"}
DEFAULT_TIMEOUT_SECONDS = 4 * 60 * 60


class WatchError(RuntimeError):
    pass


def load_state_shared(path: Path) -> dict[str, Any]:
    """Read without blocking Oracle's atomic os.replace on Windows."""
    if os.name != "nt":
        return STATE.load_state(path)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    get_file_size = kernel32.GetFileSizeEx
    get_file_size.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_longlong)]
    get_file_size.restype = ctypes.c_int
    read_file = kernel32.ReadFile
    read_file.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    read_file.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # SHARE_READ | WRITE | DELETE
        None,
        3,  # OPEN_EXISTING
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), f"cannot open state file: {path}")
    try:
        size = ctypes.c_longlong()
        if not get_file_size(handle, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), f"cannot size state file: {path}")
        if size.value < 0 or size.value > 16 * 1024 * 1024:
            raise WatchError("state file size is outside the safe watcher bound")
        buffer = ctypes.create_string_buffer(size.value)
        read = ctypes.c_uint32()
        if size.value and not read_file(
            handle, buffer, size.value, ctypes.byref(read), None
        ):
            raise OSError(ctypes.get_last_error(), f"cannot read state file: {path}")
        raw = bytes(buffer[: read.value]).decode("utf-8-sig", errors="strict")
    finally:
        close_handle(handle)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise STATE.OracleStateError("STATE_JSON_INVALID", "state file is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != STATE.STATE_SCHEMA:
        raise STATE.OracleStateError(
            "STATE_SCHEMA_INVALID", f"state schema must be {STATE.STATE_SCHEMA}"
        )
    return payload


def default_state_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    return codex_home / "state" / "chatgpt-oracle" / "projects"


def resolve_exact_run_dir(run_dir: Path, *, state_root: Path) -> Path:
    if not run_dir.is_absolute():
        raise WatchError("run directory must be absolute")
    try:
        root = state_root.resolve(strict=True)
        resolved = run_dir.resolve(strict=True)
    except OSError as exc:
        raise WatchError(f"run directory or state root is unavailable: {exc}") from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise WatchError("run directory must stay inside the Oracle projects state root") from exc
    if len(relative.parts) != 3 or relative.parts[1] != "runs":
        raise WatchError("run directory must have the exact <project>/runs/<run> shape")
    state_path = resolved / "state.json"
    state = load_state_shared(state_path)
    if str(state.get("run_id") or "") != resolved.name:
        raise WatchError("state run_id does not match the exact run directory")
    return resolved


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        open_process.restype = ctypes.c_void_p
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        get_exit_code.restype = ctypes.c_int
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # Access denied proves that the PID exists but is not queryable.
            return ctypes.get_last_error() == 5
        try:
            exit_code = ctypes.c_uint32()
            if not get_exit_code(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True


def _process_pid(state: dict[str, Any]) -> int | None:
    watchdog = state.get("host_watchdog")
    if not isinstance(watchdog, dict):
        return None
    try:
        pid = int(watchdog.get("oracle_process_pid"))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _artifact_metadata(state: dict[str, Any]) -> tuple[str | None, bool]:
    artifacts = state.get("artifacts")
    raw_path = artifacts.get("output") if isinstance(artifacts, dict) else None
    output_path = str(raw_path or "").strip()
    return (output_path or None, bool(output_path and Path(output_path).is_file()))


def build_signal(
    state: dict[str, Any],
    *,
    run_dir: Path,
    signal: str,
    pid_alive: bool | None,
) -> dict[str, Any]:
    output_path, output_exists = _artifact_metadata(state)
    pid = _process_pid(state)
    return {
        "schema": "codex.chatgpt.oracle-watch-signal/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "signal": signal,
        "run_dir": str(run_dir),
        "run_id": str(state.get("run_id") or ""),
        "status": str(state.get("status") or ""),
        "exit_code": state.get("exit_code"),
        "transport_status": str(state.get("transport_status") or ""),
        "task_outcome": str(state.get("task_outcome") or ""),
        "terminal_harvested": state.get("terminal_harvested") is True,
        "session_authority": str(state.get("session_authority") or ""),
        "artifact_path": output_path,
        "artifact_exists": output_exists,
        "artifact_sha256": state.get("artifact_sha256"),
        "oracle_process_pid": pid,
        "oracle_process_alive": pid_alive,
    }


def watch_run(
    run_dir: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = 1.0,
    process_grace_seconds: float = 15.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    pid_probe: Callable[[int], bool] = process_is_alive,
) -> dict[str, Any]:
    if timeout_seconds <= 0 or poll_interval_seconds <= 0 or process_grace_seconds < 0:
        raise WatchError("timeouts and poll interval must be positive")
    state_path = run_dir / "state.json"
    deadline = monotonic() + timeout_seconds
    missing_pid: int | None = None
    missing_since: float | None = None
    last_state: dict[str, Any] | None = None

    while True:
        state = load_state_shared(state_path)
        last_state = state
        status = str(state.get("status") or "")
        pid = _process_pid(state)
        alive = pid_probe(pid) if pid is not None else None
        if status in WAKE_STATUSES:
            return build_signal(state, run_dir=run_dir, signal=status, pid_alive=alive)

        now = monotonic()
        if pid is not None and alive is False:
            if missing_pid != pid:
                missing_pid = pid
                missing_since = now
            elif missing_since is not None and now - missing_since >= process_grace_seconds:
                # Re-read once after the grace window so a concurrent terminal
                # state write always wins over process disappearance.
                state = load_state_shared(state_path)
                status = str(state.get("status") or "")
                if status in WAKE_STATUSES:
                    return build_signal(state, run_dir=run_dir, signal=status, pid_alive=False)
                if _process_pid(state) == pid and not pid_probe(pid):
                    return build_signal(
                        state, run_dir=run_dir, signal="process_disappeared", pid_alive=False
                    )
        else:
            missing_pid = None
            missing_since = None

        if now >= deadline:
            assert last_state is not None
            return build_signal(
                last_state, run_dir=run_dir, signal="observer_timeout", pid_alive=alive
            )
        sleep(min(poll_interval_seconds, max(0.0, deadline - now)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wait silently for one exact Oracle run lifecycle signal."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--process-grace-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)
    try:
        run_dir = resolve_exact_run_dir(args.run_dir, state_root=args.state_root)
        result = watch_run(
            run_dir,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            process_grace_seconds=args.process_grace_seconds,
        )
    except (WatchError, STATE.OracleStateError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 3 if result["signal"] == "observer_timeout" else 0


if __name__ == "__main__":
    sys.exit(main())
