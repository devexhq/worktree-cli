from __future__ import annotations

import os
import shlex
import sys

from invoke import task


@task(default=True)
def test(context, path="tests/", coverage=False, fast_fail=False, parallel=True):
    """Run the test suite, optionally with coverage, parallelization, and fast-fail behavior."""
    cmd = [sys.executable, "-m", "pytest", path]

    if parallel:
        cmd.extend(["-n", "auto"])

    if coverage:
        # fail_under=80 lives in pyproject.toml [tool.coverage.report]
        cmd.extend(["--cov=getworktree", "--cov-report=term-missing"])

    if fast_fail:
        cmd.append("-x")

    cmd.append("-q")

    env = os.environ.copy()
    env["COLUMNS"] = "160"
    env["PYTHONIOENCODING"] = "utf-8"
    context.run(" ".join(shlex.quote(part) for part in cmd), env=env, pty=False)


@task
def docs(context, serve=True):
    """Build or serve documentation."""
    cmd = [sys.executable, "-m", "mkdocs", "serve" if serve else "build"]
    env = os.environ.copy()
    context.run(" ".join(shlex.quote(part) for part in cmd), env=env, pty=False)


@task
def complexity(
    context, paths="getworktree", plain=False, max_complexity=10, suggest_refactors=False, local=False, failed=False
):
    """Run complexipy, failing if any function exceeds max_complexity.

    Agents: pass the changed file(s) via `paths` (comma-separated) and use
    `plain=True` for script-friendly output; run this before every commit and
    do not commit while it fails. CI/humans: leave `paths`/`plain` at their
    defaults for a rich, whole-tree report.

    `local=True` sets `paths` to the currently staged files (`git diff
    --name-only --staged`) and takes precedence over any explicit `paths`.
    """
    if local:
        result = context.run("git diff --name-only --staged | paste -sd, -", hide=True, pty=False)
        paths = result.stdout.strip()
        if not paths:
            print("No staged files; nothing to check.")
            return

    targets = [p for p in paths.replace("\n", ",").split(",") if p.strip()]
    cmd = [
        "complexipy",
        *targets,
        "--max-complexity-allowed",
        str(max_complexity),
    ]

    if failed:
        cmd.append("--failed")
    if plain:
        cmd.append("--plain")
    elif suggest_refactors:
        cmd.append("--suggest-refactors")

    env = os.environ.copy()
    context.run(" ".join(shlex.quote(part) for part in cmd), env=env, pty=False)
