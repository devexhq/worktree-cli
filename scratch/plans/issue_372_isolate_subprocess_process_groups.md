# Implementation Plan: Isolate Subprocess Process Groups to Prevent Orphaned Background Processes (Issue #372)

## Goal / User Story

As a developer running tasks or workflows that spawn child processes (compilers, dev servers, test runners, background workers), I want step execution and direct-mutation agent adapters to run inside dedicated, isolated process groups so that step timeouts, cancellations, and `KeyboardInterrupt` (`SIGINT` / Ctrl+C) terminate the entire process tree rather than leaving orphaned background processes consuming ports, file locks, CPU, and memory.

This implementation plan delivers:
1. Isolated process group creation for all step executions and agent CLI adapters (`start_new_session=True` on POSIX, `CREATE_NEW_PROCESS_GROUP` on Windows).
2. Two-stage cascading process tree termination on timeout (`SIGTERM` -> 2.0s grace period -> `SIGKILL`).
3. Process tree cleanup on cancellation (`KeyboardInterrupt` / SIGINT) before sandbox cleanup routines run.
4. Windows support via `taskkill /PID <pid> /T /F` fallback and process tree termination.
5. Centralized, DRY process management utilities in `src/worktree/common/process.py` and comprehensive test coverage in `tests/core/step/test_process_group.py`.

---

## Architecture & Design Analysis

### Process Tree & Isolation Flow

```mermaid
graph TD
    subgraph Host Orchestrator
        ENGINE[Runtime Engine / run_steps]
        REGISTRY[ProcessRegistry: Active Process Tracker]
        ENGINE -->|Registers active child| REGISTRY
    end

    subgraph Step & Agent Execution
        RUNNER[StepExecution / Agent Adapter]
        RUNNER -->|spawn with start_new_session=True / PGID| LEADER[Process Group Leader: Child PID]
    end

    subgraph Isolated Process Group
        LEADER -->|spawns| WORKER1[Grandchild: Worker Process]
        LEADER -->|spawns & detaches| WORKER2[Grandchild: Background Daemon / Server]
    end

    subgraph Cascading Termination Lifecycle
        TIMEOUT[Timeout or KeyboardInterrupt] -->|Stage 1: SIGTERM to -pgid| LEADER
        TIMEOUT -->|Stage 1: SIGTERM to -pgid| WORKER1
        TIMEOUT -->|Stage 1: SIGTERM to -pgid| WORKER2
        LEADER -.->|Grace Period 2.0s: Poll os.killpg(pgid, 0)| WAIT[Check if group empty]
        WAIT -->|If still alive after 2.0s| STAGE2[Stage 2: SIGKILL to -pgid & proc.kill()]
    end
```

### Key Design Principles

1. **Explicit PGID Capture**:
   - On POSIX with `start_new_session=True`, the child process's PGID equals its PID (`pgid = proc.pid`).
   - If the main child process detaches workers and exits early (e.g. `sh -c "sleep 100 &"`), calling `os.getpgid(proc.pid)` after `proc` exits would fail with `ProcessLookupError`.
   - By recording `pgid = proc.pid` at spawn time, we retain the process group identifier and can signal the entire group even if the initial leader has already terminated.

2. **Cascading Escalation Algorithm**:
   - **Stage 1 (`SIGTERM`)**: Send `os.killpg(pgid, signal.SIGTERM)` (or on Windows, `proc.terminate()`).
   - **Grace Period Polling**: Poll `os.killpg(pgid, 0)` every 50ms up to `grace_seconds` (default 2.0s). If `os.killpg(pgid, 0)` raises `ProcessLookupError`, all processes in the group have exited cleanly.
   - **Stage 2 (`SIGKILL`)**: If any processes in the group remain alive after the grace period, send `os.killpg(pgid, signal.SIGKILL)` on POSIX (or `taskkill /PID <pid> /T /F` on Windows) and reap `proc.wait(timeout=1.0)`.

3. **Interruption & Cancellation Safety**:
   - During `run_steps` or `StepExecution._run_process`, if `KeyboardInterrupt` occurs, child processes are in isolated sessions and will not be killed automatically by the terminal's foreground SIGINT.
   - The execution wrappers catch `BaseException` and invoke `terminate_process_tree(proc, grace_seconds=0.5)` in a `finally:` block so no orphans survive.
   - `ProcessRegistry` tracks active processes and provides `terminate_all()` as a backstop before sandbox cleanup runs.

4. **DRY Architecture (Code Conventions Compliance)**:
   - Shared process execution and termination logic is centralized in `src/worktree/common/process.py`.
   - `StepExecution` (`src/worktree/core/step/runner.py`), `GeminiAgentAdapter` (`src/worktree/core/agents/gemini.py`), `CopilotAgentAdapter` (`src/worktree/core/agents/copilot.py`), and `LocalAgentAdapter` (`src/worktree/core/agents/local.py`) reuse these shared utilities without duplication.

---

## User Review Required

> [!IMPORTANT]
> **Timeout Grace Period Duration**:
> The specification sets a 2-second grace period for `SIGTERM` before escalating to `SIGKILL` (`GRACE_PERIOD_SECONDS = 2.0`). For urgent interruptions (like `KeyboardInterrupt`), a shorter grace period (e.g. 0.5s) will be used to ensure immediate CLI responsiveness while giving processes a moment to flush logs and close file handles.

> [!NOTE]
> **Windows Process Tree Handling**:
> On Windows where POSIX process groups do not exist, `subprocess.CREATE_NEW_PROCESS_GROUP` is set at spawn, and tree termination is handled via `proc.terminate()` followed by `taskkill /PID <pid> /T /F` and `proc.kill()`.

---

## Proposed Changes

### Component: `src/worktree/common/`

#### [NEW] `src/worktree/common/process.py`
Create reusable, cross-platform process isolation and termination utilities:
- `DEFAULT_GRACE_PERIOD_SECONDS: float = 2.0`
- `get_isolated_process_kwargs() -> dict[str, Any]`: Returns `{"start_new_session": True}` on POSIX, or `{"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}` on Windows.
- `is_process_group_alive(pgid: int) -> bool`: Checks if any processes in `pgid` are alive via `os.killpg(pgid, 0)`.
- `terminate_process_tree(proc: subprocess.Popen[Any] | int, *, grace_seconds: float = DEFAULT_GRACE_PERIOD_SECONDS, pgid: int | None = None) -> None`: Cascading `SIGTERM` -> grace period -> `SIGKILL` / `taskkill /T /F`.
- `run_isolated_process(cmd, *, cwd, env, input_data, timeout_seconds, shell, text, grace_seconds) -> subprocess.CompletedProcess[Any]`: Isolated runner that handles process groups and cascading termination on `TimeoutExpired` or `BaseException`.
- `ProcessRegistry`: Thread-safe registry tracking active `Popen` instances to guarantee zero orphan processes on run cancellation or unexpected engine exits.

```python
"""Cross-platform subprocess process group isolation and cascading tree termination."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_GRACE_PERIOD_SECONDS: float = 2.0


def get_isolated_process_kwargs() -> dict[str, Any]:
    """Return platform-specific kwargs for subprocess isolation."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def is_process_group_alive(pgid: int) -> bool:
    """Return True if at least one process in the POSIX process group is alive."""
    if not hasattr(os, "killpg"):
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def _poll_posix_group_exit(pgid: int, grace_seconds: float) -> bool:
    """Poll process group until all processes exit or grace period expires."""
    deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < deadline:
        if not is_process_group_alive(pgid):
            return True
        time.sleep(0.05)
    return not is_process_group_alive(pgid)


def _terminate_posix_group(
    pid: int,
    pgid: int,
    proc: subprocess.Popen[Any] | None,
    grace_seconds: float,
) -> None:
    """Cascading SIGTERM -> grace period -> SIGKILL on POSIX process group."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass

    exited = _poll_posix_group_exit(pgid, grace_seconds)
    if not exited:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass


def _terminate_windows_tree(
    pid: int,
    proc: subprocess.Popen[Any] | None,
    grace_seconds: float,
) -> None:
    """Graceful termination with taskkill /T /F fallback on Windows."""
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=max(0.1, grace_seconds))
            return
        except Exception:
            pass

    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=5.0,
            check=False,
        )
    except Exception:
        pass

    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass


def terminate_process_tree(
    proc: subprocess.Popen[Any] | int,
    *,
    grace_seconds: float = DEFAULT_GRACE_PERIOD_SECONDS,
    pgid: int | None = None,
) -> None:
    """Terminate or kill a process and its entire child process tree."""
    pid = proc.pid if isinstance(proc, subprocess.Popen) else proc
    popened = proc if isinstance(proc, subprocess.Popen) else None
    resolved_pgid = pgid if pgid is not None else pid

    if sys.platform != "win32" and hasattr(os, "killpg"):
        _terminate_posix_group(pid, resolved_pgid, popened, grace_seconds)
    else:
        _terminate_windows_tree(pid, popened, grace_seconds)
```

---

### Component: `src/worktree/core/step/`

#### [MODIFY] `src/worktree/core/step/runner.py`
- Import `get_isolated_process_kwargs`, `terminate_process_tree`, and `process_registry` from `worktree.common.process`.
- Update `_run_process`:
  - Pass `**get_isolated_process_kwargs()` to `subprocess.Popen`.
  - Capture `pgid = proc.pid`.
  - Register `proc` in `process_registry`.
  - On `subprocess.TimeoutExpired`: call `terminate_process_tree(proc, grace_seconds=2.0, pgid=pgid)`.
  - Catch `BaseException` (for `KeyboardInterrupt`) and ensure `terminate_process_tree(proc, grace_seconds=0.5, pgid=pgid)` is called before re-raising.
  - In `finally:` unregister `proc` and verify `proc.poll() is not None` or clean up.
- Remove legacy `_terminate_process_tree` method on `StepExecution` in favor of the shared `common.process` implementation.

---

### Component: `src/worktree/core/agents/`

#### [MODIFY] `src/worktree/core/agents/gemini.py`
- Update `default_gemini_run` to use `run_isolated_process` instead of raw `subprocess.run`, ensuring that Gemini CLI and any tools or sub-shells it spawns run in an isolated process group and are reaped on timeout or interrupt.

#### [MODIFY] `src/worktree/core/agents/copilot.py`
- Update `default_copilot_run` to use `run_isolated_process` instead of raw `subprocess.run`.

#### [MODIFY] `src/worktree/core/agents/local.py`
- Update `LocalAgentAdapter.propose_fix` to use `run_isolated_process` instead of raw `subprocess.run`.

---

### Component: `src/worktree/core/runtime/`

#### [MODIFY] `src/worktree/core/runtime/engine.py`
- In `_run_step_loop` and `run_steps`:
  - On `KeyboardInterrupt` / cancellation, call `process_registry.terminate_all(grace_seconds=0.5)` to ensure any background children spawned across all steps are terminated before sandbox diff or worktree cleanup runs.

---

### Component: `tests/core/step/`

#### [NEW] `tests/core/step/test_process_group.py`
- `test_detached_background_child_killed_on_timeout`: Spawns a shell script that starts a detached background process (e.g. `python3 -c "import time; time.sleep(100)" & sleep 2`), verifies the detached child is killed when step times out.
- `test_sigterm_escalation_to_sigkill`: Spawns a script that traps/ignores `SIGTERM` and verifies escalation to `SIGKILL` after grace period.
- `test_keyboard_interrupt_terminates_child_process_tree`: Simulates `KeyboardInterrupt` and verifies child processes are terminated immediately.
- `test_process_registry_terminate_all`: Tests registration, unregistration, and `terminate_all()` on active processes.
- `test_windows_tree_termination_fallback`: Mocks Windows environment to verify `taskkill /T /F` fallback path.

#### [MODIFY] `tests/core/step/test_runner.py`
- Update timeout assertions to confirm process group cleanup behavior.

#### [MODIFY] `tests/core/agents/test_gemini_agent.py`, `test_copilot_agent.py`, `test_cli_mutation_agent.py`
- Verify timeout handling in agent adapters correctly triggers isolated process group termination.

---

## Verification Plan

### Automated Tests
Run all verification gates to confirm 100% compliance with repository standards:
```bash
# 1. Run unit test suite with coverage check (>= 80%)
uv run inv test -c

# 2. Run new dedicated process group unit tests
uv run pytest tests/core/step/test_process_group.py -vv

# 3. Format and lint checks
uv run ruff format --check .
uv run ruff check .

# 4. Type check (0 errors required)
uv run basedpyright src --level error

# 5. Cognitive complexity gate on all modified files (max complexity <= 10)
uv run inv complexity --paths src/worktree/common/process.py,src/worktree/core/step/runner.py,src/worktree/core/runtime/engine.py,src/worktree/core/agents/gemini.py,src/worktree/core/agents/copilot.py,src/worktree/core/agents/local.py --plain --failed
```

### Manual Verification
1. Execute a blueprint step running `sh -c "sleep 60 & sleep 1"` with `timeout_seconds: 1`.
2. Inspect `ps aux | grep sleep` to confirm that no background `sleep 60` process remains running after step timeout.
3. Execute a blueprint step with a long-running command, press `Ctrl+C` (`KeyboardInterrupt`), and verify all subprocesses exit cleanly and sandbox cleanup succeeds without locked file errors.
