from worktree.common.models import DefinitionResolutionResult
from worktree.core.db import CatalogRecord

_CATALOG_RECORD_DYNAMIC_FIELDS = {"created_at", "updated_at", "checksum", "sha", "path"}

EXCLUSION_REGISTRY: dict[str, set[str] | dict[str, object]] = {
    CatalogRecord.__name__: _CATALOG_RECORD_DYNAMIC_FIELDS,
    # DefinitionResolutionResult[CatalogRecord] uses TypeVars for `resolved` and
    # `matches`, so build_exclude_mask cannot introspect through them automatically.
    # Register the concrete parameterization explicitly with per-field nested masks.
    DefinitionResolutionResult[CatalogRecord].__name__: {
        "resolved": _CATALOG_RECORD_DYNAMIC_FIELDS,
        "matches": {"__all__": _CATALOG_RECORD_DYNAMIC_FIELDS},
    },
}
