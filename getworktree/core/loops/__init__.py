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
from getworktree.core.loops.patch import (
    PatchApplyResult,
    PatchApplyStatus,
    apply_patch_result,
)
from getworktree.core.loops.payload import (
    AgentFailurePayload,
    PayloadFile,
    PayloadOmission,
    build_failure_payload,
)
from getworktree.core.loops.render import (
    format_loop_show_resolve_failure,
    format_loop_show_success,
    format_loop_show_validate_failure,
)
from getworktree.core.loops.resolve import (
    LoopResolveResult,
    LoopResolveStatus,
    resolve_loop_by_name,
)
from getworktree.core.loops.runner import (
    AttemptRecord,
    LoopFinalStatus,
    LoopRunResult,
    default_list_changed_files,
    resolve_max_attempts,
    run_loop_iteration,
)
from getworktree.core.loops.safety import (
    NO_OP_STREAK_THRESHOLD,
    REPEAT_FAILURE_THRESHOLD,
    SafetyState,
    failure_signature,
    record_agent_status,
    record_trigger_failure,
    record_trigger_success,
    safety_stop_message,
    session_timed_out,
)
from getworktree.core.loops.seeder import LoopSeedResult, seed_starter_loops
from getworktree.core.loops.trigger import (
    TriggerRunResult,
    TriggerRunStatus,
    run_trigger,
)
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
    "NO_OP_STREAK_THRESHOLD",
    "REPEAT_FAILURE_THRESHOLD",
    "AgentFailurePayload",
    "AttemptRecord",
    "LoopAgent",
    "LoopApproval",
    "LoopContext",
    "LoopDefinition",
    "LoopDiscoveryResult",
    "LoopDiscoveryStatus",
    "LoopFinalStatus",
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
    "LoopRunResult",
    "LoopSandbox",
    "LoopSeedResult",
    "LoopTrigger",
    "LoopValidationResult",
    "LoopValidationStatus",
    "PatchApplyResult",
    "PatchApplyStatus",
    "PayloadFile",
    "PayloadOmission",
    "SafetyState",
    "TriggerRunResult",
    "TriggerRunStatus",
    "apply_patch_result",
    "build_failure_payload",
    "build_loop_inventory",
    "default_list_changed_files",
    "discover_loop_files",
    "failure_signature",
    "format_loop_show_resolve_failure",
    "format_loop_show_success",
    "format_loop_show_validate_failure",
    "load_loop_definition",
    "parse_loop_metadata",
    "record_agent_status",
    "record_trigger_failure",
    "record_trigger_success",
    "resolve_loop_by_name",
    "resolve_loops_dir",
    "resolve_max_attempts",
    "run_loop_iteration",
    "run_trigger",
    "safety_stop_message",
    "seed_starter_loops",
    "session_timed_out",
    "validate_loop_document",
    "validate_loop_result",
]
