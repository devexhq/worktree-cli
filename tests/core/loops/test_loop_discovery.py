"""Tests for `getworktree.core.loops.discovery`."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from getworktree.core.config.generator import generate_default_config
from getworktree.core.loops.discovery import (
    DEFAULT_LOOPS_DIR,
    LOOP_FILE_SUFFIXES,
    LoopDiscoveryStatus,
    discover_loop_files,
    resolve_loops_dir,
)
from getworktree.core.loops.seeder import seed_starter_loops


def _write_config(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class ResolveLoopsDirTests:
    """Tests for resolve_loops_dir."""

    def test_explicit_absolute_path_wins(self, tmp_path: Path) -> None:
        explicit = tmp_path / "custom" / "loops"
        resolved, errors = resolve_loops_dir(cwd=tmp_path, loops_dir=explicit)
        assert errors == []
        assert resolved == explicit.resolve()
        assert resolved.is_absolute()

    def test_explicit_relative_path_resolves_against_cwd(self, tmp_path: Path) -> None:
        resolved, errors = resolve_loops_dir(cwd=tmp_path, loops_dir="alt/loops")
        assert errors == []
        assert resolved == (tmp_path / "alt" / "loops").resolve()

    def test_default_without_config(self, tmp_path: Path) -> None:
        resolved, errors = resolve_loops_dir(cwd=tmp_path, use_config=False)
        assert errors == []
        assert resolved == (tmp_path / DEFAULT_LOOPS_DIR).resolve()

    def test_uses_config_paths_loops_dir(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        result_gen = generate_default_config(config_path, "demo")
        assert result_gen.ok
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw["paths"]["loops_dir"] = "custom-loops"
        _write_config(config_path, raw)

        resolved, errors = resolve_loops_dir(cwd=tmp_path)
        assert errors == []
        assert resolved == (tmp_path / "custom-loops").resolve()

    def test_config_unavailable_when_missing(self, tmp_path: Path) -> None:
        resolved, errors = resolve_loops_dir(cwd=tmp_path, use_config=True)
        assert resolved == (tmp_path / DEFAULT_LOOPS_DIR).resolve()
        assert len(errors) == 1
        assert "LOOP_CONFIG_UNAVAILABLE" in errors[0]


class DiscoverLoopFilesTests:
    """Tests for discover_loop_files status and inclusion rules."""

    def test_ok_empty_directory(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopDiscoveryStatus.OK
        assert result.ok
        assert result.loops_dir == loops_dir.resolve()
        assert result.paths == []
        assert result.errors == []

    def test_ok_seeded_layout(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".worktree" / "loops"
        seed = seed_starter_loops(loops_dir)
        assert seed.ok

        result = discover_loop_files(
            cwd=tmp_path,
            loops_dir=loops_dir,
            use_config=False,
        )

        assert result.ok
        assert [path.name for path in result.paths] == [
            "fix-tests.yml",
            "review-fix.yml",
        ]
        assert all(path.is_absolute() for path in result.paths)

    def test_not_found(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "missing-loops"

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopDiscoveryStatus.NOT_FOUND
        assert not result.ok
        assert result.paths == []
        assert any("LOOP_DIR_NOT_FOUND" in error for error in result.errors)
        assert str(loops_dir.resolve()) in result.errors[0]

    def test_not_a_directory(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.write_text("not a dir\n", encoding="utf-8")

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopDiscoveryStatus.NOT_A_DIRECTORY
        assert not result.ok
        assert result.paths == []
        assert any("LOOP_DIR_NOT_A_DIRECTORY" in error for error in result.errors)

    def test_unreadable_directory(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        loops_dir.chmod(0)
        try:
            result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)
        finally:
            loops_dir.chmod(stat.S_IRWXU)

        if os.geteuid() == 0:
            pytest.skip("root can list unreadable directories")

        assert result.status == LoopDiscoveryStatus.UNREADABLE
        assert not result.ok
        assert result.paths == []
        assert any("LOOP_DIR_UNREADABLE" in error for error in result.errors)

    def test_config_unavailable(self, tmp_path: Path) -> None:
        result = discover_loop_files(cwd=tmp_path, use_config=True)

        assert result.status == LoopDiscoveryStatus.CONFIG_UNAVAILABLE
        assert not result.ok
        assert result.paths == []
        assert any("LOOP_CONFIG_UNAVAILABLE" in error for error in result.errors)
        assert result.loops_dir == (tmp_path / DEFAULT_LOOPS_DIR).resolve()

    def test_extension_filtering_and_sort_order(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        (loops_dir / "b.yaml").write_text("b\n", encoding="utf-8")
        (loops_dir / "a.yml").write_text("a\n", encoding="utf-8")
        (loops_dir / "fix-tests.yml").write_text("f\n", encoding="utf-8")
        (loops_dir / "readme.md").write_text("docs\n", encoding="utf-8")
        (loops_dir / "notes.json").write_text("{}\n", encoding="utf-8")
        (loops_dir / "nested.yml.bak").write_text("bak\n", encoding="utf-8")

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [path.name for path in result.paths] == [
            "a.yml",
            "b.yaml",
            "fix-tests.yml",
        ]
        assert all(path.suffix in LOOP_FILE_SUFFIXES for path in result.paths)

    def test_ignore_hidden_private_and_subdirs(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        (loops_dir / ".hidden.yml").write_text("h\n", encoding="utf-8")
        (loops_dir / "_private.yml").write_text("p\n", encoding="utf-8")
        (loops_dir / "subdir").mkdir()
        (loops_dir / "subdir" / "nested.yml").write_text("n\n", encoding="utf-8")
        (loops_dir / "keep.yml").write_text("k\n", encoding="utf-8")

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["keep.yml"]

    def test_skips_broken_symlink_without_failing(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        (loops_dir / "good.yml").write_text("g\n", encoding="utf-8")
        broken = loops_dir / "broken.yml"
        broken.symlink_to(tmp_path / "missing-target.yml")

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["good.yml"]

    def test_explicit_override_does_not_require_config(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "only-loops"
        loops_dir.mkdir()
        (loops_dir / "z.yml").write_text("z\n", encoding="utf-8")

        result = discover_loop_files(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [path.name for path in result.paths] == ["z.yml"]

    def test_uses_config_when_no_explicit_dir(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True)
        assert generate_default_config(config_path, "demo").ok
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw["paths"]["loops_dir"] = "from-config"
        _write_config(config_path, raw)
        loops_dir = tmp_path / "from-config"
        loops_dir.mkdir()
        (loops_dir / "one.yaml").write_text("1\n", encoding="utf-8")

        result = discover_loop_files(cwd=tmp_path)

        assert result.ok
        assert result.loops_dir == loops_dir.resolve()
        assert [path.name for path in result.paths] == ["one.yaml"]
