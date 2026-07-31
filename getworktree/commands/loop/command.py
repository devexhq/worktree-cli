"""Execute target commands inside an isolated background sandbox.

Captures failure diagnostics into structured payload blocks for downstream tools.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from getworktree.commands.loop.models import ExecutionResult
from getworktree.common.utils import RichOutput
from getworktree.core.config.context import display_context_warnings, load_context
from getworktree.core.git_sandbox import sandbox_scope

rich_output = RichOutput()


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def run_command_in_sandbox(
    command: str,
    sandbox_path: Path,
    *,
    timeout_seconds: int | None = None,
) -> ExecutionResult:
    """Execute a target shell command inside the background sandbox directory."""
    try:
        process = subprocess.run(
            command,
            cwd=sandbox_path,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return ExecutionResult(
            command=command,
            returncode=process.returncode,
            stdout=process.stdout.strip(),
            stderr=process.stderr.strip(),
            passed=process.returncode == 0,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout).strip()
        stderr = _decode_output(exc.stderr).strip()
        timeout_note = f"Command timed out after {timeout_seconds}s"
        stderr = f"{stderr}\n{timeout_note}".strip() if stderr else timeout_note
        return ExecutionResult(
            command=command,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
            passed=False,
        )
    except Exception as e:
        return ExecutionResult(
            command=command,
            returncode=1,
            stdout="",
            stderr=f"System execution exception: {e!s}",
            passed=False,
        )


def format_error_payload(
    result: ExecutionResult, branch_name: str, session_id: str
) -> str:
    """Format structured diagnostic payload block for downstream consumers."""
    diagnostics = result.stderr if result.stderr else result.stdout
    if not diagnostics:
        diagnostics = "No output captured on stderr or stdout."

    return (
        "--- LOOP FAILURE DIAGNOSTIC PAYLOAD ---\n"
        f"Session ID: {session_id}\n"
        f"Git Branch: {branch_name}\n"
        f"Executed Command: `{result.command}`\n"
        f"Process Exit Code: {result.returncode}\n"
        "\n"
        "--- ERROR DIAGNOSTICS & TRACEBACK ---\n"
        f"{diagnostics}\n"
        "---------------------------------------------"
    )


def loop_command(command: str) -> None:
    """Run a command in an isolated background worktree and surface failures."""
    cwd = Path.cwd().resolve()
    session_id = f"loop_{uuid.uuid4().hex[:8]}"

    try:
        ctx = load_context(cwd)
    except Exception as e:
        rich_output.error(f"[bold red]Initialization Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    display_context_warnings(ctx)

    rich_output.info(
        f"\n[bold cyan]🔄 Starting sandbox loop session:[/bold cyan] [dim]{session_id}[/dim]"
    )
    rich_output.info(f"[bold]Target Command:[/bold] [yellow]{command}[/yellow]\n")

    with sandbox_scope(cwd=cwd, session_id=session_id) as session:
        rich_output.info("🧪 Executing command in isolated sandbox...")
        result = run_command_in_sandbox(
            command,
            session.sandbox_path,
            timeout_seconds=ctx.config.sandbox.default_timeout_seconds,
        )
        session.command_passed = result.passed

        if result.passed:
            rich_output.info(
                Panel.fit(
                    "[bold green]✔ Execution passed[/bold green]\n"
                    f"Command [bold]{command}[/bold] completed with exit code 0.",
                    border_style="green",
                )
            )
        else:
            rich_output.error(
                f"[bold red]❌ Command execution failed "
                f"(Exit Code {result.returncode}).[/bold red]\n"
            )
            payload = format_error_payload(result, ctx.current_branch, session_id)
            rich_output.info(
                Panel(
                    Syntax(payload, "text", theme="monokai", word_wrap=True),
                    title="[bold yellow]Failure Diagnostic Payload[/bold yellow]",
                    border_style="yellow",
                )
            )
