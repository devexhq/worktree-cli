"""Verification tests for test harness fixtures and assertion helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import typer
from pydantic import BaseModel
from typer.testing import CliRunner

from tests.harness import ANY_UUID, assert_model_equal
from worktree.common.constants import REQUIRED_SUBDIRS


class DummyModel(BaseModel):
    """Pydantic model for model equality assertion tests."""

    model_config = {"strict": True}

    name: str
    count: int
    record_id: UUID
    timestamp: str = "2026-01-01T00:00:00Z"


class NestedDummyModel(BaseModel):
    """Pydantic model for nested equality assertion tests."""

    item: DummyModel
    label: str = "root"


class IsolatedWorkspaceFixtureTests:
    """Verification tests for isolated_workspace fixture."""

    def test_isolated_workspace_creates_worktree_structure(self, isolated_workspace: Path) -> None:
        dot_worktree = isolated_workspace / ".worktree"
        assert dot_worktree.is_dir()
        for subdir in REQUIRED_SUBDIRS:
            assert (dot_worktree / subdir).is_dir()
        assert (dot_worktree / "sandboxes").is_dir()
        assert (dot_worktree / "catalog").is_dir()


class GitRepoFixtureTests:
    """Verification tests for git_repo fixture."""

    def test_git_repo_initializes_valid_git_repository_on_main(self, git_repo: Path) -> None:
        assert (git_repo / ".git").is_dir()

        branch_proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert branch_proc.stdout.strip() == "main"

        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        head_sha = head_proc.stdout.strip()
        assert len(head_sha) == 40

    @pytest.mark.parametrize(
        ("config_key", "expected_value"),
        [
            pytest.param("user.name", "Test User", id="name"),
            pytest.param("user.email", "test@example.com", id="email"),
        ],
    )
    def test_git_repo_configures_local_user_identity(
        self,
        git_repo: Path,
        config_key: str,
        expected_value: str,
    ) -> None:
        proc = subprocess.run(
            ["git", "config", config_key],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert proc.stdout.strip() == expected_value


class CliRunnerFixtureTests:
    """Verification tests for cli_runner fixture."""

    def test_cli_runner_sets_columns_and_no_color(self, cli_runner: CliRunner) -> None:
        app = typer.Typer()

        @app.command()
        def check_env() -> None:
            assert os.environ.get("COLUMNS") == "160"
            assert os.environ.get("NO_COLOR") == "1"

        result = cli_runner.invoke(app)
        assert result.exit_code == 0


class AssertModelEqualTests:
    """Verification tests for assert_model_equal helper."""

    def test_assert_model_equal_passes_on_identical_models(self) -> None:
        record_id = uuid4()
        model = DummyModel(name="item", count=42, record_id=record_id, timestamp="2026-01-01T00:00:00Z")
        assert_model_equal(
            model,
            DummyModel(name="item", count=42, record_id=record_id, timestamp="2026-01-01T00:00:00Z"),
        )

    def test_assert_model_equal_fails_on_type_mismatch(self) -> None:
        model = DummyModel(name="item", count=42, record_id=uuid4(), timestamp="2026-01-01T00:00:00Z")
        with pytest.raises(AssertionError, match="type mismatch"):
            assert_model_equal(model, NestedDummyModel(item=model, label="root"))

    def test_assert_model_equal_rejects_expected_left_at_defaults(self) -> None:
        model = DummyModel(name="item", count=42, record_id=uuid4(), timestamp="2026-01-01T00:00:00Z")
        with pytest.raises(AssertionError, match=r"left .*timestamp.* to defaults"):
            assert_model_equal(model, DummyModel(name="item", count=42, record_id=model.record_id))

    def test_assert_model_equal_fails_on_field_difference(self) -> None:
        model = DummyModel(name="item", count=42, record_id=uuid4(), timestamp="2026-01-01T00:00:00Z")
        with pytest.raises(AssertionError, match="count"):
            assert_model_equal(
                model,
                DummyModel(name="item", count=99, record_id=model.record_id, timestamp="2026-01-01T00:00:00Z"),
            )

    def test_assert_model_equal_matches_unownable_field_via_matcher(self) -> None:
        """A field the test cannot pin (a DB-minted UUID) is stated as a matcher via model_construct."""
        model = DummyModel(name="item", count=42, record_id=uuid4(), timestamp="2026-01-01T00:00:00Z")
        assert_model_equal(
            model,
            DummyModel.model_construct(
                name="item",
                count=42,
                record_id=ANY_UUID,
                timestamp="2026-01-01T00:00:00Z",
            ),
        )

    def test_assert_model_equal_passes_on_identical_nested_models(self) -> None:
        record_id = uuid4()
        model = NestedDummyModel(
            item=DummyModel(name="sub", count=1, record_id=record_id, timestamp="2026-01-01T00:00:00Z"),
            label="root",
        )
        assert_model_equal(
            model,
            NestedDummyModel(
                item=DummyModel(name="sub", count=1, record_id=record_id, timestamp="2026-01-01T00:00:00Z"),
                label="root",
            ),
        )

    def test_assert_model_equal_fails_on_nested_field_difference(self) -> None:
        model = NestedDummyModel(
            item=DummyModel(name="sub", count=1, record_id=uuid4(), timestamp="2026-01-01T00:00:00Z"),
            label="root",
        )
        with pytest.raises(AssertionError, match=r"item\.timestamp"):
            assert_model_equal(
                model,
                NestedDummyModel(
                    item=DummyModel(name="sub", count=1, record_id=model.item.record_id, timestamp="different"),
                    label="root",
                ),
            )

    def test_assert_model_equal_passes_on_identical_model_sequences(self) -> None:
        record_id = uuid4()
        item = DummyModel(name="sub", count=1, record_id=record_id, timestamp="2026-01-01T00:00:00Z")

        class SequenceHolder(BaseModel):
            items: list[DummyModel]

        model = SequenceHolder(items=[item, item])
        assert_model_equal(model, SequenceHolder(items=[item, item]))

    def test_assert_model_equal_fails_on_sequence_length_mismatch(self) -> None:
        record_id = uuid4()
        item = DummyModel(name="sub", count=1, record_id=record_id, timestamp="2026-01-01T00:00:00Z")

        class SequenceHolder(BaseModel):
            items: list[DummyModel]

        model = SequenceHolder(items=[item, item])
        with pytest.raises(AssertionError, match="length mismatch"):
            assert_model_equal(model, SequenceHolder(items=[item]))

    def test_assert_model_equal_fails_on_sequence_item_difference(self) -> None:
        record_id = uuid4()
        item = DummyModel(name="sub", count=1, record_id=record_id, timestamp="2026-01-01T00:00:00Z")
        other = DummyModel(name="sub", count=2, record_id=record_id, timestamp="2026-01-01T00:00:00Z")

        class SequenceHolder(BaseModel):
            items: list[DummyModel]

        model = SequenceHolder(items=[item])
        with pytest.raises(AssertionError, match=r"items\[0\]"):
            assert_model_equal(model, SequenceHolder(items=[other]))
