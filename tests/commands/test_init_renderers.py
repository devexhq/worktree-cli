from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from getworktree.commands.init.dto import InitCommandOutcome
from getworktree.commands.init.renderers import render_init_outcome
from getworktree.common.utils import RichOutput
from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.config.generator import ConfigGenerationResult
from getworktree.core.loops.seeder import LoopSeedResult


def test_render_init_outcome_renders_summary(tmp_path: Path) -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)
    rich_output = RichOutput(console=console)

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
