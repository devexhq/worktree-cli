"""Catalog blueprint directory scanner, legacy migration engine, and inventory helper functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from getworktree.common.exceptions import DefinitionLoadError, DefinitionValidationError
from getworktree.common.fs import (
    atomic_write_text,
    compute_content_checksum,
    delete_file,
    read_yaml_file,
    scan_yaml_directory,
)
from getworktree.common.models import (
    DefinitionResolutionResult,
    DefinitionResolutionStatus,
    YamlFile,
)
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


def compute_catalog_sha(item_type: CatalogItemType | str, content: str) -> tuple[str, str]:
    """Compute SHA-256 checksum and formatted SHA string (e.g. `workflow_a1b2c3d`)."""
    type_str = item_type.value if isinstance(item_type, CatalogItemType) else str(item_type)
    checksum = compute_content_checksum(content)
    sha = f"{type_str}_{checksum[:7]}"
    return sha, checksum


def _index_catalog_entry(
    cwd: Path | None,
    item_type: CatalogItemType,
    catalog_dir: Path,
    file_entry: YamlFile,
) -> tuple[CatalogRecord | None, str | None]:
    """Upsert a single scanned YAML file into the catalog DB, or return an error message."""
    if file_entry.error:
        return None, file_entry.error

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
        return record, None
    except Exception as exc:
        return None, f"Failed to index catalog record for '{rel_path}': {exc}"


def _scan_catalog_subdirectories(
    *, cwd: Path | None = None, catalog_dir: Path, subdirs: list[tuple[CatalogItemType, Path]]
) -> CatalogSubdirectoryScanResult:
    scanned_records: list[CatalogRecord] = []
    errors: list[str] = []
    scanned_shas: set[str] = set()

    for item_type, sub_dir in subdirs:
        if not sub_dir.exists():
            continue

        for file_entry in scan_yaml_directory(sub_dir):
            record, error = _index_catalog_entry(cwd, item_type, catalog_dir, file_entry)
            if error:
                errors.append(error)
                continue
            scanned_records.append(record)
            scanned_shas.add(record.sha)

    return CatalogSubdirectoryScanResult(scanned_records=scanned_records, errors=errors, scanned_shas=scanned_shas)


def scan_and_index_catalog(cwd: Path | None = None) -> CatalogScanResult:
    """Scan `.worktree/catalog/` subdirectories, compute SHA checksums, and sync SQLite database."""
    catalog_dir = ensure_catalog_dirs(cwd)

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


def _get_initial_template_content(type_enum: CatalogItemType, stem: str, template_name: str | None) -> str:
    if template_name:
        template = get_builtin_template(template_name, type_filter=type_enum.value)
        if template is None:
            raise ValueError(f"Built-in template '{template_name}' of type '{type_enum.value}' not found.")
        return template.content

    if type_enum == CatalogItemType.WORKFLOW:
        return f"name: {stem}\ndescription: Custom workflow blueprint\nsteps: []\n"
    if type_enum == CatalogItemType.TASK:
        return f"name: {stem}\ndescription: Custom task blueprint\nuse_git_worktree: false\ncommands: []\n"
    return f"name: {stem}\ndescription: Custom step blueprint\naction: run\n"


def create_catalog_item(
    item_type: CatalogItemType | str,
    name: str,
    template_name: str | None = None,
    cwd: Path | None = None,
) -> CatalogRecord:
    """Create a new catalog blueprint under `.worktree/catalog/<type>s/<name>.yml` and sync database."""
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
        rel_path = target_path.relative_to(catalog_dir)
        raise FileExistsError(f"Catalog blueprint collision at path '{rel_path}'")

    content = _get_initial_template_content(type_enum, stem, template_name)
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


def _find_catalog_matches(
    cwd: Path | None,
    sha_or_name: str,
    type_filter: CatalogItemType | str | None,
) -> list[CatalogRecord]:
    type_filter_string = (
        type_filter.value
        if isinstance(type_filter, CatalogItemType)
        else (str(type_filter).lower() if type_filter is not None else None)
    )

    item_by_sha = CatalogDb(cwd).get_by_sha(sha_or_name)
    if item_by_sha is not None:
        if type_filter_string is None or item_by_sha.item_type.value == type_filter_string:
            return [item_by_sha]
        return []
    return CatalogDb(cwd).list_by_name(sha_or_name, item_type=type_filter)


def _read_and_parse_yaml(file_path: Path, rel_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    yaml_file = read_yaml_file(file_path)
    if yaml_file.error or yaml_file.parsed is None or not isinstance(yaml_file.parsed, dict):
        error_message = (
            yaml_file.error or f"Failed to load catalog blueprint '{rel_path}': invalid or non-object YAML content."
        )
        return None, [error_message]
    return yaml_file.parsed, []


def _validate_definition[T](
    winner: CatalogRecord,
    definition_cls: type[T],
    cwd: Path | None,
    sha_or_name: str,
) -> tuple[Any | None, DefinitionResolutionStatus, list[str]]:
    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / winner.path
    parsed_data, errors = _read_and_parse_yaml(file_path, winner.path)
    if errors:
        return None, DefinitionResolutionStatus.LOAD_ERROR, errors

    schema_validator = getattr(definition_cls, "schema_validator", None)
    if schema_validator is not None and hasattr(schema_validator, "validate"):
        validation_result = schema_validator.validate(parsed_data)
        if hasattr(validation_result, "ok") and not validation_result.ok:
            validation_errors = list(getattr(validation_result, "errors", [str(validation_result)]))
            return None, DefinitionResolutionStatus.LOAD_ERROR, validation_errors

    try:
        if hasattr(definition_cls, "model_validate"):
            definition = definition_cls.model_validate(parsed_data)
        else:
            definition = definition_cls(**parsed_data)  # type: ignore[call-arg]
        return definition, DefinitionResolutionStatus.OK, []
    except (Exception, DefinitionLoadError, DefinitionValidationError) as exc:
        return None, DefinitionResolutionStatus.LOAD_ERROR, [f"Model validation failed for '{sha_or_name}': {exc}"]


def get_catalog_item[T](
    sha_or_name: str,
    type_filter: CatalogItemType | str | None = None,
    *,
    definition_cls: type[T] | None = None,
    cwd: Path | None = None,
) -> DefinitionResolutionResult[CatalogRecord]:
    """Retrieve catalog blueprint record by SHA or name, optionally validating its content into ``definition_cls``."""
    scan_and_index_catalog(cwd)
    matches = _find_catalog_matches(cwd, sha_or_name, type_filter)

    if not matches:
        return DefinitionResolutionResult(
            status=DefinitionResolutionStatus.NOT_FOUND,
            requested_name=sha_or_name,
            resolved=None,
            matches=[],
            errors=[f"Catalog blueprint '{sha_or_name}' not found."],
        )

    winner = matches[0]
    warnings: list[str] = []
    if len(matches) > 1:
        other_matching_paths = ", ".join(m.path.as_posix() for m in matches if m.path != winner.path)
        warnings.append(
            f"Duplicate catalog name '{sha_or_name}'; using '{winner.path.as_posix()}' (also found in: {other_matching_paths})."
        )

    definition: Any | None = None
    errors: list[str] = []
    status = DefinitionResolutionStatus.OK

    if definition_cls is not None:
        definition, status, errors = _validate_definition(winner, definition_cls, cwd, sha_or_name)

    return DefinitionResolutionResult(
        status=status,
        requested_name=sha_or_name,
        resolved=winner,
        definition=definition,
        matches=matches,
        errors=errors,
        warnings=warnings,
    )


def delete_catalog_item_by_sha_or_name(
    sha_or_name: str,
    cwd: Path | None = None,
) -> CatalogRecord | None:
    """Delete a catalog blueprint file and its database record."""
    result = get_catalog_item(sha_or_name, cwd=cwd)
    item = result.resolved
    if item is None:
        return None

    catalog_dir = get_catalog_dir(cwd)
    file_path = catalog_dir / item.path
    delete_file(file_path)

    CatalogDb(cwd).delete(item.sha)
    return item
