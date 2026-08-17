"""Agent adapter interfaces and provider implementations."""

from worktree.core.agents.base import (
    AgentAdapter,
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from worktree.core.agents.cli_mutation import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_PATCH_KB,
    DEFAULT_REJECT_BINARY_CHANGES,
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from worktree.core.agents.copilot import CopilotAgentAdapter
from worktree.core.agents.cursor import CursorAgentAdapter
from worktree.core.agents.factory import get_agent_adapter
from worktree.core.agents.gemini import GeminiAgentAdapter
from worktree.core.agents.local import LocalAgentAdapter, LocalAgentStdout
from worktree.core.agents.models import (
    AgentFailurePayload,
    PayloadFile,
    PayloadOmission,
)
from worktree.core.agents.ollama import OllamaAgentAdapter

__all__ = [
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_PATCH_KB",
    "DEFAULT_REJECT_BINARY_CHANGES",
    "AgentAdapter",
    "AgentFailurePayload",
    "AgentRequest",
    "AgentResponse",
    "AgentResponseStatus",
    "CliDirectMutationAdapter",
    "CliMutationOutcome",
    "CliMutationRunFn",
    "CliMutationRunRequest",
    "CopilotAgentAdapter",
    "CursorAgentAdapter",
    "GeminiAgentAdapter",
    "LocalAgentAdapter",
    "LocalAgentStdout",
    "OllamaAgentAdapter",
    "PayloadFile",
    "PayloadOmission",
    "build_mutation_prompt",
    "get_agent_adapter",
]
