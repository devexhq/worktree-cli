"""Agent adapter interfaces and provider implementations."""

from getworktree.core.loops.agents.base import (
    AgentAdapter,
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.loops.agents.cli_mutation import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_PATCH_KB,
    DEFAULT_REJECT_BINARY_CHANGES,
    CliDirectMutationAdapter,
    CliMutationOutcome,
    CliMutationRunFn,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from getworktree.core.loops.agents.copilot import CopilotAgentAdapter
from getworktree.core.loops.agents.cursor import CursorAgentAdapter
from getworktree.core.loops.agents.factory import get_agent_adapter
from getworktree.core.loops.agents.gemini import GeminiAgentAdapter
from getworktree.core.loops.agents.local import LocalAgentAdapter, LocalAgentStdout
from getworktree.core.loops.agents.ollama import OllamaAgentAdapter

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
