"""Rendering helpers for init command output."""

from __future__ import annotations

from pathlib import Path

from worktree.common.utils import RichOutput, display_path
from worktree.core.bootstrap import BootstrapResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult

from .models import InitCommandOutcome


def render_init_bootstrap_failure(cwd: Path, errors: list[str], *, rich_output: RichOutput | None = None) -> None:
    """Render the bootstrap failure panel for a failed init run."""
    rich_output = rich_output or RichOutput()
    lines = "\n".join(f"  {err}" for err in errors)
    remediation = "\nFix:\n  resolve the path conflict above, then rerun [bold cyan]wt init[/bold cyan]."
    rich_output.error_panel("Failed to initialize Worktree:", f"{lines}{remediation}")


def render_init_config_failure(errors: list[str], *, rich_output: RichOutput | None = None) -> None:
    """Render the config generation failure panel for a failed init run."""
    rich_output = rich_output or RichOutput()
    lines = "\n".join(f"- {err}" for err in errors)
    rich_output.error_panel("Failed to generate config:", lines)


def _render_config_result(cwd: Path, result: ConfigGenerationResult, *, rich_output: RichOutput) -> None:
    if not result.config_path:
        return

    rich_output.spacer()

    label = f"./{display_path(result.config_path, cwd)}"
    if result.created:
        rich_output.dim_bullet(f"Generated config: [cyan]{label}[/cyan]")
    elif result.overwritten:
        rich_output.dim_bullet(f"Regenerated config: [cyan]{label}[/cyan]")
    elif result.repaired:
        rich_output.dim_bullet(f"Repaired config: [cyan]{label}[/cyan]")
        if result.inserted_keys:
            rich_output.dim_text("  Added missing keys:")
            for key in result.inserted_keys:
                rich_output.dim_bullet(f"[cyan]{key}[/cyan]")
    elif result.skipped_existing:
        rich_output.dim_bullet(f"Config exists: [cyan]{label}[/cyan]")


def _render_bootstrap_success(cwd: Path, result: BootstrapResult, *, rich_output: RichOutput) -> None:
    worktree_label = display_path(cwd / ".worktree", cwd)

    if result.repaired:
        rich_output.success(f"Worktree structure repaired at {worktree_label}")
        rich_output.dim_text("Created missing:")
        for path in result.dirs_created:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    if result.root_created or result.dirs_created:
        rich_output.success(f"Initialized Worktree at {worktree_label}")
        rich_output.dim_text("Created:")
        for path in result.dirs_created:
            rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")
        return

    rich_output.success(f"Worktree already initialized at {worktree_label}")
    rich_output.dim_text("No changes required.")


def _render_path_bullets(cwd: Path, paths: list[Path], *, label: str, rich_output: RichOutput) -> None:
    rich_output.dim_text(f"{label}:")
    for path in paths:
        rich_output.dim_bullet(f"[cyan]{display_path(path, cwd)}[/cyan]")


def _render_seed_result(cwd: Path, result: SeedResult, *, rich_output: RichOutput) -> None:
    rich_output.spacer()
    if result.created_files:
        rich_output.success("Seeded starter workflows")
        _render_path_bullets(cwd, result.created_files, label="Created", rich_output=rich_output)
    elif result.overwritten_files:
        rich_output.success("Refreshed starter workflows")
    else:
        rich_output.success("Starter workflows already present")

    if result.skipped_existing_files:
        _render_path_bullets(cwd, result.skipped_existing_files, label="Skipped existing", rich_output=rich_output)

    if result.errors:
        lines = "\n".join(f"- {err}" for err in result.errors)
        rich_output.error_panel("Starter workflow seeding failed:", lines)


def render_init_outcome(
    cwd: Path,
    outcome: InitCommandOutcome,
    *,
    rich_output: RichOutput | None = None,
) -> None:
    """Render the full success summary for an init command outcome."""
    rich_output = rich_output or RichOutput()
    rich_output.spacer()
    _render_bootstrap_success(cwd, outcome.bootstrap_result, rich_output=rich_output)
    _render_config_result(cwd, outcome.config_result, rich_output=rich_output)
    _render_seed_result(cwd, outcome.seed_result, rich_output=rich_output)
    rich_output.spacer()
    rich_output.dim_text("Next: run [bold cyan]wt config show[/bold cyan] or [bold cyan]wt workflow list[/bold cyan]")
