"""Loop-related core modules."""

from getworktree.core.loops.discovery import (
    DEFAULT_LOOPS_DIR,
    LOOP_FILE_SUFFIXES,
    LoopDiscoveryResult,
    LoopDiscoveryStatus,
    discover_loop_files,
    resolve_loops_dir,
)
from getworktree.core.loops.inventory import (
    LoopInventoryInvalidEntry,
    LoopInventoryResult,
    LoopInventoryStatus,
    LoopInventoryValidEntry,
    build_loop_inventory,
)
from getworktree.core.loops.metadata import (
    LOOP_NAME_PATTERN,
    LoopListMetadata,
    LoopMetadataParseResult,
    LoopMetadataStatus,
    parse_loop_metadata,
)
from getworktree.core.loops.models import (
    LoopAgent,
    LoopApproval,
    LoopContext,
    LoopDefinition,
    LoopIteration,
    LoopPatch,
    LoopSandbox,
    LoopTrigger,
)
from getworktree.core.loops.resolve import (
    LoopResolveResult,
    LoopResolveStatus,
    resolve_loop_by_name,
)
from getworktree.core.loops.seeder import LoopSeedResult, seed_starter_loops
from getworktree.core.loops.validate import (
    LOOP_VALIDATOR,
    LoopValidationResult,
    LoopValidationStatus,
    load_loop_definition,
    validate_loop_document,
    validate_loop_result,
)

__all__ = [
    "DEFAULT_LOOPS_DIR",
    "LOOP_FILE_SUFFIXES",
    "LOOP_NAME_PATTERN",
    "LOOP_VALIDATOR",
    "LoopAgent",
    "LoopApproval",
    "LoopContext",
    "LoopDefinition",
    "LoopDiscoveryResult",
    "LoopDiscoveryStatus",
    "LoopInventoryInvalidEntry",
    "LoopInventoryResult",
    "LoopInventoryStatus",
    "LoopInventoryValidEntry",
    "LoopIteration",
    "LoopListMetadata",
    "LoopMetadataParseResult",
    "LoopMetadataStatus",
    "LoopPatch",
    "LoopResolveResult",
    "LoopResolveStatus",
    "LoopSandbox",
    "LoopSeedResult",
    "LoopTrigger",
    "LoopValidationResult",
    "LoopValidationStatus",
    "build_loop_inventory",
    "discover_loop_files",
    "load_loop_definition",
    "parse_loop_metadata",
    "resolve_loop_by_name",
    "resolve_loops_dir",
    "seed_starter_loops",
    "validate_loop_document",
    "validate_loop_result",
]
