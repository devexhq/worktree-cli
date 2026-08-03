"""Seed packaged starter loop definitions into a worktree loops directory."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from getworktree.common.utils import display_path
from getworktree.core.loops.validate import LOOP_VALIDATOR


class LoopSeedResult(BaseModel):
    """Outcome of seeding starter loop files."""

    model_config = {
        "extra": "forbid",
        "strict": True,
    }

    created_files: list[Path] = Field(default_factory=list)
    skipped_existing_files: list[Path] = Field(default_factory=list)
    overwritten_files: list[Path] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when seeding completed without blocking errors."""
        return not self.errors


def _template_root() -> resources.abc.Traversable:
    return resources.files("getworktree.core.templates.loops")


def _load_template_text(template_name: str) -> str:
    with _template_root().joinpath(template_name).open(encoding="utf-8") as handle:
        return handle.read()


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def _load_and_validate_template(template_name: str) -> dict[str, Any]:
    template_text = _load_template_text(template_name)
    try:
        parsed = yaml.safe_load(template_text)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised by runtime errors
        raise ValueError(f"YAML parse failed for {template_name}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{template_name} must contain a YAML mapping at the root")

    validation = LOOP_VALIDATOR.validate(parsed)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    return parsed


def seed_starter_loops(loops_dir: Path, force: bool = False) -> LoopSeedResult:
    """Seed packaged starter loops into ``loops_dir`` without overwriting user edits by default."""
    result = LoopSeedResult()
    loops_dir = loops_dir.resolve()

    if loops_dir.exists() and loops_dir.is_file():
        result.errors.append(
            f"{display_path(loops_dir)} exists as a file, not a directory."
        )
        return result

    try:
        loops_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.errors.append(f"Could not create {display_path(loops_dir)}: {exc}")
        return result

    for template_name, target_name in (
        ("fix-tests.yml", "fix-tests.yml"),
        ("review-fix.yml", "review-fix.yml"),
    ):
        target_path = loops_dir / target_name
        if target_path.exists() and target_path.is_dir():
            result.errors.append(
                f"{display_path(target_path)} exists as a directory, not a file."
            )
            continue

        try:
            _load_and_validate_template(template_name)
        except (OSError, ValueError) as exc:
            result.errors.append(f"{display_path(target_path)}: {exc}")
            continue

        if target_path.exists() and target_path.is_file():
            if not force:
                result.skipped_existing_files.append(target_path)
                continue
            result.overwritten_files.append(target_path)
        else:
            result.created_files.append(target_path)

        try:
            template_text = _load_template_text(template_name)
            _atomic_write_text(target_path, _ensure_trailing_newline(template_text))
        except OSError as exc:
            result.errors.append(f"{display_path(target_path)}: {exc}")

    return result
