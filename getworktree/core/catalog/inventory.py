"""Catalog blueprint directory scanner, legacy migration engine, and inventory helper functions."""

from __future__ import annotations

import hashlib
from pathlib import Path

from getworktree.common.fs import atomic_write_text, scan_yaml_directory
from getworktree.core.catalog.models import CatalogScanResult, CatalogSubdirectoryScanResult
from getworktree.core.db import (
    CatalogDb,
    CatalogItemType,
    CatalogRecord,
)
from getworktree.core.templates.inventory import get_builtin_template


def get_catalog_dir(cwd: Path | None = None) -> Path:
    """Return absolute path to local `.worktree/catalog/` blueprint directory."""
    base_dir = (cwd or Path.cwd()).resolve()
    return base_dir / ".worktree" / "catalog"


def ensure_catalog_dirs(cwd: Path | None = None) -> Path:
    """Ensure directory structure under `.worktree/catalog/` exists."""
    catalog_dir = get_catalog_dir(cwd)
    for sub in ("workflows", "tasks", "steps"):
        (catalog_dir / sub).mkdir(parents=True, exist_ok=True)
    return catalog_dir


def migrate_legacy_workflows(cwd: Path | None = None) -> list[Path]:
    """Migrate legacy blueprint files from `.worktree/loops/` or `.worktree/workflows/` to `.worktree/catalog/workflows/`."""
    base_dir = (cwd or Path.cwd()).resolve()
    target_dir = get_catalog_dir(cwd) / "workflows"

    legacy_dirs = [
        base_dir / ".worktree" / "loops",
        base_dir / ".worktree" / "workflows",
    ]

    migrated: list[Path] = []
    for legacy_dir in legacy_dirs:
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            continue
        for item in sorted(legacy_dir.glob("*")):
            if item.is_file() and item.suffix.lower() in (".yml", ".yaml"):
                target_dir.mkdir(parents=True, exist_ok=True)
                dest = target_dir / item.name
                if not dest.exists():
                    item.rename(dest)
                    migrated.append(dest)

    return migrated


def compute_catalog_sha(item_type: CatalogItemType | str, content: str) -> tuple[str, str]:
    """Compute SHA-256 checksum and formatted SHA string (e.g. `workflow_a1b2c3d`)."""
    type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    sha = f"{type_str}_{checksum[:7]}"
    return sha, checksum


def _scan_catalog_subdirectories(
    *, cwd: Path | None = None, catalog_dir: Path, subdirs: list[tuple[CatalogItemType, Path]]
) -> CatalogSubdirectoryScanResult:
    scanned_records: list[CatalogRecord] = []
    errors: list[str] = []
    scanned_shas: set[str] = set()

    for item_type, sub_dir in subdirs:
        if not sub_dir.exists():
            continue

        yaml_files = scan_yaml_directory(sub_dir)
        for file_entry in yaml_files:
            sha, checksum = compute_catalog_sha(item_type, str(file_entry.content))
            rel_path = file_entry.path.relative_to(catalog_dir)

            try:
                record = CatalogDb(cwd).upsert(
                    sha=sha,
                    item_type=item_type,
                    name=file_entry.name,
                    path=rel_path,
                    checksum=checksum,
                )
                scanned_records.append(record)
                scanned_shas.add(sha)
            except Exception as exc:
                errors.append(f"Failed to index catalog record for '{rel_path}': {exc}")

    return CatalogSubdirectoryScanResult(scanned_records=scanned_records, errors=errors, scanned_shas=scanned_shas)


def scan_and_index_catalog(cwd: Path | None = None) -> CatalogScanResult:
    """Scan `.worktree/catalog/` subdirectories, compute SHA checksums, and sync SQLite database."""
    catalog_dir = ensure_catalog_dirs(cwd)
    migrate_legacy_workflows(cwd)

    subdirs: list[tuple[CatalogItemType, Path]] = [
        (CatalogItemType.WORKFLOW, catalog_dir / "workflows"),
        (CatalogItemType.TASK, catalog_dir / "tasks"),
        (CatalogItemType.STEP, catalog_dir / "steps"),
    ]
    scan_result = _scan_catalog_subdirectories(cwd=cwd, catalog_dir=catalog_dir, subdirs=subdirs)
    errors = scan_result.errors

    # Remove stale DB records for files no longer on disk
    try:
        db_items = CatalogDb(cwd).list()
        for record in db_items:
            if record.sha not in scan_result.scanned_shas:
                disk_file = catalog_dir / record.path
                if not disk_file.exists():
                    CatalogDb(cwd).delete(record.sha)
    except Exception as exc:
        errors.append(f"Error purging stale catalog DB records: {exc}")

    return CatalogScanResult(items=scan_result.scanned_records, errors=errors)


def create_catalog_item(
    item_type: CatalogItemType | str,
    name: str,
    template_name: str | None = None,
    cwd: Path | None = None,
) -> CatalogRecord:
    """Create a new catalog blueprint under `.worktree/catalog/<type>s/<name>.yml` and sync database.

    Raises:
        ValueError: If `item_type` is invalid or `template_name` is not found.
        FileExistsError: If a blueprint file already exists at the target path.
    """
    try:
        type_enum = item_type if isinstance(item_type, CatalogItemType) else CatalogItemType(str(item_type).lower())
    except ValueError as exc:
        allowed = ", ".join([t.value for t in CatalogItemType])
        raise ValueError(f"Invalid item_type '{item_type}'. Allowed choices: {allowed}") from exc

    catalog_dir = ensure_catalog_dirs(cwd)
    stem = name[:-4] if name.endswith(".yml") or name.endswith(".yaml") else name
    filename = f"{stem}.yml"
    target_path = catalog_dir / f"{type_enum.value}s" / filename

    if target_path.exists():
        rel_str = target_path.relative_to(catalog_dir)
        raise FileExistsError(f"Catalog blueprint collision at path '{rel_str}'")

    if template_name:
        tmpl = get_builtin_template(template_name, type_filter=type_enum.value)
        if tmpl is None:
            raise ValueError(f"Built-in template '{template_name}' of type '{type_enum.value}' not found.")
        content = tmpl.content
    else:
        if type_enum == CatalogItemType.WORKFLOW:
            content = f"name: {stem}\ndescription: Custom workflow blueprint\nsteps: []\n"
        elif type_enum == CatalogItemType.TASK:
            content = f"name: {stem}\ndescription: Custom task blueprint\nuse_git_worktree: false\ncommands: []\n"
        else:
            content = f"name: {stem}\ndescription: Custom step blueprint\naction: run\n"

    atomic_write_text(target_path, content)

    sha, checksum = compute_catalog_sha(type_enum, content)
    rel_path = target_path.relative_to(catalog_dir)

    return CatalogDb(cwd).upsert(
        sha=sha,
        item_type=type_enum,
        name=stem,
        path=rel_path,
        checksum=checksum,
    )


def get_catalog_item(
    sha_or_name: str,
    type_filter: CatalogItemType | str | None = None,
    cwd: Path | None = None,
) -> CatalogRecord | None:
    """Retrieve catalog blueprint record by SHA or name."""
    scan_and_index_catalog(cwd)

    item = CatalogDb(cwd).get_by_sha(sha_or_name)
    if item is not None:
        if type_filter:
            tf_str = type_filter.value if isinstance(type_filter, CatalogItemType) else str(type_filter).lower()
            if item.item_type.value != tf_str:
                return None
        return item

    return CatalogDb(cwd).get_by_name(sha_or_name, item_type=type_filter)


def delete_catalog_item_by_sha_or_name(
    sha_or_name: str,
    cwd: Path | None = None,
) -> CatalogRecord | None:
    """Delete a catalog blueprint file and its database record."""
    item = get_catalog_item(sha_or_name, cwd=cwd)
    if item is None:
        return None

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path
    if file_path.exists():
        file_path.unlink(missing_ok=True)

    CatalogDb(cwd).delete(item.sha)
    return item
