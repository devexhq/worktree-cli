"""Resolve a logical workflow name to one inventory entry."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.workflows.discovery import (
    DEFAULT_WORKFLOWS_DIR,
    resolve_workflows_dir,
)
from getworktree.core.workflows.inventory import (
    WorkflowInventoryStatus,
    WorkflowInventoryValidEntry,
    build_workflow_inventory,
)
from getworktree.core.workflows.metadata import WORKFLOW_NAME_PATTERN


class WorkflowResolveStatus(StrEnum):
    """Classified outcomes for resolving a workflow by name."""

    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID_NAME = "invalid_name"
    DISCOVERY_FAILED = "discovery_failed"


class WorkflowResolveResult(BaseModel):
    """Non-raising result of resolving one workflow name against inventory."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowResolveStatus
    name: str
    workflows_dir: Path
    entry: WorkflowInventoryValidEntry | None = None
    matches: list[WorkflowInventoryValidEntry] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a unique or deterministically chosen entry was found."""
        return self.status == WorkflowResolveStatus.OK


def _warning_duplicate_name(
    name: str,
    winner: WorkflowInventoryValidEntry,
    matches: list[WorkflowInventoryValidEntry],
) -> str:
    others = [entry.source_path.name for entry in matches if entry.source_path != winner.source_path]
    also = ", ".join(others)
    return (
        f"Duplicate workflow name '{name}'; using '{winner.source_path.name}' "
        f"(also found in: {also}) (WORKFLOW_RESOLVE_DUPLICATE_NAME)."
    )


def _resolve_workflows_dir_for_invalid_name(
    cwd: Path | None,
    *,
    workflows_dir: Path | str | None,
    use_config: bool,
) -> Path:
    """Best-effort absolute workflows_dir for invalid_name results only."""
    root = (cwd or Path.cwd()).expanduser().resolve()
    fallback = (root / DEFAULT_WORKFLOWS_DIR).resolve()
    resolved, errors = resolve_workflows_dir(
        cwd=root,
        workflows_dir=workflows_dir,
        use_config=use_config,
    )
    if errors:
        return fallback
    return resolved


def _match_sort_key(entry: WorkflowInventoryValidEntry) -> tuple[str, str]:
    return (entry.source_path.name, entry.source_path.as_posix())


def resolve_workflow_by_name(
    name: str,
    cwd: Path | None = None,
    *,
    workflows_dir: Path | str | None = None,
    use_config: bool = True,
) -> WorkflowResolveResult:
    """Resolve a workflow name to one inventory entry.

    Non-raising primary API. Expected product failures (invalid name, missing
    name, discovery failure) are classified on the result. Duplicate valid
    names select a deterministic winner and emit a warning.

    Args:
        name: Logical workflow name to resolve (exact, case-sensitive).
        cwd: Repository root for inventory/config resolution.
        workflows_dir: Explicit workflows directory override.
        use_config: When True and ``workflows_dir`` is omitted, read
            ``paths.workflows_dir`` from config via inventory/discovery.

    Returns:
        ``WorkflowResolveResult`` with absolute ``workflows_dir`` and classified
        status. ``ok`` means an entry was selected.
    """
    requested = name

    if not isinstance(requested, str) or not requested or not WORKFLOW_NAME_PATTERN.fullmatch(requested):
        echo = requested if isinstance(requested, str) else str(requested)
        return WorkflowResolveResult(
            status=WorkflowResolveStatus.INVALID_NAME,
            name=echo,
            workflows_dir=_resolve_workflows_dir_for_invalid_name(
                cwd,
                workflows_dir=workflows_dir,
                use_config=use_config,
            ),
            errors=[
                f"Invalid workflow name '{echo}' (WORKFLOW_RESOLVE_INVALID_NAME).\n"
                "Fix:\n"
                f"- use a name matching {WORKFLOW_NAME_PATTERN.pattern}"
            ],
        )

    inventory = build_workflow_inventory(
        cwd=cwd,
        workflows_dir=workflows_dir,
        use_config=use_config,
    )

    if inventory.status == WorkflowInventoryStatus.DISCOVERY_FAILED:
        return WorkflowResolveResult(
            status=WorkflowResolveStatus.DISCOVERY_FAILED,
            name=requested,
            workflows_dir=inventory.workflows_dir,
            errors=list(inventory.errors),
            warnings=list(inventory.warnings),
        )

    matches = sorted(
        (entry for entry in inventory.valid if entry.name == requested),
        key=_match_sort_key,
    )
    warnings = list(inventory.warnings)

    if not matches:
        return WorkflowResolveResult(
            status=WorkflowResolveStatus.NOT_FOUND,
            name=requested,
            workflows_dir=inventory.workflows_dir,
            errors=[
                f"No workflow named '{requested}' in "
                f"'{inventory.workflows_dir.as_posix()}' "
                f"(WORKFLOW_RESOLVE_NOT_FOUND).\n"
                "Fix:\n"
                "- run `wt workflow list` to see available workflows\n"
                "- add a definition under the workflows directory"
            ],
            warnings=warnings,
        )

    winner = matches[0]
    if len(matches) > 1:
        warnings.append(_warning_duplicate_name(requested, winner, matches))

    return WorkflowResolveResult(
        status=WorkflowResolveStatus.OK,
        name=requested,
        workflows_dir=inventory.workflows_dir,
        entry=winner,
        matches=list(matches),
        warnings=warnings,
    )
