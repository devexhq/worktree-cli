"""Unit tests for the core status collector."""

from __future__ import annotations

import os
import stat
import subprocess

import pytest

from tests.helpers import FileSystem, GitFileSystem
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.db import (
    BlueprintKind,
    RunsRepository,
    RunStatus,
    SandboxesRepository,
)
from worktree.core.git import (
    GitNotFoundError,
    GitPlumbingTimeoutError,
    GitRunner,
)
from worktree.core.status.services.collector import collect_status


class TestStatusCollector:
    """Test suite for worktree.core.status.collect_status."""

    def test_collect_status_clean_worktree(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test status collection in a healthy, initialized workspace with database and catalog."""
        monkeypatch.chdir(git_fs.base_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature-status"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )

        git_fs.create_config_file(
            agent={"model": "gpt-4o", "provider": "openai"},
            sandbox={"max_active_sandboxes": 3},
        )
        git_fs.create_workflow_file("deploy")
        git_fs.create_task_file("lint-task")
        git_fs.create_step_file("test-step")

        # Initialize DB and insert a run
        runs_repo = RunsRepository(git_fs.base_path)
        runs_repo.create(
            session_id="sess-001",
            blueprint_name="deploy",
            kind=BlueprintKind.WORKFLOW,
            status=RunStatus.COMPLETED,
        )

        sandboxes_repo = SandboxesRepository(git_fs.base_path)
        sandboxes_repo.create(
            id="sb-001",
            branch_name="wt/sb-001",
            base_commit="HEAD",
            sandbox_path=git_fs.base_path / ".worktree" / "sandboxes" / "sb-001",
        )

        result = collect_status(git_fs.base_path)

        assert result.ok
        assert result.is_initialized
        assert result.root_dir == git_fs.base_path.resolve()

        # Git
        assert result.git.is_git_repo
        assert result.git.branch == "feature-status"
        assert not result.git.is_dirty
        assert result.git.uncommitted_files == 0

        # Config
        assert result.config.is_valid
        assert result.config.status == ConfigLoadStatus.OK
        assert result.config.config is not None
        assert result.config.config.agent.model == "gpt-4o"
        assert result.config.errors == []

        # Catalog
        assert result.catalog.exists
        assert result.catalog.workflows_count == 1
        assert result.catalog.tasks_count == 1
        assert result.catalog.steps_count == 1
        assert result.catalog.total_items == 3
        assert result.catalog.invalid_items == 0
        assert "deploy" in result.catalog.item_names
        assert "lint-task" in result.catalog.item_names
        assert "run-test-step" in result.catalog.item_names or "test-step" in result.catalog.item_names

        # Database
        assert result.database.exists
        assert result.database.is_accessible
        assert result.database.total_runs == 1

        # Sandboxes
        assert result.sandboxes.active_sandboxes == 1
        assert result.sandboxes.total_sandboxes == 1
        assert result.sandboxes.max_active_sandboxes == 3

        # Warnings
        assert result.warnings == []

    def test_collect_status_dirty_worktree(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test status collection with dirty working directory and untracked files."""
        monkeypatch.chdir(git_fs.base_path)
        subprocess.run(
            ["git", "checkout", "-b", "feature-dirty"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )
        git_fs.create_config_file(agent={"model": "gpt-4o"})
        RunsRepository(git_fs.base_path)

        # Modify tracked file and add untracked file
        untracked = git_fs.base_path / "new_file.txt"
        untracked.write_text("hello", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert result.git.is_dirty
        assert result.git.uncommitted_files >= 1
        assert any("Working tree has" in w for w in result.warnings)

    def test_collect_status_detached_head(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test git status collection when HEAD is detached."""
        monkeypatch.chdir(git_fs.base_path)
        git_fs.create_config_file(agent={"model": "gpt-4o"})
        RunsRepository(git_fs.base_path)

        commit_hash = GitRunner.run(["rev-parse", "HEAD"], path=git_fs.base_path).strip()
        subprocess.run(["git", "checkout", commit_hash], cwd=git_fs.base_path, check=True, capture_output=True)

        result = collect_status(git_fs.base_path)

        assert result.git.is_git_repo
        assert result.git.branch == "HEAD (detached)"

    def test_collect_status_non_git_directory(
        self,
        fs: FileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test status collection in a directory outside any git repository."""
        monkeypatch.chdir(fs.base_path)

        result = collect_status(fs.base_path)

        assert not result.ok
        assert not result.git.is_git_repo
        assert result.git.branch == "none"
        assert not result.git.is_dirty
        assert result.git.uncommitted_files == 0

    def test_collect_status_git_not_found(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test graceful handling when git binary is missing."""

        def mock_run(*args: object, **kwargs: object) -> str:
            raise GitNotFoundError("git not found")

        monkeypatch.setattr(GitRunner, "run", mock_run)

        result = collect_status(git_fs.base_path)

        assert not result.git.is_git_repo
        assert result.git.branch == "unknown"
        assert not result.git.is_dirty
        assert result.git.uncommitted_files == 0
        assert not result.ok

    def test_collect_status_git_timeout(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test graceful handling when git plumbing commands time out."""

        def mock_run(*args: object, **kwargs: object) -> str:
            raise GitPlumbingTimeoutError("git timed out")

        monkeypatch.setattr(GitRunner, "run", mock_run)

        result = collect_status(git_fs.base_path)

        assert not result.git.is_git_repo
        assert result.git.branch == "unknown"
        assert not result.git.is_dirty
        assert result.git.uncommitted_files == 0
        assert not result.ok

    def test_collect_status_uninitialized_workspace(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test uninitialized workspace without .worktree/ or config.json."""
        result = collect_status(git_fs.base_path)

        assert not result.ok
        assert not result.is_initialized
        assert result.config.status == ConfigLoadStatus.NOT_FOUND
        assert not result.config.is_valid
        assert "Worktree workspace is not initialized. Run 'wt init' to configure." in result.warnings

    def test_collect_status_malformed_config(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test workspace with malformed JSON in .worktree/config.json."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{invalid_json: true", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert not result.ok
        assert result.config.status == ConfigLoadStatus.MALFORMED_JSON
        assert not result.config.is_valid
        assert len(result.config.errors) > 0

    def test_collect_status_missing_catalog_directory(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test catalog status when .worktree/catalog does not exist."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})

        result = collect_status(git_fs.base_path)

        assert not result.catalog.exists
        assert result.catalog.total_items == 0
        assert result.catalog.workflows_count == 0
        assert result.catalog.tasks_count == 0
        assert result.catalog.steps_count == 0
        assert result.catalog.invalid_items == 0
        assert result.catalog.item_names == []

    def test_collect_status_invalid_catalog_blueprint(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test catalog collection with invalid YAML blueprint files."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})
        RunsRepository(git_fs.base_path)
        git_fs.create_workflow_file("valid-wf")

        bad_file = git_fs.base_path / ".worktree" / "catalog" / "tasks" / "bad.yml"
        bad_file.parent.mkdir(parents=True, exist_ok=True)
        bad_file.write_text("invalid: [yaml: broken", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert not result.ok  # Because invalid_items > 0
        assert result.catalog.exists
        assert result.catalog.total_items == 2
        assert result.catalog.workflows_count == 1
        assert result.catalog.tasks_count == 1
        assert result.catalog.invalid_items == 1
        assert "1 invalid blueprint file(s) detected in catalog." in result.warnings

    def test_collect_status_missing_database(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test database status when .worktree/data.db is missing."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})

        result = collect_status(git_fs.base_path)

        assert not result.ok
        assert not result.database.exists
        assert not result.database.is_accessible
        assert result.database.total_runs == 0

    def test_collect_status_corrupted_database(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test database status when .worktree/data.db is corrupted."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})
        db_path = git_fs.base_path / ".worktree" / "data.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text("NOT A SQLITE DATABASE", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert not result.ok
        assert result.database.exists
        assert not result.database.is_accessible
        assert result.database.total_runs == 0

    def test_collect_status_sandboxes_directory_fallback(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Test sandbox status fallback to directory inspection when database is missing."""
        git_fs.create_config_file(
            agent={"model": "gpt-4o"},
            sandbox={"max_active_sandboxes": 4},
        )
        sb1 = git_fs.base_path / ".worktree" / "sandboxes" / "sb-1"
        sb2 = git_fs.base_path / ".worktree" / "sandboxes" / "sb-2"
        sb1.mkdir(parents=True, exist_ok=True)
        sb2.mkdir(parents=True, exist_ok=True)

        result = collect_status(git_fs.base_path)

        assert result.sandboxes.active_sandboxes == 2
        assert result.sandboxes.total_sandboxes == 2
        assert result.sandboxes.max_active_sandboxes == 4

    def test_collect_status_warnings_deterministic_order(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that all 6 warnings appear in the exact deterministic order defined in FR-7."""
        monkeypatch.chdir(git_fs.base_path)
        # Ensure we are on main branch
        subprocess.run(["git", "checkout", "-B", "main"], cwd=git_fs.base_path, check=True, capture_output=True)

        # 1. Uninitialized workspace (missing config.json)
        # 2. Primary branch ('main')
        # 3. Dirty working tree (uncommitted files)
        # 4. Missing agent model (not evaluated when config is not loaded, tested next)
        # 5. High sandbox limit (defaults to 5 when config missing, tested next)
        # 6. Invalid catalog items
        (git_fs.base_path / "dirty.txt").write_text("dirty content", encoding="utf-8")

        catalog_tasks = git_fs.base_path / ".worktree" / "catalog" / "tasks"
        catalog_tasks.mkdir(parents=True, exist_ok=True)
        (catalog_tasks / "broken.yml").write_text("bad: [yaml", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert len(result.warnings) == 4
        assert result.warnings[0] == "Worktree workspace is not initialized. Run 'wt init' to configure."
        assert result.warnings[1] == "Active branch is 'main'. Automated workflows on primary branches are discouraged."
        assert "Working tree has" in result.warnings[2]
        assert result.warnings[3] == "1 invalid blueprint file(s) detected in catalog."

        # Now test with config containing no agent model and sandbox limit > 5 on main branch with dirty files
        git_fs.create_config_file(
            agent={"model": None},
            sandbox={"max_active_sandboxes": 8},
        )
        RunsRepository(git_fs.base_path)

        result2 = collect_status(git_fs.base_path)
        assert len(result2.warnings) == 5
        assert (
            result2.warnings[0] == "Active branch is 'main'. Automated workflows on primary branches are discouraged."
        )
        assert "Working tree has" in result2.warnings[1]
        assert result2.warnings[2] == "Agent model is not configured (agent.model is null)."
        assert result2.warnings[3] == "max_active_sandboxes (8) is unusually high."
        assert result2.warnings[4] == "1 invalid blueprint file(s) detected in catalog."

    def test_collect_status_pure_execution_immutability(
        self,
        git_fs: GitFileSystem,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify collect_status produces zero console output and does not mutate the filesystem."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})

        # Record files before
        files_before = set(git_fs.base_path.rglob("*"))

        result = collect_status(git_fs.base_path)
        captured = capsys.readouterr()

        assert result is not None
        assert captured.out == ""
        assert captured.err == ""

        # Verify no data.db was created by collect_status
        assert not (git_fs.base_path / ".worktree" / "data.db").exists()
        files_after = set(git_fs.base_path.rglob("*"))
        assert files_before == files_after

    def test_collect_status_git_rev_parse_not_true(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test git status collection when rev-parse returns a string other than 'true'."""
        monkeypatch.setattr(GitRunner, "run", lambda *args, **kwargs: "false")

        result = collect_status(git_fs.base_path)

        assert not result.git.is_git_repo
        assert result.git.branch == "none"
        assert not result.git.is_dirty
        assert result.git.uncommitted_files == 0

    def test_collect_status_sandboxes_db_query_error(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fallback when database is accessible for runs but sandboxes query raises an exception."""
        git_fs.create_config_file(agent={"model": "gpt-4o"})
        runs_repo = RunsRepository(git_fs.base_path)
        runs_repo.create(
            session_id="sess-test",
            blueprint_name="test-bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )

        sb1 = git_fs.base_path / ".worktree" / "sandboxes" / "sb-fallback"
        sb1.mkdir(parents=True, exist_ok=True)

        def mock_list(*args: object, **kwargs: object) -> list[object]:
            raise RuntimeError("DB query failure")

        monkeypatch.setattr(SandboxesRepository, "list", mock_list)

        result = collect_status(git_fs.base_path)

        assert result.database.is_accessible
        assert result.sandboxes.active_sandboxes == 1
        assert result.sandboxes.total_sandboxes == 1

    def test_collect_status_warnings_includes_cleaned_config_error(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify cleaned config errors are included in result.warnings when config is malformed."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{\ninvalid_json: true\n", encoding="utf-8")

        result = collect_status(git_fs.base_path)

        assert any(
            w.startswith("Malformed config.json: Expecting property name enclosed in double quotes")
            and "(CONFIG_MALFORMED_JSON)" in w
            for w in result.warnings
        )

    def test_collect_status_warnings_ignores_config_errors_when_not_found(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify config errors are ignored and only uninitialized warning is included when config is missing."""
        subprocess.run(
            ["git", "checkout", "-b", "feature-test"],
            cwd=git_fs.base_path,
            check=True,
            capture_output=True,
        )
        result = collect_status(git_fs.base_path)

        assert result.warnings == ["Worktree workspace is not initialized. Run 'wt init' to configure."]

    def test_collect_status_fixes_for_uninitialized_workspace(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains initialization guidance for uninitialized workspace."""
        result = collect_status(git_fs.base_path)
        assert result.fixes == ["Run 'wt init' to initialize Worktree in this repository."]

    def test_collect_status_fixes_for_non_git_repo(
        self,
        fs: FileSystem,
    ) -> None:
        """Verify result.fixes contains git init guidance for non-git repository with valid config."""
        fs.create_config_file(agent={"model": "gpt-4o"})
        result = collect_status(fs.base_path)
        assert result.fixes == ["Run 'git init' or navigate to a Git repository."]

    def test_collect_status_fixes_for_malformed_json(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains JSON repair guidance for malformed config."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{bad json: true", encoding="utf-8")
        result = collect_status(git_fs.base_path)
        assert result.fixes == ["Repair JSON syntax in .worktree/config.json or restore from backup."]

    def test_collect_status_fixes_for_schema_invalid(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains schema repair guidance for invalid config schema."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}", encoding="utf-8")
        result = collect_status(git_fs.base_path)
        assert result.fixes == [
            "Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys."
        ]

    def test_collect_status_fixes_for_root_not_object(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains root object guidance when config root is an array."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('["not", "an", "object"]', encoding="utf-8")
        result = collect_status(git_fs.base_path)
        assert result.fixes == ["Ensure .worktree/config.json contains a JSON object root."]

    def test_collect_status_fixes_for_path_is_directory(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains removal guidance when config path is a directory."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.mkdir(parents=True, exist_ok=True)
        result = collect_status(git_fs.base_path)
        assert result.fixes == ["Remove directory at .worktree/config.json and run 'wt init'."]

    def test_collect_status_fixes_for_unreadable(
        self,
        git_fs: GitFileSystem,
    ) -> None:
        """Verify result.fixes contains permissions guidance when config file is unreadable."""
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}", encoding="utf-8")
        config_path.chmod(0)
        try:
            if os.access(config_path, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            result = collect_status(git_fs.base_path)
            assert result.fixes == ["Check file permissions for .worktree/config.json."]
        finally:
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
