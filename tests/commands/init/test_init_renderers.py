"""Tests for `getworktree.commands.init.renderers`."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from getworktree.commands.init.dto import InitCommandOutcome
from getworktree.commands.init.renderers import (
    render_init_bootstrap_failure,
    render_init_config_failure,
    render_init_outcome,
)
from getworktree.common.utils import RichOutput
from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.config.generator import ConfigGenerationResult
from getworktree.core.loops.seeder import LoopSeedResult


def _rich() -> tuple[RichOutput, StringIO]:
    output = StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)
    return RichOutput(console=console), output


class RenderInitFailureTests:
    """Tests for failure renderers."""

    def test_bootstrap_failure_panel(self, tmp_path: Path) -> None:
        rich_output, output = _rich()
        render_init_bootstrap_failure(
            tmp_path, ["path conflict"], rich_output=rich_output
        )
        text = output.getvalue()
        assert "Failed to initialize Worktree" in text
        assert "path conflict" in text

    def test_bootstrap_failure_default_rich_output(self, tmp_path: Path) -> None:
        # Exercises rich_output=None branch
        render_init_bootstrap_failure(tmp_path, ["err"])

    def test_config_failure_panel(self) -> None:
        rich_output, output = _rich()
        render_init_config_failure(["bad config"], rich_output=rich_output)
        text = output.getvalue()
        assert "Failed to generate config" in text
        assert "bad config" in text

    def test_config_failure_default_rich_output(self) -> None:
        render_init_config_failure(["bad"])


class RenderInitOutcomeTests:
    """Tests for `render_init_outcome`."""

    def test_render_init_outcome_renders_summary(self, tmp_path: Path) -> None:
        rich_output, output = _rich()
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=tmp_path / ".worktree"),
            config_result=ConfigGenerationResult(
                config_path=tmp_path / ".worktree" / "config.json",
                skipped_existing=True,
            ),
            loop_seed_result=LoopSeedResult(
                created_files=[tmp_path / ".worktree" / "loops" / "fix-tests.yml"]
            ),
        )
        render_init_outcome(tmp_path, outcome, rich_output=rich_output)
        rendered = output.getvalue()
        assert "Worktree already initialized" in rendered
        assert "Config exists" in rendered
        assert "Seeded starter loops" in rendered

    def test_render_repaired_bootstrap_and_config(self, tmp_path: Path) -> None:
        rich_output, output = _rich()
        root = tmp_path / ".worktree"
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(
                root_path=root,
                repaired=True,
                dirs_created=[root / "sessions"],
            ),
            config_result=ConfigGenerationResult(
                config_path=root / "config.json",
                repaired=True,
                inserted_keys=["telemetry.enabled"],
            ),
            loop_seed_result=LoopSeedResult(
                skipped_existing_files=[root / "loops" / "fix-tests.yml"],
            ),
        )
        render_init_outcome(tmp_path, outcome, rich_output=rich_output)
        rendered = output.getvalue()
        assert "repaired" in rendered.lower()
        assert "telemetry.enabled" in rendered
        assert "Skipped existing" in rendered

    def test_render_created_bootstrap_and_overwritten_config(
        self, tmp_path: Path
    ) -> None:
        rich_output, output = _rich()
        root = tmp_path / ".worktree"
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(
                root_path=root,
                root_created=True,
                dirs_created=[root / "loops"],
            ),
            config_result=ConfigGenerationResult(
                config_path=root / "config.json",
                overwritten=True,
            ),
            loop_seed_result=LoopSeedResult(
                overwritten_files=[root / "loops" / "x.yml"]
            ),
        )
        render_init_outcome(tmp_path, outcome, rich_output=rich_output)
        rendered = output.getvalue()
        assert "Initialized Worktree" in rendered
        assert "Regenerated config" in rendered
        assert "Refreshed starter loops" in rendered

    def test_render_generated_config_and_loop_errors(self, tmp_path: Path) -> None:
        rich_output, output = _rich()
        root = tmp_path / ".worktree"
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=root),
            config_result=ConfigGenerationResult(
                config_path=root / "config.json",
                created=True,
            ),
            loop_seed_result=LoopSeedResult(errors=["could not seed"]),
        )
        render_init_outcome(tmp_path, outcome, rich_output=rich_output)
        rendered = output.getvalue()
        assert "Generated config" in rendered
        assert "Starter loop seeding failed" in rendered
        assert "could not seed" in rendered

    def test_render_skips_config_without_path(self, tmp_path: Path) -> None:
        rich_output, output = _rich()
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=tmp_path / ".worktree"),
            config_result=ConfigGenerationResult(config_path=None),
            loop_seed_result=LoopSeedResult(),
        )
        render_init_outcome(tmp_path, outcome, rich_output=rich_output)
        rendered = output.getvalue()
        assert "Config" not in rendered or "Config exists" not in rendered
        assert "Starter loops already present" in rendered

    def test_render_default_rich_output(self, tmp_path: Path) -> None:
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=tmp_path / ".worktree"),
            config_result=ConfigGenerationResult(
                config_path=tmp_path / ".worktree" / "config.json",
                skipped_existing=True,
            ),
            loop_seed_result=LoopSeedResult(),
        )
        render_init_outcome(tmp_path, outcome)
