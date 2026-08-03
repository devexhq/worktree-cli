"""Tests for `getworktree.core.loops.inventory`."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from getworktree.core.loops.inventory import (
    LoopInventoryStatus,
    build_loop_inventory,
)
from getworktree.core.loops.seeder import seed_starter_loops


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _template_text(name: str) -> str:
    root = resources.files("getworktree.core.templates.loops")
    with root.joinpath(name).open(encoding="utf-8") as handle:
        return handle.read()


def _minimal_valid(name: str, description: str = "desc") -> str:
    return f"version: 1\nname: {name}\ndescription: {description}\n"


class BuildLoopInventoryTests:
    """Tests for build_loop_inventory composition behavior."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopInventoryStatus.OK
        assert result.ok
        assert result.loops_dir == loops_dir.resolve()
        assert result.valid == []
        assert result.invalid == []
        assert result.errors == []
        assert result.warnings == []

    def test_all_valid_seeded_starters(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        assert seed_starter_loops(loops_dir).ok

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.invalid == []
        assert [entry.name for entry in result.valid] == [
            "fix-tests",
            "review-fix",
        ]
        assert all(entry.source_path.is_absolute() for entry in result.valid)
        assert len(result.valid) + len(result.invalid) == 2

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        assert seed_starter_loops(loops_dir).ok
        _write(loops_dir / "broken.yml", "version: [\n")
        _write(loops_dir / "noname.yml", "version: 1\ndescription: missing name\n")

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.errors == []
        assert [entry.name for entry in result.valid] == [
            "fix-tests",
            "review-fix",
        ]
        assert [entry.source_path.name for entry in result.invalid] == [
            "broken.yml",
            "noname.yml",
        ]
        assert result.invalid[0].name is None
        assert result.invalid[0].description is None
        assert result.invalid[0].status == "malformed_yaml"
        assert any(
            "LOOP_META_MALFORMED_YAML" in error for error in result.invalid[0].errors
        )
        assert any(
            "LOOP_META_MISSING_NAME" in error for error in result.invalid[1].errors
        )
        assert len(result.valid) + len(result.invalid) == 4

    def test_all_invalid(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "a.yml", "[]\n")
        _write(loops_dir / "b.yml", "version: 2\nname: x\ndescription: d\n")

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.valid == []
        assert [entry.source_path.name for entry in result.invalid] == [
            "a.yml",
            "b.yml",
        ]
        assert len(result.valid) + len(result.invalid) == 2

    def test_discovery_failure_passthrough(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-loops"

        result = build_loop_inventory(cwd=tmp_path, loops_dir=missing)

        assert result.status == LoopInventoryStatus.DISCOVERY_FAILED
        assert not result.ok
        assert result.valid == []
        assert result.invalid == []
        assert result.loops_dir == missing.resolve()
        assert any("LOOP_DIR_NOT_FOUND" in error for error in result.errors)

    def test_valid_ordering_by_name_then_path(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "z.yml", _minimal_valid("beta"))
        _write(loops_dir / "a.yml", _minimal_valid("alpha"))
        _write(loops_dir / "m.yml", _minimal_valid("alpha", "second alpha"))

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [(e.name, e.source_path.name) for e in result.valid] == [
            ("alpha", "a.yml"),
            ("alpha", "m.yml"),
            ("beta", "z.yml"),
        ]

    def test_invalid_ordering_by_filename(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "z-bad.yml", "[]\n")
        _write(loops_dir / "a-bad.yml", "version: [\n")

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [entry.source_path.name for entry in result.invalid] == [
            "a-bad.yml",
            "z-bad.yml",
        ]

    def test_duplicate_name_warnings(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "b.yml", _minimal_valid("fix-tests"))
        _write(loops_dir / "a.yml", _minimal_valid("fix-tests", "other"))
        _write(loops_dir / "solo.yml", _minimal_valid("unique"))

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert len(result.valid) == 3
        assert result.warnings == [
            "Duplicate loop name 'fix-tests' in multiple files: a.yml, b.yml"
        ]

    def test_invalid_entries_do_not_join_duplicate_warnings(
        self, tmp_path: Path
    ) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "ok.yml", _minimal_valid("fix-tests"))
        _write(loops_dir / "broken.yml", "version: [\n")

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.warnings == []
        assert len(result.invalid) == 1

    def test_unreadable_file_is_invalid_only(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        good = _write(loops_dir / "good.yml", _minimal_valid("good-loop"))
        secret = _write(loops_dir / "secret.yml", _minimal_valid("secret-loop"))
        secret.chmod(0)
        try:
            result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)
        finally:
            secret.chmod(0o600)

        assert result.ok
        if any(entry.source_path.name == "secret.yml" for entry in result.valid):
            # Root or environments that ignore file mode still keep inventory ok.
            assert [entry.name for entry in result.valid]
            return

        assert [entry.name for entry in result.valid] == ["good-loop"]
        assert result.valid[0].source_path == good.resolve()
        assert len(result.invalid) == 1
        assert result.invalid[0].source_path.name == "secret.yml"
        assert result.invalid[0].status == "unreadable"

    def test_explicit_loops_dir_does_not_need_config(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "only"
        loops_dir.mkdir()
        _write(loops_dir / "one.yml", _template_text("fix-tests.yml"))

        result = build_loop_inventory(cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert [entry.name for entry in result.valid] == ["fix-tests"]
