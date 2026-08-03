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
from getworktree.core.loops.seeder import LoopSeedResult, seed_starter_loops

__all__ = [
    "DEFAULT_LOOPS_DIR",
    "LOOP_FILE_SUFFIXES",
    "LOOP_NAME_PATTERN",
    "LoopDiscoveryResult",
    "LoopDiscoveryStatus",
    "LoopInventoryInvalidEntry",
    "LoopInventoryResult",
    "LoopInventoryStatus",
    "LoopInventoryValidEntry",
    "LoopListMetadata",
    "LoopMetadataParseResult",
    "LoopMetadataStatus",
    "LoopSeedResult",
    "build_loop_inventory",
    "discover_loop_files",
    "parse_loop_metadata",
    "resolve_loops_dir",
    "seed_starter_loops",
]
