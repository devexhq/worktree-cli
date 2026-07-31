from __future__ import annotations

import os
import shlex
import sys

from invoke import task


@task(default=True)
def test(context, path="tests/", coverage=False, fast_fail=False):
    """Run the test suite, optionally with coverage and/or fast-fail behavior."""
    cmd = [sys.executable, "-m", "pytest", path]

    if coverage:
        cmd.extend(["--cov=getworktree", "--cov-report=term-missing"])

    if fast_fail:
        cmd.append("-x")

    cmd.append("-q")

    env = os.environ.copy()
    context.run(" ".join(shlex.quote(part) for part in cmd), env=env, pty=False)
