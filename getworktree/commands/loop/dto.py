"""DTOs for the loop command."""

from __future__ import annotations

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """Captured stdout/stderr from a command run inside a sandbox."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    command: str
    returncode: int
    stdout: str
    stderr: str
    passed: bool
