"""Agent adapter interfaces and provider implementations."""

from getworktree.core.agents.base import (
    AgentAdapter,
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.agents.factory import get_agent_adapter
from getworktree.core.agents.local import LocalAgentAdapter, LocalAgentStdout

__all__ = [
    "AgentAdapter",
    "AgentRequest",
    "AgentResponse",
    "AgentResponseStatus",
    "LocalAgentAdapter",
    "LocalAgentStdout",
    "get_agent_adapter",
]
