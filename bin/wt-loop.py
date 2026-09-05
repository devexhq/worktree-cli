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
    "agy": ["agy", "-p", "{prompt}", "--dangerously-skip-permissions", "--print-timeout", "{timeout}"],
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


def log(message: str) -> None:
    """Print a driver-level message, distinguishable from agent output."""
    print(f"[wt-loop] {message}", flush=True)


def git_state() -> str:
    """Return the porcelain working-tree state."""
    return subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout


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
    completed = subprocess.run(argv, check=False)
    elapsed = time.monotonic() - started

    log(f"{phase}: exit {completed.returncode} in {elapsed:.0f}s")
    return PhaseResult(phase=phase, exit_code=completed.returncode, seconds=elapsed)


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
    """Snapshot the round's verdict and phase timings under .agentic/rounds/."""
    ROUNDS.mkdir(parents=True, exist_ok=True)
    if REVIEW_JSON.exists():
        shutil.copy(REVIEW_JSON, ROUNDS / f"round-{number}-review.json")

    timings = {result.phase: round(result.seconds) for result in results}
    (ROUNDS / f"round-{number}-timings.json").write_text(json.dumps(timings, indent=2) + "\n")


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
        verdict, _ = code_and_review(args, number)
        log(f"round {number}: {verdict}")
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
