"""GitHub Copilot CLI direct-mutation agent adapter."""

from __future__ import annotations

import json
import os
import subprocess

from worktree.core.agents.base import AgentRequest
from worktree.core.agents.cli_mutation import (
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
)

COPILOT_TOKEN_ENVS = ("GH_TOKEN", "GITHUB_TOKEN")


def resolve_copilot_token(env: dict[str, str] | None = None) -> str | None:
    """Resolve the Copilot auth token from the environment."""
    environ = env if env is not None else os.environ
    for name in COPILOT_TOKEN_ENVS:
        key = environ.get(name)
        if key is not None and key.strip():
            return key.strip()
    return None


def _extract_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content
        response = value.get("response")
        if isinstance(response, str):
            return response
        message = value.get("message")
        if isinstance(message, dict):
            nested = message.get("content")
            if isinstance(nested, str):
                return nested
    return None


def _parse_jsonl(stdout_text: str) -> tuple[str | None, int | None, str | None]:
    assistant_text: str | None = None
    result_exit_code: int | None = None
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            return None, None, f"invalid JSONL from Copilot CLI: {exc}"
        if not isinstance(data, dict):
            continue
        event_type = data.get("type")
        if event_type == "assistant.message":
            payload = data.get("data")
            text = _extract_text(payload)
            if text is not None:
                assistant_text = text
        elif event_type == "result":
            payload = data.get("data")
            if isinstance(payload, dict):
                raw_exit = payload.get("exitCode")
                if raw_exit is None:
                    raw_exit = payload.get("exit_code")
                if isinstance(raw_exit, int):
                    result_exit_code = raw_exit
                elif isinstance(raw_exit, str) and raw_exit.isdigit():
                    result_exit_code = int(raw_exit)
                text = _extract_text(payload)
                if text is not None:
                    assistant_text = assistant_text or text
    return assistant_text, result_exit_code, None


def default_copilot_run(request: CliMutationRunRequest) -> CliMutationOutcome:
    """Invoke `gh copilot` and map its JSONL stream into an outcome."""
    token = resolve_copilot_token()
    if token is None:
        return CliMutationOutcome(
            status="error",
            error_detail="missing GH_TOKEN or GITHUB_TOKEN",
        )

    # Keep prompt off argv to avoid OS argument length limits on large payloads.
    cmd = [
        "gh",
        "copilot",
        "--",
        "-p",
        "",
        "--output-format",
        "json",
        "--silent",
        "--allow-all-tools",
        "--allow-all-paths",
        "--allow-all-urls",
    ]
    env = os.environ.copy()
    env.setdefault("GH_TOKEN", token)
    env.setdefault("GITHUB_TOKEN", token)
    if request.model:
        env["COPILOT_MODEL"] = request.model

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(request.sandbox_path),
            env=env,
            input=request.prompt.encode("utf-8"),
            capture_output=True,
            text=False,
            shell=False,
            timeout=request.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CliMutationOutcome(status="timeout")
    except FileNotFoundError as exc:
        return CliMutationOutcome(
            status="error",
            error_detail=(
                f"gh is not installed or not on PATH: {exc}. Fix: install the GitHub CLI (https://cli.github.com)"
            ),
        )
    except OSError as exc:
        return CliMutationOutcome(status="error", error_detail=str(exc))

    stdout_text = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (completed.stderr or b"").decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr_text.strip() or stdout_text.strip() or f"exit {completed.returncode}"
        return CliMutationOutcome(status="error", error_detail=detail)

    assistant_text, exit_code, parse_error = _parse_jsonl(stdout_text)
    if parse_error is not None:
        return CliMutationOutcome(status="error", error_detail=parse_error)
    if exit_code is not None and exit_code != 0:
        return CliMutationOutcome(
            status="error",
            error_detail=f"Copilot CLI result exit code {exit_code}",
            result_text=assistant_text,
        )
    if assistant_text is None and not stdout_text.strip():
        return CliMutationOutcome(status="error", error_detail="empty Copilot CLI output")
    if assistant_text is None:
        assistant_text = stdout_text.strip() or None
    return CliMutationOutcome(status="finished", result_text=assistant_text)


class CopilotAgentAdapter(CliDirectMutationAdapter):
    """Run GitHub Copilot through the shared direct-mutation base."""

    def __init__(self, *, run_fn: CliMutationRunFn | None = None) -> None:
        super().__init__(run_fn=run_fn)

    def _preflight(self, request: AgentRequest) -> str | None:
        if resolve_copilot_token() is None:
            return "missing GH_TOKEN or GITHUB_TOKEN. Fix: export GH_TOKEN=..."
        return None

    def _provider_name(self) -> str:
        return "copilot"

    def _default_run(self, request: CliMutationRunRequest) -> CliMutationOutcome:
        return default_copilot_run(request)
