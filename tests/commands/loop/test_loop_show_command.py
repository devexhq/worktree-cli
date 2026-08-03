"""Tests for `wt loop show`."""

from __future__ import annotations

import subprocess
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from getworktree.cli import app
from getworktree.commands.loop.command import loop_show_command
from getworktree.core.config.generator import generate_default_config
from getworktree.core.loops.inventory import LoopInventoryValidEntry
from getworktree.core.loops.resolve import LoopResolveResult, LoopResolveStatus
from getworktree.core.loops.seeder import seed_starter_loops
from getworktree.core.loops.validate import (
    LoopValidationResult,
    LoopValidationStatus,
)

runner = CliRunner()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return tmp_path


def _init_with_loops(repo: Path) -> Path:
    config_path = repo / ".worktree" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    assert generate_default_config(config_path, project_name=repo.name).ok
    loops_dir = repo / ".worktree" / "loops"
    assert seed_starter_loops(loops_dir).ok
    return loops_dir


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.loops")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


def _assert_failure_panel(stdout: str, stderr: str = "") -> str:
    combined = stdout + stderr
    assert "Loop Show Failed" in combined
    assert "Status: valid" not in stdout
    assert not any(line.startswith("Loop: ") for line in stdout.splitlines())
    return combined


class LoopShowCommandDirectTests:
    """Direct loop_show_command tests."""

    def test_success_seeded_fix_tests(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        source = (loops_dir / "fix-tests.yml").resolve()

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        lines = out.splitlines()
        assert lines[0] == "Loop: fix-tests"
        assert lines[1] == f"Source: {source.as_posix()}"
        assert lines[2] == "Status: valid"
        assert lines[3] == ""
        assert "Description:" in out
        assert "  command: pytest" in out
        assert "  args: []" in out
        assert "  reject_binary_changes: null" in out
        assert out.endswith("\n")
        assert "Loop Show Failed" not in out

    def test_success_with_duplicate_warning(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        # Second file with same logical name.
        alt = loops_dir / "fix-tests-copy.yml"
        alt.write_text(_template_text("fix-tests.yml"), encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 0

        out = capsys.readouterr().out
        assert "Status: valid with warnings" in out
        assert "Warnings:" in out
        assert "LOOP_RESOLVE_DUPLICATE_NAME" in out
        assert "Description:" in out

    def test_missing_loop_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("no-such-loop", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_panel(capsys.readouterr().out)
        assert "LOOP_RESOLVE_NOT_FOUND" in combined

    def test_invalid_name_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("Bad_Name", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_panel(capsys.readouterr().out)
        assert "LOOP_RESOLVE_INVALID_NAME" in combined

    def test_discovery_failure_exits_one(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        # No config / no loops dir → discovery failure when use_config default.

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_panel(capsys.readouterr().out)
        assert (
            "LOOP_CONFIG_UNAVAILABLE" in combined
            or "LOOP_DIR_NOT_FOUND" in combined
            or "CONFIG_" in combined
        )

    def test_schema_invalid_after_resolve(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        bad = loops_dir / "broken.yml"
        bad.write_text(
            "version: 1\nname: broken\ndescription: incomplete body only\n",
            encoding="utf-8",
        )

        with pytest.raises(typer.Exit) as exc_info:
            loop_show_command("broken", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_panel(capsys.readouterr().out)
        assert "LOOP_INVALID_SCHEMA" in combined

    def test_malformed_yaml_after_resolve(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        # Metadata requires version/name/description; write valid metadata then
        # corrupt only after inventory would accept? Full file must parse for
        # metadata. Use a file that metadata accepts is hard with malformed YAML.
        # Instead write a mapping-valid-for-metadata then replace with malformed
        # after seeding a name via a crafted inventory path is overkill—write
        # YAML that is valid enough for metadata but fail full validation is
        # covered above. For malformed: identity fields as strings with bad indent.
        path = loops_dir / "malformed.yml"
        # Valid for list metadata parse (mapping with three fields) requires valid YAML.
        # True malformed YAML never resolves via inventory. Simulate via mock.
        entry = LoopInventoryValidEntry(
            name="malformed",
            description="x",
            version=1,
            source_path=path.resolve(),
        )
        path.write_text("version: [\n", encoding="utf-8")
        fake_resolve = LoopResolveResult(
            status=LoopResolveStatus.OK,
            name="malformed",
            loops_dir=loops_dir.resolve(),
            entry=entry,
            matches=[entry],
        )
        with (
            patch(
                "getworktree.commands.loop.command.resolve_loop_by_name",
                return_value=fake_resolve,
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            loop_show_command("malformed", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        combined = _assert_failure_panel(capsys.readouterr().out)
        assert "LOOP_INVALID_MALFORMED_YAML" in combined

    def test_validate_failure_with_resolve_warnings(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        path = loops_dir / "broken.yml"
        path.write_text(
            "version: 1\nname: broken\ndescription: incomplete\n",
            encoding="utf-8",
        )
        entry = LoopInventoryValidEntry(
            name="broken",
            description="incomplete",
            version=1,
            source_path=path.resolve(),
        )
        fake_resolve = LoopResolveResult(
            status=LoopResolveStatus.OK,
            name="broken",
            loops_dir=loops_dir.resolve(),
            entry=entry,
            matches=[entry],
            warnings=["dup warning (LOOP_RESOLVE_DUPLICATE_NAME)."],
        )
        with (
            patch(
                "getworktree.commands.loop.command.resolve_loop_by_name",
                return_value=fake_resolve,
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            loop_show_command("broken", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Loop Show Failed" in out
        assert "Warnings:" in out
        assert "LOOP_RESOLVE_DUPLICATE_NAME" in out

    def test_empty_resolve_errors_fallback(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        fake = LoopResolveResult(
            status=LoopResolveStatus.NOT_FOUND,
            name="x",
            loops_dir=git_repo / ".worktree" / "loops",
            errors=[],
        )
        with (
            patch(
                "getworktree.commands.loop.command.resolve_loop_by_name",
                return_value=fake,
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            loop_show_command("x", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        assert "Failed to resolve loop." in capsys.readouterr().out

    def test_empty_validate_errors_fallback(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(git_repo)
        loops_dir = _init_with_loops(git_repo)
        path = loops_dir / "fix-tests.yml"
        entry = LoopInventoryValidEntry(
            name="fix-tests",
            description="d",
            version=1,
            source_path=path.resolve(),
        )
        fake_resolve = LoopResolveResult(
            status=LoopResolveStatus.OK,
            name="fix-tests",
            loops_dir=loops_dir.resolve(),
            entry=entry,
            matches=[entry],
        )
        fake_validate = LoopValidationResult(
            status=LoopValidationStatus.INVALID,
            source_path=path.resolve(),
            errors=[],
        )
        with (
            patch(
                "getworktree.commands.loop.command.resolve_loop_by_name",
                return_value=fake_resolve,
            ),
            patch(
                "getworktree.commands.loop.command.validate_loop_result",
                return_value=fake_validate,
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            loop_show_command("fix-tests", cwd=git_repo)
        assert exc_info.value.exit_code == 1
        assert "Loop definition is invalid." in capsys.readouterr().out


class LoopShowCliTests:
    """CliRunner coverage for registration and help."""

    def test_help_text(self) -> None:
        result = runner.invoke(app, ["loop", "show", "--help"])
        assert result.exit_code == 0
        assert "Show a human-readable summary of a loop definition." in result.stdout
        assert "NAME" in result.stdout.upper() or "name" in result.stdout

    def test_cli_success(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        result = runner.invoke(app, ["loop", "show", "fix-tests"])
        assert result.exit_code == 0
        assert "Loop: fix-tests" in result.stdout
        assert "Status: valid" in result.stdout

    def test_cli_missing(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo)
        _init_with_loops(git_repo)
        result = runner.invoke(app, ["loop", "show", "nope"])
        assert result.exit_code == 1
        assert "Loop Show Failed" in result.stdout

    def test_old_freeform_loop_command_gone(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_repo)
        result = runner.invoke(app, ["loop", "true"])
        # Without subcommand name, Typer should not treat "true" as shell command.
        assert result.exit_code != 0
