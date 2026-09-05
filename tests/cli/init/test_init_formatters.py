"""Unit tests for WorkspaceInitFormatter and init UI dispatching."""

from __future__ import annotations

import json

import pytest
from rich.console import Group
from rich.panel import Panel

from tests.helpers import FileSystem, make_dispatcher_with_buffer, render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.init import (
    InitOutcomeFormatter,
    WorkspaceInitFormatter,
    register_init_formatters,
)
from worktree.core.bootstrap import (
    BootstrapOutcome,
    BootstrapResult,
    InitFailureMode,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


def test_init_outcome_formatter_to_rich_success(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
        config_result=ConfigGenerationResult(
            config_path=fs.base_path / ".worktree" / "config.json",
            skipped_existing=True,
        ),
        seed_result=SeedResult(created_files=[fs.base_path / ".worktree" / "workflows" / "fix-tests.yml"]),
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    rendered = render_rich(rich_renderable)
    assert "Worktree already initialized" in rendered
    assert "Config exists" in rendered
    assert "Seeded starter workflows" in rendered
    assert "Next: run wt config show or wt workflow list" in rendered


def test_init_outcome_formatter_to_rich_repaired(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
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

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    rendered = render_rich(rich_renderable)
    assert "repaired" in rendered.lower()
    assert "Created missing:" in rendered
    assert "telemetry.enabled" in rendered
    assert "Skipped existing" in rendered


def test_init_outcome_formatter_to_rich_created_and_overwritten(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
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

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    rendered = render_rich(rich_renderable)
    assert "Initialized Worktree" in rendered
    assert "Regenerated config" in rendered
    assert "Refreshed starter workflows" in rendered


def test_init_outcome_formatter_to_rich_generated_and_seeding_errors(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=root),
        config_result=ConfigGenerationResult(
            config_path=root / "config.json",
            created=True,
        ),
        seed_result=SeedResult(errors=["could not seed"]),
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    rendered = render_rich(rich_renderable)
    assert "Generated config" in rendered
    assert "Starter workflow seeding failed" in rendered
    assert "could not seed" in rendered


def test_init_outcome_formatter_to_rich_skips_config_without_path(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
        config_result=ConfigGenerationResult(config_path=None),
        seed_result=SeedResult(),
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    rendered = render_rich(rich_renderable)
    assert "Config exists" not in rendered
    assert "Starter workflows already present" in rendered


def test_init_outcome_formatter_to_rich_preflight_failure() -> None:
    formatter = WorkspaceInitFormatter()
    err = "The current directory is not a valid Git repository."
    result = WorkspaceInitResult(errors=[err])

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    rendered = render_rich(rich_renderable)
    assert "Initialization Failed!" in rendered
    assert "The current directory is not a valid Git repository." in rendered


def test_init_outcome_formatter_to_rich_bootstrap_failure(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    bootstrap = BootstrapResult(
        root_path=fs.base_path / ".worktree",
        errors=["path conflict: .worktree is a file"],
    )
    result = WorkspaceInitResult(bootstrap_result=bootstrap, errors=list(bootstrap.errors))

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    rendered = render_rich(rich_renderable)
    assert "Failed to initialize Worktree" in rendered
    assert "path conflict: .worktree is a file" in rendered
    assert "Fix:" in rendered


def test_init_outcome_formatter_to_rich_config_failure(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    bootstrap = BootstrapResult(root_path=fs.base_path / ".worktree")
    config = ConfigGenerationResult(errors=["CONFIG_WRITE_FAILED: permission denied"])
    result = WorkspaceInitResult(
        bootstrap_result=bootstrap,
        config_result=config,
        errors=list(config.errors),
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Panel)

    rendered = render_rich(rich_renderable)
    assert "Failed to generate config" in rendered
    assert "CONFIG_WRITE_FAILED: permission denied" in rendered


def test_init_outcome_formatter_to_json_serializable(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=root,
            root_created=True,
            dirs_created=[root / "sessions"],
        ),
        config_result=ConfigGenerationResult(
            config_path=root / "config.json",
            created=True,
        ),
        seed_result=SeedResult(
            created_files=[root / "workflows" / "test.yml"],
        ),
    )

    dumped = formatter.to_json_serializable(result)
    assert isinstance(dumped, dict)
    assert dumped["bootstrap_result"]["root_created"] is True
    assert dumped["bootstrap_result"]["root_path"] == str(root)
    assert dumped["bootstrap_result"]["outcome"] == "initialized"
    assert dumped["failure_mode"] is None
    assert dumped["config_result"]["created"] is True
    assert dumped["config_result"]["config_path"] == str(root / "config.json")
    assert dumped["seed_result"]["created_files"] == [str(root / "workflows" / "test.yml")]
    assert dumped["errors"] == []

    # Verify JSON encoding works with no error
    encoded = json.dumps(dumped)
    decoded = json.loads(encoded)
    assert decoded["bootstrap_result"]["root_created"] is True
    assert decoded["bootstrap_result"]["outcome"] == "initialized"
    assert decoded["failure_mode"] is None


def test_init_outcome_formatter_to_json_serializable_carries_outcome_and_failure_mode(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=root,
            root_created=True,
            outcome=BootstrapOutcome.INITIALIZED,
        ),
        config_result=ConfigGenerationResult(config_path=root / "config.json", created=True),
        seed_result=SeedResult(),
        failure_mode=None,
    )
    dumped = formatter.to_json_serializable(result)
    assert dumped["bootstrap_result"]["outcome"] == "initialized"
    assert dumped["failure_mode"] is None


def test_init_outcome_formatter_to_rich_branches_on_outcome(fs: FileSystem) -> None:
    formatter = WorkspaceInitFormatter()
    root = fs.base_path / ".worktree"
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=root,
            outcome=BootstrapOutcome.REPAIRED,
            dirs_created=[root / "sessions"],
        ),
        config_result=ConfigGenerationResult(config_path=root / "config.json", created=True),
        seed_result=SeedResult(),
    )
    rendered = render_rich(formatter.to_rich(result))
    assert "sessions" in rendered


def test_init_outcome_formatter_to_rich_branches_on_failure_mode() -> None:
    formatter = WorkspaceInitFormatter()
    result = WorkspaceInitResult(
        errors=["The current directory is not a valid Git repository."],
        failure_mode=InitFailureMode.PREFLIGHT,
    )
    rendered = render_rich(formatter.to_rich(result))
    assert "The current directory is not a valid Git repository." in rendered


def test_register_init_formatters_custom_dispatcher() -> None:
    dispatcher = UiDispatcher()
    register_init_formatters(dispatcher)

    assert WorkspaceInitResult in dispatcher._registry
    assert isinstance(dispatcher._registry[WorkspaceInitResult], WorkspaceInitFormatter)


def test_ui_dispatcher_registration() -> None:
    assert WorkspaceInitResult in ui_dispatcher._registry
    assert isinstance(ui_dispatcher._registry[WorkspaceInitResult], WorkspaceInitFormatter)
    assert InitOutcomeFormatter is WorkspaceInitFormatter


def test_dispatcher_json_format_ndjson(fs: FileSystem, capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_init_formatters(dispatcher)
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree", root_created=True),
        config_result=ConfigGenerationResult(config_path=fs.base_path / ".worktree" / "config.json", created=True),
        seed_result=SeedResult(),
    )

    dispatcher.dispatch(result, output_format="json")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event_type"] == "WorkspaceInitResult"
    assert payload["payload"]["bootstrap_result"]["root_created"] is True
    assert payload["payload"]["config_result"]["created"] is True


def test_dispatcher_terminal_format(fs: FileSystem) -> None:
    dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
    result = WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree", root_created=True),
        config_result=ConfigGenerationResult(config_path=fs.base_path / ".worktree" / "config.json", created=True),
        seed_result=SeedResult(),
    )

    dispatcher.dispatch(result, output_format="terminal")

    output = buffer.getvalue()
    assert "Initialized Worktree" in output
    assert "Generated config" in output
