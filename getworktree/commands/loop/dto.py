"""DTOs for the loop command."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Captured stdout/stderr from a command run inside a sandbox."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    passed: bool
