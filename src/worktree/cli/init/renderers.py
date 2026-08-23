"""Rendering helpers for init command output."""

from __future__ import annotations

from pathlib import Path

from worktree.common.utils import RichOutput, display_path
from worktree.core.bootstrap import BootstrapResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult

from .models import InitCommandOutcome


def render_init_bootstrap_failure(cwd: Path, errors: list[str], *, output: RichOutput) -> None:
    """Render the bootstrap failure panel for a failed init run."""
    lines = "\n".join(f"  {err}" for err in errors)
    remediation = "\nFix:\n  resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    output.error_panel("Failed to initialize Worktree:", f"{lines}{remediation}")


def render_init_config_failure(errors: list[str], *, output: RichOutput) -> None:
    """Render the config generation failure panel for a failed init run."""
    lines = "\n".join(f"- {err}" for err in errors)
    output.error_panel("Failed to generate config:", lines)


def _render_config_result(cwd: Path, result: ConfigGenerationResult, *, output: RichOutput) -> None:
    if not result.config_path:
        return

    output.spacer()

    label = f"./{display_path(result.config_path, cwd)}"
    if result.created:
        output.dim_bullet(f"Generated config: [cyan]{label}[/cyan]")
    elif result.overwritten:
        output.dim_bullet(f"Regenerated config: [cyan]{label}[/cyan]")
    elif result.repaired:
        output.dim_bullet(f"Repaired config: [cyan]{label}[/cyan]")
        if result.inserted_keys:
            output.dim_text("  Added missing keys:")
            for key in result.inserted_keys:
                output.dim_bullet(f"[cyan]{key}[/cyan]")
    elif result.skipped_existing:
        output.dim_bullet(f"Config exists: [cyan]{label}[/cyan]")


def _render_bootstrap_success(cwd: Path, result: BootstrapResult, *, output: RichOutput) -> None:
    worktree_label = display_path(cwd / ".worktree", cwd)

    if result.repaired:
        output.success(f"Worktree structure repaired at {worktree_label}")
        output.dim_text("Created missing:")
        for path in result.dirs_created:
            output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    if result.root_created or result.dirs_created:
        output.success(f"Initialized Worktree at {worktree_label}")
        output.dim_text("Created:")
        for path in result.dirs_created:
            output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    output.success(f"Worktree already initialized at {worktree_label}")
    output.dim_text("No changes required.")


def _render_path_bullets(cwd: Path, paths: list[Path], *, label: str, output: RichOutput) -> None:
    output.dim_text(f"{label}:")
    for path in paths:
        output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")


def _render_seed_result(cwd: Path, result: SeedResult, *, output: RichOutput) -> None:
    output.spacer()
    if result.created_files:
        output.success("Seeded starter workflows")
        _render_path_bullets(cwd, result.created_files, label="Created", output=output)
    elif result.overwritten_files:
        output.success("Refreshed starter workflows")
    else:
        output.success("Starter workflows already present")

    if result.skipped_existing_files:
        _render_path_bullets(cwd, result.skipped_existing_files, label="Skipped existing", output=output)

    if result.errors:
        lines = "\n".join(f"- {err}" for err in result.errors)
        output.error_panel("Starter workflow seeding failed:", lines)


def render_init_outcome(
    cwd: Path,
    outcome: InitCommandOutcome,
    *,
    output: RichOutput,
) -> None:
    """Render the full success summary for an init command outcome."""
    output.spacer()
    if outcome.bootstrap_result is not None:
        _render_bootstrap_success(cwd, outcome.bootstrap_result, output=output)
    if outcome.config_result is not None:
        _render_config_result(cwd, outcome.config_result, output=output)
    if outcome.seed_result is not None:
        _render_seed_result(cwd, outcome.seed_result, output=output)
    output.spacer()
    output.dim_text("Next: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt workflow list[/bold cyan]")
