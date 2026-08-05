"""Tests for `getworktree.core.loops.resolve`."""

from __future__ import annotations

from pathlib import Path

from getworktree.core.loops.resolve import (
    LoopResolveStatus,
    resolve_loop_by_name,
)
from getworktree.core.loops.seeder import seed_starter_loops


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _minimal_valid(name: str, description: str = "desc") -> str:
    return f"version: 1\nname: {name}\ndescription: {description}\n"


class ResolveLoopByNameTests:
    """Tests for resolve_loop_by_name classification and winner order."""

    def test_unique_valid_match(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        assert seed_starter_loops(loops_dir).ok

        result = resolve_loop_by_name("fix-tests", cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopResolveStatus.OK
        assert result.ok
        assert result.name == "fix-tests"
        assert result.loops_dir == loops_dir.resolve()
        assert result.entry is not None
        assert result.entry.name == "fix-tests"
        assert result.entry.source_path == (loops_dir / "fix-tests.yml").resolve()
        assert result.matches == [result.entry]
        assert result.errors == []
        assert result.warnings == []

    def test_not_found_empty_directory(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()

        result = resolve_loop_by_name("missing-loop", cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopResolveStatus.NOT_FOUND
        assert not result.ok
        assert result.entry is None
        assert result.matches == []
        assert any("LOOP_RESOLVE_NOT_FOUND" in error for error in result.errors)
        assert "missing-loop" in result.errors[0]
        assert loops_dir.resolve().as_posix() in result.errors[0]
        assert "wt workflow list" in result.errors[0]

    def test_not_found_when_only_invalid_files(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "broken.yml", "version: [\n")
        _write(
            loops_dir / "named-but-invalid.yml",
            "version: 2\nname: ghost\ndescription: bad version\n",
        )

        result = resolve_loop_by_name("ghost", cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopResolveStatus.NOT_FOUND
        assert result.entry is None
        assert result.matches == []
        assert any("LOOP_RESOLVE_NOT_FOUND" in error for error in result.errors)

    def test_case_sensitive_name_match(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "ok.yml", _minimal_valid("fix-tests"))

        result = resolve_loop_by_name("Fix-Tests", cwd=tmp_path, loops_dir=loops_dir)

        # Uppercase fails name pattern before inventory (invalid_name).
        assert result.status == LoopResolveStatus.INVALID_NAME

        result_lower = resolve_loop_by_name(
            "fix-tests", cwd=tmp_path, loops_dir=loops_dir
        )
        assert result_lower.ok
        assert result_lower.entry is not None

    def test_duplicate_names_deterministic_winner(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        later = _write(
            loops_dir / "fix-tests.yaml", _minimal_valid("fix-tests", "yaml")
        )
        first = _write(loops_dir / "fix-tests.yml", _minimal_valid("fix-tests", "yml"))
        other = _write(
            loops_dir / "other-fix-tests.yml",
            _minimal_valid("fix-tests", "other"),
        )

        result = resolve_loop_by_name("fix-tests", cwd=tmp_path, loops_dir=loops_dir)

        assert result.status == LoopResolveStatus.OK
        assert result.ok
        assert result.entry is not None
        # Winner order: source_path.name, then full POSIX path.
        # fix-tests.yaml < fix-tests.yml < other-fix-tests.yml
        assert result.entry.source_path == later.resolve()
        assert [m.source_path.name for m in result.matches] == [
            "fix-tests.yaml",
            "fix-tests.yml",
            "other-fix-tests.yml",
        ]
        assert first.resolve() in {m.source_path for m in result.matches}
        assert other.resolve() in {m.source_path for m in result.matches}
        assert result.errors == []
        assert any(
            "LOOP_RESOLVE_DUPLICATE_NAME" in warning for warning in result.warnings
        )
        assert any(
            "Duplicate loop name 'fix-tests' in multiple files:" in warning
            for warning in result.warnings
        )
        resolver_warning = next(
            w for w in result.warnings if "LOOP_RESOLVE_DUPLICATE_NAME" in w
        )
        assert "using 'fix-tests.yaml'" in resolver_warning
        assert "also found in:" in resolver_warning
        assert "fix-tests.yml" in resolver_warning
        assert "other-fix-tests.yml" in resolver_warning
        # Resolver warning is appended after inventory warnings.
        assert result.warnings[-1] == resolver_warning

    def test_duplicate_winner_by_filename_then_posix(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "b.yml", _minimal_valid("shared"))
        winner = _write(loops_dir / "a.yml", _minimal_valid("shared", "a"))

        result = resolve_loop_by_name("shared", cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == winner.resolve()
        assert [m.source_path.name for m in result.matches] == ["a.yml", "b.yml"]

    def test_discovery_failed_copies_inventory_errors(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-loops"

        result = resolve_loop_by_name("fix-tests", cwd=tmp_path, loops_dir=missing)

        assert result.status == LoopResolveStatus.DISCOVERY_FAILED
        assert not result.ok
        assert result.entry is None
        assert result.matches == []
        assert result.loops_dir == missing.resolve()
        assert any("LOOP_DIR_NOT_FOUND" in error for error in result.errors)
        assert not any("LOOP_RESOLVE_" in error for error in result.errors)

    def test_invalid_name_empty_string(self, tmp_path: Path) -> None:
        result = resolve_loop_by_name("", cwd=tmp_path, loops_dir=tmp_path / "loops")

        assert result.status == LoopResolveStatus.INVALID_NAME
        assert result.name == ""
        assert result.entry is None
        assert result.matches == []
        assert any("LOOP_RESOLVE_INVALID_NAME" in error for error in result.errors)
        assert result.loops_dir.is_absolute()

    def test_invalid_name_whitespace_uppercase_underscore_pathlike(
        self, tmp_path: Path
    ) -> None:
        cases = ["   ", "Bad_Name", "has_underscore", "../x", "a/b", "Fix-Tests"]
        for name in cases:
            result = resolve_loop_by_name(
                name, cwd=tmp_path, loops_dir=tmp_path / "loops"
            )
            assert result.status == LoopResolveStatus.INVALID_NAME, name
            assert result.name == name
            assert any("LOOP_RESOLVE_INVALID_NAME" in e for e in result.errors), name
            assert "^[a-z0-9][a-z0-9-]*$" in result.errors[0]

    def test_invalid_name_does_not_require_loops_dir(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Invalid name must not call inventory (no discovery IO)."""
        import getworktree.core.loops.resolve as resolve_mod

        def _boom(*_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("build_loop_inventory should not be called")

        monkeypatch.setattr(resolve_mod, "build_loop_inventory", _boom)

        result = resolve_loop_by_name("Bad_Name", cwd=tmp_path)

        assert result.status == LoopResolveStatus.INVALID_NAME
        assert result.loops_dir == (tmp_path / ".worktree/loops").resolve()

    def test_invalid_entries_never_win(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        good = _write(loops_dir / "good.yml", _minimal_valid("alpha"))
        _write(
            loops_dir / "bad.yml",
            "version: 1\nname: alpha\n",  # missing description → invalid
        )

        result = resolve_loop_by_name("alpha", cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == good.resolve()
        assert len(result.matches) == 1
        assert result.warnings == []

    def test_pass_through_unrelated_inventory_warnings(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        _write(loops_dir / "a.yml", _minimal_valid("dup"))
        _write(loops_dir / "b.yml", _minimal_valid("dup", "other"))
        solo = _write(loops_dir / "solo.yml", _minimal_valid("solo"))

        result = resolve_loop_by_name("solo", cwd=tmp_path, loops_dir=loops_dir)

        assert result.ok
        assert result.entry is not None
        assert result.entry.source_path == solo.resolve()
        assert any(
            "Duplicate loop name 'dup' in multiple files:" in w for w in result.warnings
        )
        assert not any("LOOP_RESOLVE_DUPLICATE_NAME" in w for w in result.warnings)

    def test_exported_from_package(self) -> None:
        from getworktree.core.loops import (
            LoopResolveResult,
            LoopResolveStatus,
            resolve_loop_by_name as exported,
        )

        assert exported is resolve_loop_by_name
        assert LoopResolveStatus.OK.value == "ok"
        assert LoopResolveResult.model_fields["status"]
