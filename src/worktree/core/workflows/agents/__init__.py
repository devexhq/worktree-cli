"""Agent adapter interfaces and provider implementations."""

from worktree.core.workflows.agents.base import (
    AgentAdapter,
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from worktree.core.workflows.agents.cli_mutation import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_PATCH_KB,
    DEFAULT_REJECT_BINARY_CHANGES,
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from worktree.core.workflows.agents.copilot import CopilotAgentAdapter
from worktree.core.workflows.agents.cursor import CursorAgentAdapter
from worktree.core.workflows.agents.factory import get_agent_adapter
from worktree.core.workflows.agents.gemini import GeminiAgentAdapter
from worktree.core.workflows.agents.local import LocalAgentAdapter, LocalAgentStdout
from worktree.core.workflows.agents.ollama import OllamaAgentAdapter

__all__ = [
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_PATCH_KB",
    "DEFAULT_REJECT_BINARY_CHANGES",
    "AgentAdapter",
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
    "build_mutation_prompt",
    "get_agent_adapter",
]
