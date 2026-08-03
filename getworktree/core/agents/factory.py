"""Factory for selecting an agent adapter by provider name."""

from __future__ import annotations

from getworktree.core.agents.base import AgentAdapter
from getworktree.core.agents.copilot import CopilotAgentAdapter
from getworktree.core.agents.cursor import CursorAgentAdapter
from getworktree.core.agents.gemini import GeminiAgentAdapter
from getworktree.core.agents.local import LocalAgentAdapter
from getworktree.core.agents.ollama import OllamaAgentAdapter
from getworktree.core.config.models import AgentConfig

_SUPPORTED_V1 = ("local", "ollama", "cursor", "gemini", "copilot")


def get_agent_adapter(
    provider: str, *, config: AgentConfig | None = None
) -> AgentAdapter:
    """Return an adapter for ``provider``.

    Args:
        provider: Provider id from loop/config (v1: ``local``, ``ollama``,
            ``cursor``, ``gemini``, ``copilot``).
        config: Optional agent config; unused by current adapters (request
            fields are populated by the runner from config).

    Returns:
        An ``AgentAdapter`` implementation.

    Raises:
        ValueError: When ``provider`` is not supported in v1.
    """
    _ = config  # reserved; request carries resolved model/endpoint fields
    if provider == "local":
        return LocalAgentAdapter()
    if provider == "ollama":
        return OllamaAgentAdapter()
    if provider == "cursor":
        return CursorAgentAdapter()
    if provider == "gemini":
        return GeminiAgentAdapter()
    if provider == "copilot":
        return CopilotAgentAdapter()
    supported = ", ".join(_SUPPORTED_V1)
    raise ValueError(
        f"Unsupported agent provider '{provider}' "
        f"(AGENT_PROVIDER_UNSUPPORTED). "
        f"Supported v1 providers: {supported}."
    )
