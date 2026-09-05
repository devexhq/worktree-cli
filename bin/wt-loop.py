#!/usr/bin/env python3
"""Drive the wt-plan / wt-code / wt-review / wt-push skills as one loop, a fresh agent session per phase."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

AGENTIC = Path(".agentic")
PLAN = AGENTIC / "plan.md"
REVIEW_MD = AGENTIC / "review.md"
REVIEW_JSON = AGENTIC / "review.json"
ROUNDS = AGENTIC / "rounds"
SKILLS = Path(".agents/skills")

# Argv template per host. "{prompt}" and "{timeout}" are substituted per phase.
# agy notes, all load-bearing:
#   --print-timeout defaults to 5m, which truncates any real implementation phase.
#   Headless tools are handled by policy, so without --dangerously-skip-permissions a write is denied.
#   `agy -p` writes nothing to stdout when stdout is not a TTY, so never redirect this driver's
#   output; run it in a terminal, or wrap it in `script -qec '...' /dev/null`.
#   Headless uses cached credentials: authenticate once interactively, or set GEMINI_API_KEY.
HOSTS: dict[str, list[str]] = {
    "agy": [
        "agy",
        "-p",
        "{prompt}",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--print-timeout",
        "{timeout}",
    ],
    "copilot": ["copilot", "-p", "{prompt}", "--allow-all-tools"],
    "cursor": ["cursor-agent", "-p", "{prompt}"],
}

VERDICT_APPROVE = "APPROVE"
VERDICT_CHANGES = "CHANGES_REQUIRED"


@dataclass(frozen=True)
class PhaseResult:
    """Outcome of one agent session."""

    phase: str
    exit_code: int
    seconds: float
    usage: dict[str, int] | None = None


@dataclass
class StreamState:
    """Track streaming text state during subprocess execution."""

    pending_newline: bool = False
    streamed_any_text: bool = False
    usage: dict[str, int] | None = None

    def write_delta(self, delta: str) -> None:
        """Stream an agent text delta."""
        print(delta, end="", flush=True)
        self.pending_newline = not delta.endswith("\n")
        self.streamed_any_text = True

    def ensure_newline(self) -> None:
        """Ensure terminal cursor is on a fresh line before driver logs."""
        if self.pending_newline:
            print()
            self.pending_newline = False


def log(message: str) -> None:
    """Print a driver-level message, distinguishable from agent output."""
    print(f"[wt-loop] {message}", flush=True)


def format_tool_target(params: dict[str, object]) -> str:
    """Extract a relative path and optional line range from tool parameters."""
    target = str(params.get("AbsolutePath") or params.get("TargetFile") or "")
    try:
        target = str(Path(target).relative_to(Path.cwd()))
    except ValueError:
        pass
    if "StartLine" in params and "EndLine" in params:
        return f"{target}:{params['StartLine']}-{params['EndLine']}"
    return target


def summarize_tool(tool_name: str, params: dict[str, object]) -> str:
    """Format a compact, single-line summary of a tool call."""
    if tool_name == "run_command":
        return str(params.get("CommandLine", ""))
    if tool_name in {"view_file", "replace_file_content", "write_to_file"}:
        return format_tool_target(params)
    if tool_name == "grep_search":
        return f"query={params.get('Query', '')!r}"

    parts: list[str] = []
    for k, v in params.items():
        if k in {"CodeContent", "ReplacementContent", "TargetContent", "toolSummary", "toolAction"}:
            continue
        v_str = str(v)
        parts.append(f"{k}={v_str[:37]}..." if len(v_str) > 40 else f"{k}={v_str}")
    return " ".join(parts)


def handle_tool_step(update: dict[str, object], state: StreamState) -> None:
    """Log a tool invocation or completion."""
    state.ensure_newline()
    tool = str(update.get("tool_name", "tool"))
    tool_state = str(update.get("state", ""))
    tool_info = update.get("tool_info")
    params: dict[str, object] = tool_info.get("parameters", {}) if isinstance(tool_info, dict) else {}

    if tool_state == "ACTIVE":
        detail = summarize_tool(tool, params)
        log(f"  -> [{tool}] {detail}".strip())
        return

    duration = update.get("duration_seconds")
    dur_str = f" in {duration:.1f}s" if isinstance(duration, (int, float)) else ""
    if tool_state == "DONE":
        log(f"  ✓ [{tool}]{dur_str}")
    elif tool_state == "ERROR":
        log(f"  ✗ [{tool}] error{dur_str}")


def handle_agent_response(update: dict[str, object], state: StreamState) -> None:
    """Stream response delta if present."""
    delta = update.get("text_delta")
    if isinstance(delta, str) and delta:
        state.write_delta(delta)


def handle_step_update(update: dict[str, object], state: StreamState) -> None:
    """Dispatch step update events."""
    step_type = update.get("step_type")
    if step_type == "tool":
        handle_tool_step(update, state)
    elif step_type == "agent_response":
        handle_agent_response(update, state)


def handle_result(result: dict[str, object], state: StreamState) -> None:
    """Capture token usage and print the final response if no deltas were streamed."""
    usage_data = result.get("usage")
    if isinstance(usage_data, dict):
        state.usage = {str(k): int(v) for k, v in usage_data.items() if isinstance(v, (int, float))}

    if state.streamed_any_text:
        return
    resp = result.get("response")
    if isinstance(resp, str) and resp:
        state.ensure_newline()
        print(resp, flush=True)


def handle_stream_event(event_obj: dict[str, object], state: StreamState) -> None:
    """Dispatch a parsed NDJSON stream event."""
    event = event_obj.get("event")
    payload = event_obj.get(str(event))
    if not isinstance(payload, dict):
        return

    if event == "step_update":
        handle_step_update(payload, state)
    elif event == "result":
        handle_result(payload, state)


def stream_process_output(process: subprocess.Popen[str]) -> StreamState:
    """Stream process stdout line by line, parsing JSON events when present."""
    state = StreamState()
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event_obj = json.loads(line)
        except json.JSONDecodeError:
            state.ensure_newline()
            print(raw_line, end="", flush=True)
            continue

        if isinstance(event_obj, dict):
            handle_stream_event(event_obj, state)

    state.ensure_newline()
    return state


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable string."""
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    m, s = divmod(total, 60)
    return f"{m}m {s:02d}s"


def format_token_count(tokens: int) -> str:
    """Format token count with a metric suffix."""
    if tokens >= 1000:
        return f"{tokens / 1000:.1f}k"
    return str(tokens)


def format_round_summary(verdict: str, results: list[PhaseResult]) -> str:
    """Format a summary string for a round including time and token usage."""
    total_seconds = sum(r.seconds for r in results)
    dur_str = format_duration(total_seconds)
    breakdown = ""
    if len(results) > 1:
        parts = [f"{r.phase.split(' ')[0]}: {format_duration(r.seconds)}" for r in results]
        breakdown = f" ({', '.join(parts)})"

    total_tokens = sum((r.usage or {}).get("total_tokens", 0) for r in results)
    in_tokens = sum((r.usage or {}).get("input_tokens", 0) for r in results)
    out_tokens = sum((r.usage or {}).get("output_tokens", 0) for r in results)

    tok_str = ""
    if total_tokens > 0:
        tok_str = (
            f" | tokens: {format_token_count(total_tokens)} total "
            f"({format_token_count(in_tokens)} in, {format_token_count(out_tokens)} out)"
        )

    return f"{verdict} in {dur_str}{breakdown}{tok_str}"


def git_state() -> str:
    """Return the porcelain working-tree state."""
    return subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout


def build_prompt(skill: str, instruction: str, inline: bool) -> str:
    """Build a phase prompt, inlining the SKILL.md body for hosts that do not discover skills."""
    if not inline:
        return f"Use the {skill} skill. {instruction}".strip()

    body = (SKILLS / skill / "SKILL.md").read_text()
    return f"Follow these instructions exactly:\n\n{body}\n\n---\n\n{instruction}".strip()


def fill(part: str, prompt: str, timeout: str) -> str:
    """Substitute one argv placeholder."""
    if part == "{prompt}":
        return prompt
    if part == "{timeout}":
        return timeout
    return part


def run_phase(phase: str, host: str, prompt: str, args: argparse.Namespace) -> PhaseResult:
    """Run one agent session to completion and time it."""
    dry_run = args.dry_run
    argv = [fill(part, prompt, args.phase_timeout) for part in HOSTS[host]]

    log(f"{phase}: {host} session starting")
    if dry_run:
        log(f"{phase}: dry run, would exec: {argv[0]} ... ({len(prompt)} char prompt)")
        return PhaseResult(phase=phase, exit_code=0, seconds=0.0)

    started = time.monotonic()
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    state = stream_process_output(process)
    process.wait()
    elapsed = time.monotonic() - started

    tok = state.usage.get("total_tokens", 0) if state.usage else 0
    tok_str = f" ({format_token_count(tok)} tokens)" if tok > 0 else ""
    log(f"{phase}: exit {process.returncode} in {elapsed:.0f}s{tok_str}")
    return PhaseResult(phase=phase, exit_code=process.returncode, seconds=elapsed, usage=state.usage)


def read_verdict() -> dict[str, object]:
    """Read and validate .agentic/review.json, raising when it is missing or self-inconsistent."""
    if not REVIEW_JSON.exists():
        raise RuntimeError(f"{REVIEW_JSON} was not written; the review session produced no verdict")

    payload = json.loads(REVIEW_JSON.read_text())
    verdict = payload.get("verdict")
    if verdict not in {VERDICT_APPROVE, VERDICT_CHANGES}:
        raise RuntimeError(f"unrecognized verdict {verdict!r} in {REVIEW_JSON}")

    counts = payload.get("counts") or {}
    blocking = counts.get("blocking")
    if (verdict == VERDICT_APPROVE) != (blocking == 0):
        raise RuntimeError(f"verdict {verdict} disagrees with blocking count {blocking}")

    return payload


def archive_round(number: int, results: list[PhaseResult]) -> None:
    """Snapshot the round's verdict, timings, and token metrics under .agentic/rounds/."""
    ROUNDS.mkdir(parents=True, exist_ok=True)
    if REVIEW_JSON.exists():
        shutil.copy(REVIEW_JSON, ROUNDS / f"round-{number}-review.json")

    timings = {result.phase: round(result.seconds) for result in results}
    timings["total"] = round(sum(result.seconds for result in results))
    (ROUNDS / f"round-{number}-timings.json").write_text(json.dumps(timings, indent=2) + "\n")

    usage_metrics: dict[str, object] = {result.phase: result.usage or {} for result in results}
    usage_metrics["total"] = {
        "input_tokens": sum((r.usage or {}).get("input_tokens", 0) for r in results),
        "output_tokens": sum((r.usage or {}).get("output_tokens", 0) for r in results),
        "total_tokens": sum((r.usage or {}).get("total_tokens", 0) for r in results),
    }
    (ROUNDS / f"round-{number}-usage.json").write_text(json.dumps(usage_metrics, indent=2) + "\n")


def command_plan(args: argparse.Namespace) -> int:
    """Run the planning session, then stop for human review."""
    prompt = build_prompt("wt-plan", args.task, args.inline_skills)
    result = run_phase("plan", args.host, prompt, args)

    if not args.dry_run and not PLAN.exists():
        log(f"FAILED: {PLAN} was not written (exit {result.exit_code}). Check the host's permission flags.")
        return 1

    log(f"plan written to {PLAN}. Review it, then run: {sys.argv[0]} run")
    return 0


def code_and_review(args: argparse.Namespace, number: int) -> tuple[str, list[PhaseResult]]:
    """Run one implement-then-review round and return its verdict."""
    instruction = (
        "Implement .agentic/plan.md."
        if number == 1
        else "Run in review mode: address the findings in .agentic/review.md."
    )
    code_prompt = build_prompt("wt-code", instruction, args.inline_skills)

    before = git_state()
    code_result = run_phase(f"code (round {number})", args.host, code_prompt, args)
    if not args.dry_run and git_state() == before:
        log("WARNING: the working tree is unchanged after the code session; the host may be soft-denying writes")

    review_prompt = build_prompt("wt-review", "", args.inline_skills)
    review_result = run_phase(f"review (round {number})", args.host, review_prompt, args)

    results = [code_result, review_result]
    if args.dry_run:
        return VERDICT_APPROVE, results

    payload = read_verdict()
    archive_round(number, results)
    return str(payload["verdict"]), results


def command_run(args: argparse.Namespace) -> int:
    """Loop implement-and-review until APPROVE or the round cap, then optionally push."""
    if not PLAN.exists() and not args.dry_run:
        log(f"FAILED: {PLAN} is missing. Run `{sys.argv[0]} plan '<task>'` first.")
        return 1

    verdict = VERDICT_CHANGES
    for number in range(1, args.max_rounds + 1):
        verdict, results = code_and_review(args, number)
        log(f"round {number}: {format_round_summary(verdict, results)}")
        if verdict == VERDICT_APPROVE:
            break

    if verdict != VERDICT_APPROVE:
        log(f"STOPPED: still {verdict} after {args.max_rounds} rounds. See {REVIEW_MD}.")
        return 1

    if not args.push:
        log("APPROVE. Nothing pushed; run with --push, or use /wt-push yourself.")
        return 0

    push_prompt = build_prompt("wt-push", "", args.inline_skills)
    push_result = run_phase("push", args.host, push_prompt, args)
    return 0 if push_result.exit_code == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=sorted(HOSTS), default="agy", help="agent CLI to spawn per phase")
    parser.add_argument(
        "--phase-timeout",
        default="4h",
        help="per-session cap; agy's --print-timeout default of 5m truncates an implementation phase",
    )
    parser.add_argument(
        "--inline-skills",
        action="store_true",
        help="paste SKILL.md into the prompt; unnecessary for agy, which discovers .agents/skills natively",
    )
    parser.add_argument("--dry-run", action="store_true", help="print what would run without spawning")

    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="plan only, then stop for human review")
    plan_parser.add_argument("task", help="issue number or plain-language task")
    plan_parser.set_defaults(func=command_plan)

    run_parser = subparsers.add_parser("run", help="implement, review, loop to APPROVE")
    run_parser.add_argument("--max-rounds", type=int, default=3, help="review rounds before giving up")
    run_parser.add_argument("--push", action="store_true", help="run wt-push after APPROVE")
    run_parser.set_defaults(func=command_run)

    return parser


def main() -> int:
    """Entry point."""
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (RuntimeError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        log(f"FAILED: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
