"""Tests for `worktree.cli.init.renderers`."""

from __future__ import annotations

from tests.helpers import FileSystem, make_rich_output
from worktree.cli.init.models import InitCommandOutcome
from worktree.cli.init.renderers import (
    render_init_bootstrap_failure,
    render_init_config_failure,
    render_init_outcome,
)
from worktree.core.bootstrap import BootstrapResult
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class RenderInitFailureTests:
    """Tests for failure renderers."""

    def test_bootstrap_failure_panel(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        render_init_bootstrap_failure(fs.base_path, ["path conflict"], output=rich_output)
        rich_output.print()
        text = output.getvalue()
        assert "Failed to initialize Worktree" in text
        assert "path conflict" in text

    def test_bootstrap_failure_output(self, fs: FileSystem) -> None:
        rich_output, _ = make_rich_output()
        render_init_bootstrap_failure(fs.base_path, ["err"], output=rich_output)

    def test_config_failure_panel(self) -> None:
        rich_output, output = make_rich_output()
        render_init_config_failure(["bad config"], output=rich_output)
        rich_output.print()
        text = output.getvalue()
        assert "Failed to generate config" in text
        assert "bad config" in text

    def test_config_failure_output(self) -> None:
        rich_output, _ = make_rich_output()
        render_init_config_failure(["bad"], output=rich_output)


class RenderInitOutcomeTests:
    """Tests for `render_init_outcome`."""

    def test_render_init_outcome_renders_summary(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
            config_result=ConfigGenerationResult(
                config_path=fs.base_path / ".worktree" / "config.json",
                skipped_existing=True,
            ),
            seed_result=SeedResult(created_files=[fs.base_path / ".worktree" / "workflows" / "fix-tests.yml"]),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
        rich_output.print()
        rendered = output.getvalue()
        assert "Worktree already initialized" in rendered
        assert "Config exists" in rendered
        assert "Seeded starter workflows" in rendered

    def test_render_repaired_bootstrap_and_config(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        root = fs.base_path / ".worktree"
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
            seed_result=SeedResult(
                skipped_existing_files=[root / "workflows" / "fix-tests.yml"],
            ),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
        rich_output.print()
        rendered = output.getvalue()
        assert "repaired" in rendered.lower()
        assert "telemetry.enabled" in rendered
        assert "Skipped existing" in rendered

    def test_render_created_bootstrap_and_overwritten_config(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        root = fs.base_path / ".worktree"
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(
                root_path=root,
                root_created=True,
                dirs_created=[root / "workflows"],
            ),
            config_result=ConfigGenerationResult(
                config_path=root / "config.json",
                overwritten=True,
            ),
            seed_result=SeedResult(overwritten_files=[root / "workflows" / "x.yml"]),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
        rich_output.print()
        rendered = output.getvalue()
        assert "Initialized Worktree" in rendered
        assert "Regenerated config" in rendered
        assert "Refreshed starter workflows" in rendered

    def test_render_generated_config_and_workflow_errors(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        root = fs.base_path / ".worktree"
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=root),
            config_result=ConfigGenerationResult(
                config_path=root / "config.json",
                created=True,
            ),
            seed_result=SeedResult(errors=["could not seed"]),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
        rich_output.print()
        rendered = output.getvalue()
        assert "Generated config" in rendered
        assert "Starter workflow seeding failed" in rendered
        assert "could not seed" in rendered

    def test_render_skips_config_without_path(self, fs: FileSystem) -> None:
        rich_output, output = make_rich_output()
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
            config_result=ConfigGenerationResult(config_path=None),
            seed_result=SeedResult(),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
        rich_output.print()
        rendered = output.getvalue()
        assert "Config" not in rendered or "Config exists" not in rendered
        assert "Starter workflows already present" in rendered

    def test_render_output_call(self, fs: FileSystem) -> None:
        rich_output, _ = make_rich_output()
        outcome = InitCommandOutcome(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
            config_result=ConfigGenerationResult(
                config_path=fs.base_path / ".worktree" / "config.json",
                skipped_existing=True,
            ),
            seed_result=SeedResult(),
        )
        render_init_outcome(fs.base_path, outcome, output=rich_output)
