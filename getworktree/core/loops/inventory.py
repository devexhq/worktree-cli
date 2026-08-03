"""Compose loop discovery and metadata parse into a partial-success inventory."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.loops.discovery import discover_loop_files
from getworktree.core.loops.metadata import parse_loop_metadata


class LoopInventoryStatus(StrEnum):
    """Classified outcomes for building a loop inventory."""

    OK = "ok"
    DISCOVERY_FAILED = "discovery_failed"


class LoopInventoryValidEntry(BaseModel):
    """One successfully parsed loop definition in the inventory."""

    model_config = {"extra": "forbid", "strict": True}

    name: str
    description: str
    version: int
    source_path: Path


class LoopInventoryInvalidEntry(BaseModel):
    """One discovered loop file that failed metadata parse."""

    model_config = {"extra": "forbid", "strict": True}

    source_path: Path
    status: str
    errors: list[str] = Field(default_factory=list)
    name: None = None
    description: None = None


class LoopInventoryResult(BaseModel):
    """Non-raising inventory of valid and invalid loop definitions."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopInventoryStatus
    loops_dir: Path
    valid: list[LoopInventoryValidEntry] = Field(default_factory=list)
    invalid: list[LoopInventoryInvalidEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when discovery succeeded (invalid entries may remain)."""
        return self.status == LoopInventoryStatus.OK


def _duplicate_name_warnings(
    valid: list[LoopInventoryValidEntry],
) -> list[str]:
    by_name: dict[str, list[LoopInventoryValidEntry]] = defaultdict(list)
    for entry in valid:
        by_name[entry.name].append(entry)

    warnings: list[str] = []
    for name in sorted(by_name):
        entries = by_name[name]
        if len(entries) < 2:
            continue
        file_names = sorted(entry.source_path.name for entry in entries)
        joined = ", ".join(file_names)
        warnings.append(f"Duplicate loop name '{name}' in multiple files: {joined}")
    return warnings


def build_loop_inventory(
    cwd: Path | None = None,
    *,
    loops_dir: Path | str | None = None,
    use_config: bool = True,
) -> LoopInventoryResult:
    """Discover loop files and parse list metadata with partial success.

    Non-raising composition API. Directory-level discovery failures become
    ``discovery_failed`` with empty partitions. Per-file metadata failures
    never abort the inventory when discovery itself succeeded.

    Args:
        cwd: Repository root for discovery/config resolution.
        loops_dir: Explicit loops directory override.
        use_config: When True and ``loops_dir`` is omitted, read
            ``paths.loops_dir`` from config via discovery.

    Returns:
        ``LoopInventoryResult`` with absolute ``loops_dir`` and partitioned
        entries. ``ok`` means discovery succeeded, not that ``invalid`` is
        empty.
    """
    discovery = discover_loop_files(
        cwd=cwd,
        loops_dir=loops_dir,
        use_config=use_config,
    )

    if not discovery.ok:
        return LoopInventoryResult(
            status=LoopInventoryStatus.DISCOVERY_FAILED,
            loops_dir=discovery.loops_dir,
            errors=list(discovery.errors),
        )

    valid: list[LoopInventoryValidEntry] = []
    invalid: list[LoopInventoryInvalidEntry] = []

    for path in discovery.paths:
        parsed = parse_loop_metadata(path)
        if parsed.ok and parsed.metadata is not None:
            valid.append(
                LoopInventoryValidEntry(
                    name=parsed.metadata.name,
                    description=parsed.metadata.description,
                    version=parsed.metadata.version,
                    source_path=parsed.metadata.source_path,
                )
            )
            continue

        errors = list(parsed.errors)
        if not errors:
            errors = [f"Loop definition is invalid. ({parsed.status.value})"]
        invalid.append(
            LoopInventoryInvalidEntry(
                source_path=parsed.source_path,
                status=parsed.status.value,
                errors=errors,
            )
        )

    valid.sort(key=lambda entry: (entry.name, entry.source_path.as_posix()))
    invalid.sort(
        key=lambda entry: (
            entry.source_path.name,
            entry.source_path.as_posix(),
        )
    )

    return LoopInventoryResult(
        status=LoopInventoryStatus.OK,
        loops_dir=discovery.loops_dir,
        valid=valid,
        invalid=invalid,
        warnings=_duplicate_name_warnings(valid),
    )
