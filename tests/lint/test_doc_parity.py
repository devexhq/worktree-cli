"""Parity tests ensuring CLI command registrations and documentation stay in sync."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from worktree.cli.cli import app

REPO_ROOT = Path(__file__).parent.parent.parent
README_PATH = REPO_ROOT / "README.md"

pytestmark = pytest.mark.invariant


def test_cli_readme_command_parity() -> None:
    """Ensure every registered CLI command is documented in README.md and vice versa."""
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"
    readme_text = README_PATH.read_text(encoding="utf-8")

    registered_commands = {command.name for command in app.registered_commands if command.name}
    registered_groups = {group.name for group in app.registered_groups if group.name}
    all_cli_commands = registered_commands | registered_groups

    readme_cmds = set(re.findall(r"- `wt ([a-z\-]+)", readme_text))

    missing_from_readme = all_cli_commands - readme_cmds
    extra_in_readme = readme_cmds - all_cli_commands

    assert not missing_from_readme, (
        f"Commands registered in CLI but missing from README.md: {sorted(missing_from_readme)}"
    )
    assert not extra_in_readme, f"Commands documented in README.md but not registered in CLI: {sorted(extra_in_readme)}"


def test_agent_rules_parity() -> None:
    """Ensure compiled agent rule artifacts stay in sync with rules_spec.yaml."""
    from scripts.compile_rules import _resolve_spec_path, build_artifacts, check_artifacts_parity

    spec_path = _resolve_spec_path(REPO_ROOT)
    assert spec_path is not None, f"rules_spec.yaml not found under {REPO_ROOT}"

    artifacts = build_artifacts(spec_path, root=REPO_ROOT)
    mismatched = check_artifacts_parity(artifacts)
    assert not mismatched, (
        f"Agent rule artifacts out of sync with rules_spec.yaml: {[str(p) for p in mismatched]}. "
        "Run `uv run python scripts/compile_rules.py` to regenerate."
    )
