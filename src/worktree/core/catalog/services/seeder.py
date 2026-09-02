"""Seed packaged catalog blueprint templates into `.worktree/catalog/<type>s/wt/`."""

from __future__ import annotations

from pathlib import Path

from worktree.common.filesystem import Filesystem
from worktree.common.lock import WorkspaceLock
from worktree.common.utils import display_path
from worktree.core.catalog.models import SeedResult
from worktree.core.db import CatalogItemType


def _iter_source_files(source_dir: Path) -> list[Path]:
    return sorted(p for p in source_dir.rglob("*") if p.is_file())


def _seed_one_file(source_file: Path, target_path: Path, *, force: bool, result: SeedResult) -> None:
    if target_path.exists() and target_path.is_dir():
        result.errors.append(f"{display_path(target_path)} exists as a directory, not a file.")
        return

    existed = target_path.exists()
    if existed and not force:
        result.skipped_existing_files.append(target_path)
        return

    try:
        text = source_file.read_text(encoding="utf-8")
        Filesystem.atomic_write_text(target_path, text)
    except OSError as exc:
        result.errors.append(f"{display_path(target_path)}: {exc}")
        return

    if existed:
        result.overwritten_files.append(target_path)
    else:
        result.created_files.append(target_path)


def seed_catalog_templates(
    item_type: CatalogItemType,
    path: Path,
    *,
    force: bool = False,
) -> SeedResult:
    """Copy curated `wt/` seed files for `item_type` into `.worktree/catalog/<type>s/wt/`."""
    with WorkspaceLock(path):
        result = SeedResult()

        source_dir = Filesystem().catalog_templates_dir / f"{item_type.value}s" / "wt"
        if not source_dir.is_dir():
            return result

        target_dir = Filesystem(path).catalog_dir / f"{item_type.value}s" / "wt"

        for source_file in _iter_source_files(Path(str(source_dir))):
            rel_name = source_file.relative_to(Path(str(source_dir)))
            target_path = target_dir / rel_name
            _seed_one_file(source_file, target_path, force=force, result=result)

        return result


def seed_all_catalog_templates(
    path: Path,
    *,
    force: bool = False,
) -> SeedResult:
    """Seed curated `wt/` templates for workflows, tasks, and steps; aggregate the results."""
    with WorkspaceLock(path):
        aggregate = SeedResult()

        for item_type in (CatalogItemType.WORKFLOW, CatalogItemType.TASK, CatalogItemType.STEP):
            result = seed_catalog_templates(item_type, path=path, force=force)
            aggregate.created_files.extend(result.created_files)
            aggregate.skipped_existing_files.extend(result.skipped_existing_files)
            aggregate.overwritten_files.extend(result.overwritten_files)
            aggregate.warnings.extend(result.warnings)
            aggregate.errors.extend(result.errors)

        return aggregate
