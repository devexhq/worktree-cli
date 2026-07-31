from __future__ import annotations

from pathlib import Path

from getworktree.core.loops.seeder import seed_starter_loops


def test_seed_starter_loops_creates_missing_files(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"

    result = seed_starter_loops(loops_dir)

    assert result.ok
    assert {path.name for path in result.created_files} == {
        "fix-tests.yml",
        "review-fix.yml",
    }
    assert (loops_dir / "fix-tests.yml").is_file()
    assert (loops_dir / "review-fix.yml").is_file()


def test_seed_starter_loops_skips_existing_files_by_default(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    target = loops_dir / "fix-tests.yml"
    target.write_text("custom\n", encoding="utf-8")

    result = seed_starter_loops(loops_dir)

    assert result.ok
    assert target in result.skipped_existing_files
    assert target.read_text(encoding="utf-8") == "custom\n"


def test_seed_starter_loops_overwrites_in_force_mode(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    target = loops_dir / "review-fix.yml"
    target.write_text("custom\n", encoding="utf-8")

    result = seed_starter_loops(loops_dir, force=True)

    assert result.ok
    assert target in result.overwritten_files
    assert "version: 1" in target.read_text(encoding="utf-8")


def test_seed_starter_loops_handles_partial_existing_state(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    existing = loops_dir / "fix-tests.yml"
    existing.write_text("custom\n", encoding="utf-8")

    result = seed_starter_loops(loops_dir)

    assert result.ok
    assert existing in result.skipped_existing_files
    assert (loops_dir / "review-fix.yml") in result.created_files


def test_seed_starter_loops_reports_directory_collisions(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    target = loops_dir / "fix-tests.yml"
    target.mkdir()

    result = seed_starter_loops(loops_dir)

    assert not result.ok
    assert any(str(target) in error for error in result.errors)
    assert (loops_dir / "review-fix.yml") in result.created_files
