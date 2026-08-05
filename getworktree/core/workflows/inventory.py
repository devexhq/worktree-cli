"""Compose workflow discovery and metadata parse into a partial-success inventory."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.workflows.discovery import discover_workflow_files
from getworktree.core.workflows.metadata import parse_workflow_metadata


class WorkflowInventoryStatus(StrEnum):
    """Classified outcomes for building a workflow inventory."""

    OK = "ok"
    DISCOVERY_FAILED = "discovery_failed"


class WorkflowInventoryValidEntry(BaseModel):
    """One successfully parsed workflow definition in the inventory."""

    model_config = {"extra": "forbid", "strict": True}

    name: str
    description: str
    version: int
    source_path: Path


class WorkflowInventoryInvalidEntry(BaseModel):
    """One discovered workflow file that failed metadata parse."""

    model_config = {"extra": "forbid", "strict": True}

    source_path: Path
    status: str
    errors: list[str] = Field(default_factory=list)
    name: None = None
    description: None = None


class WorkflowInventoryResult(BaseModel):
    """Non-raising inventory of valid and invalid workflow definitions."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowInventoryStatus
    workflows_dir: Path
    valid: list[WorkflowInventoryValidEntry] = Field(default_factory=list)
    invalid: list[WorkflowInventoryInvalidEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when discovery succeeded (invalid entries may remain)."""
        return self.status == WorkflowInventoryStatus.OK


def _duplicate_name_warnings(
    valid: list[WorkflowInventoryValidEntry],
) -> list[str]:
    by_name: dict[str, list[WorkflowInventoryValidEntry]] = defaultdict(list)
    for entry in valid:
        by_name[entry.name].append(entry)

    warnings: list[str] = []
    for name in sorted(by_name):
        entries = by_name[name]
        if len(entries) < 2:
            continue
        file_names = sorted(entry.source_path.name for entry in entries)
        joined = ", ".join(file_names)
        warnings.append(f"Duplicate workflow name '{name}' in multiple files: {joined}")
    return warnings


def build_workflow_inventory(
    cwd: Path | None = None,
    *,
    workflows_dir: Path | str | None = None,
    use_config: bool = True,
) -> WorkflowInventoryResult:
    """Discover workflow files and parse list metadata with partial success.

    Non-raising composition API. Directory-level discovery failures become
    ``discovery_failed`` with empty partitions. Per-file metadata failures
    never abort the inventory when discovery itself succeeded.

    Args:
        cwd: Repository root for discovery/config resolution.
        workflows_dir: Explicit workflows directory override.
        use_config: When True and ``workflows_dir`` is omitted, read
            ``paths.workflows_dir`` from config via discovery.

    Returns:
        ``WorkflowInventoryResult`` with absolute ``workflows_dir`` and partitioned
        entries. ``ok`` means discovery succeeded, not that ``invalid`` is
        empty.
    """
    discovery = discover_workflow_files(
        cwd=cwd,
        workflows_dir=workflows_dir,
        use_config=use_config,
    )

    if not discovery.ok:
        return WorkflowInventoryResult(
            status=WorkflowInventoryStatus.DISCOVERY_FAILED,
            workflows_dir=discovery.workflows_dir,
            errors=list(discovery.errors),
        )

    valid: list[WorkflowInventoryValidEntry] = []
    invalid: list[WorkflowInventoryInvalidEntry] = []

    for path in discovery.paths:
        parsed = parse_workflow_metadata(path)
        if parsed.ok and parsed.metadata is not None:
            valid.append(
                WorkflowInventoryValidEntry(
                    name=parsed.metadata.name,
                    description=parsed.metadata.description,
                    version=parsed.metadata.version,
                    source_path=parsed.metadata.source_path,
                )
            )
            continue

        errors = list(parsed.errors)
        if not errors:
            errors = [f"Workflow definition is invalid. ({parsed.status.value})"]
        invalid.append(
            WorkflowInventoryInvalidEntry(
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

    return WorkflowInventoryResult(
        status=WorkflowInventoryStatus.OK,
        workflows_dir=discovery.workflows_dir,
        valid=valid,
        invalid=invalid,
        warnings=_duplicate_name_warnings(valid),
    )
