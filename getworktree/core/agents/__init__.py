"""Agent adapter interfaces and provider implementations."""

from getworktree.core.agents.base import (
    AgentAdapter,
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.agents.cli_mutation import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_PATCH_KB,
    DEFAULT_REJECT_BINARY_CHANGES,
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from getworktree.core.agents.copilot import CopilotAgentAdapter
from getworktree.core.agents.cursor import CursorAgentAdapter
from getworktree.core.agents.factory import get_agent_adapter
from getworktree.core.agents.gemini import GeminiAgentAdapter
from getworktree.core.agents.local import LocalAgentAdapter, LocalAgentStdout
from getworktree.core.agents.ollama import OllamaAgentAdapter

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
