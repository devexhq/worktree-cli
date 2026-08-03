"""Resolve a logical loop name to one inventory entry."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.loops.discovery import DEFAULT_LOOPS_DIR, resolve_loops_dir
from getworktree.core.loops.inventory import (
    LoopInventoryStatus,
    LoopInventoryValidEntry,
    build_loop_inventory,
)
from getworktree.core.loops.metadata import LOOP_NAME_PATTERN


class LoopResolveStatus(StrEnum):
    """Classified outcomes for resolving a loop by name."""

    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID_NAME = "invalid_name"
    DISCOVERY_FAILED = "discovery_failed"


class LoopResolveResult(BaseModel):
    """Non-raising result of resolving one loop name against inventory."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopResolveStatus
    name: str
    loops_dir: Path
    entry: LoopInventoryValidEntry | None = None
    matches: list[LoopInventoryValidEntry] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when a unique or deterministically chosen entry was found."""
        return self.status == LoopResolveStatus.OK


def _error_invalid_name(name: str) -> str:
    return (
        f"Invalid loop name '{name}' (LOOP_RESOLVE_INVALID_NAME).\n"
        "Fix:\n"
        f"- use a name matching {LOOP_NAME_PATTERN.pattern}"
    )


def _error_not_found(name: str, loops_dir: Path) -> str:
    return (
        f"No loop named '{name}' in '{loops_dir.as_posix()}' "
        f"(LOOP_RESOLVE_NOT_FOUND).\n"
        "Fix:\n"
        "- run `wt loop list` to see available loops\n"
        "- add a definition under the loops directory"
    )


def _warning_duplicate_name(
    name: str,
    winner: LoopInventoryValidEntry,
    matches: list[LoopInventoryValidEntry],
) -> str:
    others = [
        entry.source_path.name
        for entry in matches
        if entry.source_path != winner.source_path
    ]
    also = ", ".join(others)
    return (
        f"Duplicate loop name '{name}'; using '{winner.source_path.name}' "
        f"(also found in: {also}) (LOOP_RESOLVE_DUPLICATE_NAME)."
    )


def _resolve_loops_dir_for_invalid_name(
    cwd: Path | None,
    *,
    loops_dir: Path | str | None,
    use_config: bool,
) -> Path:
    """Best-effort absolute loops_dir for invalid_name results only."""
    root = (cwd or Path.cwd()).expanduser().resolve()
    fallback = (root / DEFAULT_LOOPS_DIR).resolve()
    resolved, errors = resolve_loops_dir(
        cwd=root,
        loops_dir=loops_dir,
        use_config=use_config,
    )
    if errors:
        return fallback
    return resolved


def _match_sort_key(entry: LoopInventoryValidEntry) -> tuple[str, str]:
    return (entry.source_path.name, entry.source_path.as_posix())


def resolve_loop_by_name(
    name: str,
    cwd: Path | None = None,
    *,
    loops_dir: Path | str | None = None,
    use_config: bool = True,
) -> LoopResolveResult:
    """Resolve a loop name to one inventory entry.

    Non-raising primary API. Expected product failures (invalid name, missing
    name, discovery failure) are classified on the result. Duplicate valid
    names select a deterministic winner and emit a warning.

    Args:
        name: Logical loop name to resolve (exact, case-sensitive).
        cwd: Repository root for inventory/config resolution.
        loops_dir: Explicit loops directory override.
        use_config: When True and ``loops_dir`` is omitted, read
            ``paths.loops_dir`` from config via inventory/discovery.

    Returns:
        ``LoopResolveResult`` with absolute ``loops_dir`` and classified
        status. ``ok`` means an entry was selected.
    """
    requested = name

    if (
        not isinstance(requested, str)
        or not requested
        or not LOOP_NAME_PATTERN.fullmatch(requested)
    ):
        echo = requested if isinstance(requested, str) else str(requested)
        return LoopResolveResult(
            status=LoopResolveStatus.INVALID_NAME,
            name=echo,
            loops_dir=_resolve_loops_dir_for_invalid_name(
                cwd,
                loops_dir=loops_dir,
                use_config=use_config,
            ),
            errors=[_error_invalid_name(echo)],
        )

    inventory = build_loop_inventory(
        cwd=cwd,
        loops_dir=loops_dir,
        use_config=use_config,
    )

    if inventory.status == LoopInventoryStatus.DISCOVERY_FAILED:
        return LoopResolveResult(
            status=LoopResolveStatus.DISCOVERY_FAILED,
            name=requested,
            loops_dir=inventory.loops_dir,
            errors=list(inventory.errors),
            warnings=list(inventory.warnings),
        )

    matches = sorted(
        (entry for entry in inventory.valid if entry.name == requested),
        key=_match_sort_key,
    )
    warnings = list(inventory.warnings)

    if not matches:
        return LoopResolveResult(
            status=LoopResolveStatus.NOT_FOUND,
            name=requested,
            loops_dir=inventory.loops_dir,
            errors=[_error_not_found(requested, inventory.loops_dir)],
            warnings=warnings,
        )

    winner = matches[0]
    if len(matches) > 1:
        warnings.append(_warning_duplicate_name(requested, winner, matches))

    return LoopResolveResult(
        status=LoopResolveStatus.OK,
        name=requested,
        loops_dir=inventory.loops_dir,
        entry=winner,
        matches=list(matches),
        warnings=warnings,
    )
