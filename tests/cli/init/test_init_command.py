"""Integration tests for `getworktree.cli.init.command.init_command`."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest
import typer

from getworktree.cli.init.command import init_command
from getworktree.common.schema_validation import SchemaValidator
from getworktree.core.bootstrap import BootstrapResult
from getworktree.core.config.generator import ConfigGenerationResult
from getworktree.core.config.models import PathsConfig
from getworktree.core.workflows.seeder import WorkflowSeedResult
from tests.helpers import FileSystem, GitFileSystem

CONFIG_VALIDATOR = SchemaValidator(resources.files("getworktree.schemas.v1") / "config.json")


class InitCommandConfigTests:
    """Tests for config generation behavior triggered by `wt init`."""

    def test_init_creates_v1_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")

        config_path = git_fs.base_path / ".worktree" / "config.json"
        assert config_path.is_file()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["project"]["name"] == git_fs.base_path.name
        assert CONFIG_VALIDATOR.validate(data).ok

    def test_init_idempotent_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")
        config_path = git_fs.base_path / ".worktree" / "config.json"
        first = config_path.read_text(encoding="utf-8")

        init_command(tool_version="0.1.1")
        second = config_path.read_text(encoding="utf-8")
        assert first == second

    def test_init_repair_partial_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        del data["telemetry"]
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        init_command(tool_version="0.1.1", repair=True)
        repaired = json.loads(config_path.read_text(encoding="utf-8"))
        assert "telemetry" in repaired
        assert CONFIG_VALIDATOR.validate(repaired).ok

    def test_init_overwrite_replaces_config(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["project"]["name"] = "stale-name"
        data["custom_user_key"] = True
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        init_command(tool_version="0.1.1", overwrite=True)

        replaced = json.loads(config_path.read_text(encoding="utf-8"))
        assert replaced["project"]["name"] == git_fs.base_path.name
        assert "custom_user_key" not in replaced
        assert CONFIG_VALIDATOR.validate(replaced).ok


class InitCommandGuardrailTests:
    """Init guardrails: git preflight, layout repair, non-destructive defaults."""

    def test_fresh_init_creates_full_layout(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)

        init_command(tool_version="0.1.1")

        root = git_fs.base_path / ".worktree"
        assert root.is_dir()
        for name in (
            ".meta",
            "workflows",
            "sessions",
            "artifacts",
            "tmp",
            "logs",
        ):
            assert (root / name).is_dir()

        meta_path = root / ".meta" / "bootstrap.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["schema_version"] == 1
        assert meta["status"] == "initialized"
        assert meta["tool_version"] == "0.1.1"
        assert meta["initialized_at"]

        assert (root / "config.json").is_file()
        assert (root / "workflows" / "fix-tests.yml").is_file()
        assert (root / "workflows" / "review-fix.yml").is_file()
        assert "/.worktree/" in (git_fs.base_path / ".gitignore").read_text(encoding="utf-8")

    def test_second_init_is_non_destructive(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")

        config_path = git_fs.base_path / ".worktree" / "config.json"
        workflow_path = git_fs.base_path / ".worktree" / "workflows" / "fix-tests.yml"
        config_before = config_path.read_text(encoding="utf-8")
        workflow_path.write_text("edited by user\n", encoding="utf-8")
        meta_before = json.loads(
            (git_fs.base_path / ".worktree" / ".meta" / "bootstrap.json").read_text(encoding="utf-8")
        )

        init_command(tool_version="0.1.1")

        assert config_path.read_text(encoding="utf-8") == config_before
        assert workflow_path.read_text(encoding="utf-8") == "edited by user\n"
        meta_after = json.loads(
            (git_fs.base_path / ".worktree" / ".meta" / "bootstrap.json").read_text(encoding="utf-8")
        )
        assert meta_after["initialized_at"] == meta_before["initialized_at"]

    def test_repairs_missing_subdirectory(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")
        sessions = git_fs.base_path / ".worktree" / "sessions"
        sessions.rmdir()
        assert not sessions.exists()

        init_command(tool_version="0.1.1")

        assert sessions.is_dir()
        meta = json.loads((git_fs.base_path / ".worktree" / ".meta" / "bootstrap.json").read_text(encoding="utf-8"))
        assert meta["status"] == "repaired"


class InitCommandWorkflowSeedingTests:
    """Tests for starter workflow seeding behavior triggered by `wt init`."""

    def test_init_seeds_starter_workflows_in_fresh_repo(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        init_command(tool_version="0.1.1")

        workflows_dir = git_fs.base_path / ".worktree" / "workflows"
        assert (workflows_dir / "fix-tests.yml").is_file()
        assert (workflows_dir / "review-fix.yml").is_file()

    def test_init_does_not_overwrite_edited_workflow_files(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)

        init_command(tool_version="0.1.1")
        workflow_path = git_fs.base_path / ".worktree" / "workflows" / "fix-tests.yml"
        workflow_path.write_text("edited by user\n", encoding="utf-8")

        init_command(tool_version="0.1.1")

        assert workflow_path.read_text(encoding="utf-8") == "edited by user\n"


class InitCommandFailureTests:
    """Failure and edge paths for init_command."""

    def test_not_a_git_repo_exits_without_creating_worktree(
        self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(fs.base_path)
        with pytest.raises(typer.Exit) as exc:
            init_command(tool_version="0.1.1")
        assert exc.value.exit_code == 1
        assert not (fs.base_path / ".worktree").exists()

    def test_accepts_gitfile_style_repository(self, fs: FileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        """Linked worktrees / some submodules use a `.git` file, not a directory."""
        (fs.base_path / ".git").write_text("gitdir: /tmp/fake\n", encoding="utf-8")
        monkeypatch.chdir(fs.base_path)

        init_command(tool_version="0.1.1")

        assert (fs.base_path / ".worktree" / "config.json").is_file()

    def test_bootstrap_path_collision_exits(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)
        collision = git_fs.base_path / ".worktree"
        collision.write_text("not-a-directory\n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc:
            init_command(tool_version="0.1.1")
        assert exc.value.exit_code == 1
        assert collision.is_file()
        assert collision.read_text(encoding="utf-8") == "not-a-directory\n"

    def test_bootstrap_failure_exits(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)

        def boom(root_path, *, tool_version=None):
            return BootstrapResult(
                root_path=root_path,
                errors=["simulated bootstrap failure"],
            )

        monkeypatch.setattr("getworktree.cli.init.command.bootstrap_worktree", boom)
        with pytest.raises(typer.Exit) as exc:
            init_command(tool_version="0.1.1")
        assert exc.value.exit_code == 1

    def test_config_generation_failure_exits(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)

        def bad_config(*args, **kwargs):
            return ConfigGenerationResult(errors=["CONFIG_WRITE_FAILED"])

        monkeypatch.setattr("getworktree.cli.init.command.generate_default_config", bad_config)
        with pytest.raises(typer.Exit) as exc:
            init_command(tool_version="0.1.1")
        assert exc.value.exit_code == 1

    def test_workflow_seed_failure_exits(self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_fs.base_path)

        def bad_seed(*args, **kwargs):
            return WorkflowSeedResult(errors=["seed failed"])

        monkeypatch.setattr("getworktree.cli.init.command.seed_starter_workflows", bad_seed)
        with pytest.raises(typer.Exit) as exc:
            init_command(tool_version="0.1.1")
        assert exc.value.exit_code == 1

    def test_invalid_config_falls_back_to_default_db_path(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_fs.base_path)
        init_command(tool_version="0.1.1")
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.write_text("{not-json", encoding="utf-8")

        recorded: list[str] = []

        def capture_init_database(*, cwd=None, db_rel_path=None):
            recorded.append(db_rel_path)
            return Path(cwd or ".") / db_rel_path

        monkeypatch.setattr("getworktree.cli.init.command.init_database", capture_init_database)
        monkeypatch.setattr(
            "getworktree.cli.init.command.generate_default_config",
            lambda *a, **k: ConfigGenerationResult(
                skipped_existing=True,
                config_path=config_path,
            ),
        )
        monkeypatch.setattr(
            "getworktree.cli.init.command.seed_starter_workflows",
            lambda *a, **k: WorkflowSeedResult(),
        )
        monkeypatch.setattr(
            "getworktree.cli.init.command.bootstrap_worktree",
            lambda root_path, *, tool_version=None: BootstrapResult(root_path=root_path, root_created=False),
        )

        init_command(tool_version="0.1.1")
        assert recorded
        assert recorded[-1] == PathsConfig().db_path
