"""Catalog domain facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yaml

from worktree.common.exceptions import DefinitionLoadError, DefinitionValidationError
from worktree.common.filesystem import Filesystem
from worktree.common.lock import WorkspaceLock
from worktree.common.models import DefinitionResolutionResult, DefinitionResolutionStatus
from worktree.core.catalog.exceptions import (
    CatalogFileNotFoundError,
    CatalogWriteError,
    CatalogYamlError,
)
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogResolveResult,
    CatalogResolveStatus,
    CatalogScanResult,
    CatalogShowResult,
    CatalogValidateResult,
    CatalogValidateStatus,
    DefinitionValidationOutcome,
    YamlParseOutcome,
)
from worktree.core.catalog.services.inventory import (
    create_catalog_item,
    delete_catalog_item_by_sha_or_name,
    ensure_catalog_dirs,
    find_packaged_templates,
    get_catalog_dir,
    list_packaged_template_defaults,
    scan_and_index_catalog,
)
from worktree.core.catalog.services.seeder import (
    SeedResult,
    seed_all_catalog_templates,
)
from worktree.core.catalog.services.validate import validate_catalog_item
from worktree.core.db import (
    CatalogItemType,
    CatalogRecord,
    CatalogRepository,
)


class _PydanticModel(Protocol):
    """Minimal protocol for catalog definition classes validated via Pydantic."""

    @classmethod
    def model_validate(cls, obj: Any) -> Any:
        """Validate and parse raw data into a model instance."""
        ...


class Catalog:
    """Unified entrypoint for blueprint catalog inventory and management."""

    def __init__(self, path: Path = Path("."), db: CatalogRepository | None = None) -> None:
        self.path = path.resolve()
        self.cwd = self.path
        self.db = db if db is not None else CatalogRepository(self.path)

    @property
    def root_dir(self):
        """Return the root catalogs direcotry path."""
        return Filesystem(self.path).catalog_dir

    def list(
        self,
        kind: CatalogItemType | str | None = None,
        *,
        type_filter: CatalogItemType | str | None = None,
    ) -> CatalogListResult:
        """Return indexed catalog records, optionally filtered by item type."""
        filter_value = type_filter if type_filter is not None else kind
        if filter_value is not None and str(filter_value).lower() == "template":
            return CatalogListResult(templates=self.list_packaged_templates(), type_filter="template")

        parsed_type, error = self._parse_filter_type(filter_value)
        if error is not None:
            return CatalogListResult(errors=[error])

        scan_result = self.sync()
        items = self.db.list() if parsed_type is None else self.db.list(item_type=parsed_type)
        return CatalogListResult(
            items=items,
            type_filter=parsed_type,
            warnings=list(scan_result.errors),
        )

    def _parse_filter_type(
        self, filter_value: CatalogItemType | str | None
    ) -> tuple[CatalogItemType | None, str | None]:
        """Parse optional type filter, returning (item_type, error_message)."""
        if filter_value is None:
            return None, None
        try:
            return self._coerce_item_type(filter_value), None
        except ValueError:
            allowed = ", ".join(t.value for t in CatalogItemType)
            return None, f"Invalid --type argument '{filter_value}'. Allowed choices: {allowed}"

    def show(self, sha_or_name: str) -> CatalogShowResult:
        """Show details and definition content of a catalog blueprint or template."""
        resolution_result = self.get(sha_or_name)
        item = resolution_result.resolved
        if not resolution_result.ok or item is None:
            found = self.find_packaged_templates(sha_or_name)
            if found:
                return CatalogShowResult(template_matches=found, content=found[0][1] if found else None)

            return CatalogShowResult(errors=[f"Catalog blueprint or template '{sha_or_name}' not found."])

        catalog_dir = get_catalog_dir(self.path)
        file_path = catalog_dir / item.path

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            return CatalogShowResult(
                item=item,
                errors=[f"Failed to read file for catalog blueprint '{sha_or_name}': {exc}"],
            )

        return CatalogShowResult(item=item, content=content)

    def resolve(self, name: str, item_type: CatalogItemType) -> CatalogResolveResult:
        """Reindex, find typed matches, and load the winning YAML object."""
        self.sync()
        non_namespaced_name, namespace = self._split_name_and_namespace(name)
        matches = self._find_typed_matches(non_namespaced_name, [item_type], namespace=namespace)
        if not matches:
            return CatalogResolveResult(
                status=CatalogResolveStatus.NOT_FOUND,
                name=name,
                errors=[f"Catalog blueprint '{name}' not found."],
            )
        winner = matches[0]
        warnings = [self._duplicate_name_warning(name, winner, matches)] if len(matches) > 1 else []
        raw, parse_errors = self._parse_catalog_yaml(get_catalog_dir(self.path) / winner.path, winner.path)
        if parse_errors or raw is None:
            return CatalogResolveResult(
                status=CatalogResolveStatus.LOAD_ERROR,
                name=name,
                record=winner,
                matches=matches,
                errors=parse_errors,
                warnings=warnings,
            )
        return CatalogResolveResult(
            status=CatalogResolveStatus.OK,
            name=name,
            raw=raw,
            record=winner,
            matches=matches,
            warnings=warnings,
        )

    def _split_name_and_namespace(self, name: str) -> tuple[str, str | None]:
        """Split a potentially namespaced blueprint identifier into name and namespace."""
        if "/" not in name:
            return name, None
        namespace_parts = name.split("/")
        namespace = "/".join(namespace_parts[:-1])
        non_namespaced_name = namespace_parts[-1]
        return non_namespaced_name, namespace

    def get[T](
        self,
        sha_or_name: str,
        item_type: CatalogItemType | str | None = None,
        definition_cls: type[_PydanticModel] | None = None,
    ) -> DefinitionResolutionResult[CatalogRecord]:
        """Retrieve catalog blueprint record by SHA or name, optionally validating its content into ``definition_cls``."""
        self.sync()
        non_namespaced_name, namespace = self._split_name_and_namespace(sha_or_name)
        matches = self.db.find_catalog_matches(non_namespaced_name, item_type, namespace=namespace)

        if not matches:
            return DefinitionResolutionResult[CatalogRecord](
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
            validation_outcome = self._validate_definition(winner, definition_cls, sha_or_name)
            definition = validation_outcome.definition
            status = validation_outcome.status
            errors = validation_outcome.errors

        return DefinitionResolutionResult[CatalogRecord](
            status=status,
            requested_name=sha_or_name,
            resolved=winner,
            definition=definition,
            matches=matches,
            errors=errors,
            warnings=warnings,
        )

    def get_by_key[T](
        self,
        key: str,
        item_type: CatalogItemType,
        definition_cls: type[_PydanticModel] | None = None,
    ) -> DefinitionResolutionResult[CatalogRecord]:
        """Retrieve an indexed catalog record by its globally unique key.

        Unlike ``get``/``resolve``, this performs no SHA or ambiguous-name
        matching: ``key`` must equal exactly one indexed record's ``key``.
        """
        self.sync()
        record = self.db.get_by_key(key)
        if record is None or record.item_type != item_type:
            return DefinitionResolutionResult[CatalogRecord](
                status=DefinitionResolutionStatus.NOT_FOUND,
                requested_name=key,
                resolved=None,
                matches=[],
                errors=[f"Catalog {item_type.value} '{key}' not found."],
            )

        definition: Any | None = None
        errors: list[str] = []
        status = DefinitionResolutionStatus.OK
        if definition_cls is not None:
            validation_outcome = self._validate_definition(record, definition_cls, key)
            definition = validation_outcome.definition
            status = validation_outcome.status
            errors = validation_outcome.errors

        return DefinitionResolutionResult[CatalogRecord](
            status=status,
            requested_name=key,
            resolved=record,
            definition=definition,
            matches=[record],
            errors=errors,
        )

    def create(
        self,
        item_type: CatalogItemType | str,
        name: str,
    ) -> CatalogCreateResult:
        """Create a new catalog blueprint file and reindex."""
        try:
            record = create_catalog_item(
                item_type=self._coerce_item_type(item_type),
                name=name,
                path=self.path,
                db=self.db,
            )
            return CatalogCreateResult(item=record)
        except Exception as exc:
            return CatalogCreateResult(errors=[str(exc)])

    def delete(self, sha_or_name: str) -> CatalogDeleteResult:
        """Delete catalog blueprint file and its database index record."""
        try:
            deleted_item = delete_catalog_item_by_sha_or_name(sha_or_name, path=self.path, db=self.db)
            if deleted_item is None:
                return CatalogDeleteResult(errors=[f"Catalog blueprint '{sha_or_name}' not found."])
            return CatalogDeleteResult(item=deleted_item, deleted=True)
        except Exception as exc:
            return CatalogDeleteResult(errors=[str(exc)])

    def save(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        item_type: CatalogItemType | str,
    ) -> CatalogRecord:
        """Write YAML under the type folder and reindex. Overwrites an existing file."""
        with WorkspaceLock(self.path):
            type_enum = self._coerce_item_type(item_type)
            catalog_dir = ensure_catalog_dirs(self.path)
            stem = self._strip_yaml_suffix(name)
            rel_path = Path(f"{type_enum.value}s") / f"{stem}.yml"
            target_path = catalog_dir / rel_path
            text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False)

            if not text.endswith("\n"):
                text += "\n"
            try:
                Filesystem.atomic_write_text(target_path, text)
            except OSError as exc:
                raise CatalogWriteError(f"Failed to write catalog blueprint '{target_path}': {exc}") from exc

            self.sync()

            record = self._record_for_rel_path(rel_path)
            if record is None:
                raise CatalogWriteError(f"Failed to reindex catalog blueprint '{rel_path.as_posix()}'.")

            return record

    def seed(self, *, force: bool = False) -> SeedResult:
        """Seed packaged catalog templates into the workspace."""
        return seed_all_catalog_templates(self.path, force=force)

    def sync(self) -> CatalogScanResult:
        """Synchronize database index with on-disk YAML blueprints.

        Called automatically by every name/SHA-resolving method (``list``, ``resolve``, ``get``,
        ``get_by_key``, ``save``, and ``validate`` for a catalog-name target) so a lookup always sees
        the current contents of ``.worktree/catalog/``, never a stale index. ``validate`` is the one
        exception within itself: a direct file-path target is inspected without calling ``get``/``sync``
        at all, so validating a file never touches the index or acquires the workspace lock.
        """
        return scan_and_index_catalog(self.path, db=self.db)

    def validate(
        self,
        target: str,
        *,
        item_type: CatalogItemType | None = None,
        blueprint_cls: type[_PydanticModel],
        step_cls: type[_PydanticModel],
    ) -> CatalogValidateResult:
        """Validate a catalog blueprint or step definition without executing it.

        A catalog-name target is resolved via ``get()``, which re-syncs the index first, like every
        other name-based lookup on this class (see ``sync()``). A file-path target is inspected
        directly and never touches the index.
        """
        resolution = self._resolve_validate_target(target, item_type=item_type)
        if isinstance(resolution, CatalogValidateResult):
            return resolution
        return validate_catalog_item(
            target,
            repo_root=self.path,
            resolved=resolution,
            blueprint_cls=blueprint_cls,
            step_cls=step_cls,
        )

    def _resolve_validate_target(
        self,
        target: str,
        *,
        item_type: CatalogItemType | None,
    ) -> CatalogValidateResult | tuple[Path, str, str, list[str]]:
        """Resolve target to (absolute_path, item_type_value, definition_key, warnings), or a terminal not-found/type-required result.

        Kept on ``Catalog`` rather than in ``services/validate.py`` so the catalog-name branch can call
        ``self.get()`` directly instead of duplicating its matching and duplicate-name-warning logic;
        ``services/validate.py`` never imports ``Catalog``, which would create an import cycle
        (``catalog.py`` already imports ``services/validate.py`` for the YAML/schema/semantic checks).
        """
        candidate = Path(target)
        file_candidate = candidate if candidate.is_absolute() else self.path / candidate

        if file_candidate.is_file():
            if item_type is None:
                return CatalogValidateResult(
                    status=CatalogValidateStatus.TYPE_REQUIRED,
                    valid=False,
                    target=target,
                    resolved_path=file_candidate,
                    item_type=None,
                    errors=[f"'--type' is required to validate file target '{target}' (CATALOG_TYPE_REQUIRED)."],
                    warnings=[],
                    fixes=["Pass --type blueprint or --type step for a file target."],
                )
            return file_candidate, item_type.value, file_candidate.stem, []

        resolution = self.get(target)
        if resolution.resolved is None:
            return CatalogValidateResult(
                status=CatalogValidateStatus.NOT_FOUND,
                valid=False,
                target=target,
                resolved_path=None,
                item_type=None,
                errors=[f"Catalog item '{target}' not found (CATALOG_ITEM_NOT_FOUND)."],
                warnings=[],
                fixes=[f"Check that '{target}' names an indexed catalog item, or pass a file path instead."],
            )

        record = resolution.resolved
        return self.root_dir / record.path, record.item_type.value, record.key, list(resolution.warnings)

    @staticmethod
    def list_packaged_templates() -> list[tuple[str, str]]:
        """Return (type, relative_path) pairs for the packaged default templates."""
        return list_packaged_template_defaults()

    @staticmethod
    def find_packaged_templates(sha_or_name: str) -> list[tuple[str, str]]:
        """Return (relative_path, content) pairs for packaged templates matching sha_or_name."""
        return find_packaged_templates(sha_or_name)

    @staticmethod
    def read_yaml(path: Path) -> dict[str, Any]:
        """Load a YAML object from path or raise a classified catalog error."""
        if not path.exists():
            raise CatalogFileNotFoundError(f"Catalog file not found at '{path}'.")
        yaml_file = Filesystem.read_yaml_file(path)
        if yaml_file.error or yaml_file.parsed is None or not isinstance(yaml_file.parsed, dict):
            detail = yaml_file.error or "invalid or non-object YAML content."
            raise CatalogYamlError(f"Failed to load catalog blueprint '{path}': {detail}")
        return yaml_file.parsed

    @staticmethod
    def _coerce_item_type(value: CatalogItemType | str) -> CatalogItemType:
        """Parse a catalog item type or raise ValueError with allowed choices."""
        if isinstance(value, CatalogItemType):
            return value
        try:
            return CatalogItemType(str(value).lower())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in CatalogItemType)
            raise ValueError(f"Invalid item_type '{value}'. Allowed choices: {allowed}") from exc

    @staticmethod
    def _strip_yaml_suffix(name: str) -> str:
        """Remove a trailing ``.yml`` / ``.yaml`` suffix when present."""
        if name.endswith(".yaml"):
            return name[:-5]
        if name.endswith(".yml"):
            return name[:-4]
        return name

    def _find_typed_matches(
        self, name: str, allowed_types: list[CatalogItemType], namespace: str | None = None
    ) -> list[CatalogRecord]:
        """Return SHA or name matches restricted to ``allowed_types``, path-ascending."""
        by_sha = self.db.get_by_sha(name)
        if by_sha is not None:
            if by_sha.item_type in allowed_types:
                return [by_sha]
            return []
        matches: list[CatalogRecord] = []
        for item_type in allowed_types:
            matches.extend(self.db.list_by_name(name, item_type=item_type, namespace=namespace))
        return sorted(matches, key=lambda record: record.path.as_posix())

    @staticmethod
    def _duplicate_name_warning(name: str, winner: CatalogRecord, matches: list[CatalogRecord]) -> str:
        """Match ``get_catalog_item`` duplicate-name warning wording."""
        other_matching_paths = ", ".join(match.path.as_posix() for match in matches if match.path != winner.path)
        return f"Duplicate catalog name '{name}'; using '{winner.path.as_posix()}' (also found in: {other_matching_paths})."

    @staticmethod
    def _parse_catalog_yaml(file_path: Path, rel_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
        """Read ``file_path`` as a YAML object, using ``rel_path`` in fallback errors."""
        yaml_file = Filesystem.read_yaml_file(file_path)
        if yaml_file.error or yaml_file.parsed is None or not isinstance(yaml_file.parsed, dict):
            error_message = (
                yaml_file.error or f"Failed to load catalog blueprint '{rel_path}': invalid or non-object YAML content."
            )
            return None, [error_message]
        return yaml_file.parsed, []

    def _record_for_rel_path(self, rel_path: Path) -> CatalogRecord | None:
        """Return the indexed record whose path equals ``rel_path``."""
        return self.db.get_by_path(rel_path)

    def _read_and_parse_yaml(self, file_path: Path, rel_path: Path) -> YamlParseOutcome:
        """Read and parse a catalog YAML file, returning parsed dict or error messages."""
        yaml_file = Filesystem.read_yaml_file(file_path)
        if yaml_file.error or yaml_file.parsed is None or not isinstance(yaml_file.parsed, dict):
            error_message = (
                yaml_file.error or f"Failed to load catalog blueprint '{rel_path}': invalid or non-object YAML content."
            )
            return YamlParseOutcome(parsed_data=None, errors=[error_message])
        return YamlParseOutcome(parsed_data=yaml_file.parsed, errors=[])

    def _validate_definition(
        self,
        winner: CatalogRecord,
        definition_cls: type[_PydanticModel],
        sha_or_name: str,
    ) -> DefinitionValidationOutcome:
        """Validate definition payload against model class, returning resolution outcome."""
        file_path = self.root_dir / winner.path
        parse_outcome = self._read_and_parse_yaml(file_path, winner.path)
        if parse_outcome.errors or parse_outcome.parsed_data is None:
            return DefinitionValidationOutcome(
                definition=None,
                status=DefinitionResolutionStatus.LOAD_ERROR,
                errors=parse_outcome.errors,
            )

        parsed_data = parse_outcome.parsed_data
        schema_validator = getattr(definition_cls, "schema_validator", None)
        if schema_validator is not None and hasattr(schema_validator, "validate"):
            validation_result = schema_validator.validate(parsed_data)
            if hasattr(validation_result, "ok") and not validation_result.ok:
                validation_errors = list(getattr(validation_result, "errors", [str(validation_result)]))
                return DefinitionValidationOutcome(
                    definition=None,
                    status=DefinitionResolutionStatus.LOAD_ERROR,
                    errors=validation_errors,
                )

        try:
            from_document = getattr(definition_cls, "from_document", None)
            if callable(from_document):
                definition = from_document(parsed_data, key=winner.key or sha_or_name)
            else:
                definition = definition_cls.model_validate(parsed_data)
            return DefinitionValidationOutcome(
                definition=definition,
                status=DefinitionResolutionStatus.OK,
                errors=[],
            )
        except (Exception, DefinitionLoadError, DefinitionValidationError) as exc:
            return DefinitionValidationOutcome(
                definition=None,
                status=DefinitionResolutionStatus.LOAD_ERROR,
                errors=[f"Model validation failed for '{sha_or_name}': {exc}"],
            )
