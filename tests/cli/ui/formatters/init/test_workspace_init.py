"""Tier 2 presentation contract tests for WorkspaceInitFormatter."""

from __future__ import annotations

import json

from tests.helpers import FileSystem, render_rich
from worktree.cli.ui.formatters.init import WorkspaceInitFormatter
from worktree.core.bootstrap import (
    BootstrapOutcome,
    BootstrapResult,
    InitFailureMode,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult


class WorkspaceInitFormatterTests:
    """Presentation contract tests for WorkspaceInitFormatter."""

    def test_to_rich_initialized_renders_summary(self, fs: FileSystem) -> None:
        formatter = WorkspaceInitFormatter()
        result = WorkspaceInitResult(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
            config_result=ConfigGenerationResult(
                config_path=fs.base_path / ".worktree" / "config.json",
                skipped_existing=True,
            ),
            seed_result=SeedResult(created_files=[fs.base_path / ".worktree" / "workflows" / "fix-tests.yml"]),
        )

        rendered = render_rich(formatter.to_rich(result))
        assert ".worktree" in rendered
        assert "config.json" in rendered
        assert "fix-tests.yml" in rendered

    def test_to_rich_when_repaired_renders_repaired_details(self, fs: FileSystem) -> None:
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

        rendered = render_rich(formatter.to_rich(result))
        assert "sessions" in rendered
        assert "telemetry.enabled" in rendered

    def test_to_rich_when_created_and_overwritten_renders_summary(self, fs: FileSystem) -> None:
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

        rendered = render_rich(formatter.to_rich(result))
        assert "workflows" in rendered
        assert "config.json" in rendered

    def test_to_rich_when_seeding_errors_renders_error_message(self, fs: FileSystem) -> None:
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

        rendered = render_rich(formatter.to_rich(result))
        assert "could not seed" in rendered
        assert "config.json" in rendered

    def test_to_rich_when_no_config_path_skips_config_entry(self, fs: FileSystem) -> None:
        formatter = WorkspaceInitFormatter()
        result = WorkspaceInitResult(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree"),
            config_result=ConfigGenerationResult(config_path=None),
            seed_result=SeedResult(),
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "config.json" not in rendered

    def test_to_rich_when_preflight_failure_renders_error_message(self) -> None:
        formatter = WorkspaceInitFormatter()
        error_message = "The current directory is not a valid Git repository."
        result = WorkspaceInitResult(errors=[error_message])

        rendered = render_rich(formatter.to_rich(result))
        assert error_message in rendered

    def test_to_rich_when_bootstrap_failure_renders_error_message(self, fs: FileSystem) -> None:
        formatter = WorkspaceInitFormatter()
        bootstrap = BootstrapResult(
            root_path=fs.base_path / ".worktree",
            errors=["path conflict: .worktree is a file"],
        )
        result = WorkspaceInitResult(bootstrap_result=bootstrap, errors=list(bootstrap.errors))

        rendered = render_rich(formatter.to_rich(result))
        assert "path conflict: .worktree is a file" in rendered

    def test_to_rich_when_config_failure_renders_error_message(self, fs: FileSystem) -> None:
        formatter = WorkspaceInitFormatter()
        bootstrap = BootstrapResult(root_path=fs.base_path / ".worktree")
        config = ConfigGenerationResult(errors=["CONFIG_WRITE_FAILED: permission denied"])
        result = WorkspaceInitResult(
            bootstrap_result=bootstrap,
            config_result=config,
            errors=list(config.errors),
        )

        rendered = render_rich(formatter.to_rich(result))
        assert "CONFIG_WRITE_FAILED: permission denied" in rendered

    def test_to_json_serializable_returns_exact_dict(self, fs: FileSystem) -> None:
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
        assert dumped == {
            "errors": [],
            "warnings": [],
            "fixes": [],
            "bootstrap_result": {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "root_path": str(root),
                "outcome": "initialized",
                "root_created": True,
                "dirs_created": [str(root / "sessions")],
                "dirs_existing": [],
                "repaired": False,
                "seed_result": {
                    "errors": [],
                    "warnings": [],
                    "fixes": [],
                    "created_files": [],
                    "skipped_existing_files": [],
                    "overwritten_files": [],
                },
            },
            "config_result": {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "created": True,
                "skipped_existing": False,
                "repaired": False,
                "overwritten": False,
                "inserted_keys": [],
                "config_path": str(root / "config.json"),
            },
            "seed_result": {
                "errors": [],
                "warnings": [],
                "fixes": [],
                "created_files": [str(root / "workflows" / "test.yml")],
                "skipped_existing_files": [],
                "overwritten_files": [],
            },
            "failure_mode": None,
        }

        # Verify JSON encoding works with no error
        encoded = json.dumps(dumped)
        decoded = json.loads(encoded)
        assert decoded["bootstrap_result"]["root_created"] is True
        assert decoded["bootstrap_result"]["outcome"] == "initialized"
        assert decoded["failure_mode"] is None

    def test_to_rich_branches_on_outcome(self, fs: FileSystem) -> None:
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

    def test_to_rich_branches_on_failure_mode(self) -> None:
        formatter = WorkspaceInitFormatter()
        result = WorkspaceInitResult(
            errors=["The current directory is not a valid Git repository."],
            failure_mode=InitFailureMode.PREFLIGHT,
        )
        rendered = render_rich(formatter.to_rich(result))
        assert "The current directory is not a valid Git repository." in rendered
