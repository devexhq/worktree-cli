"""Factory for selecting an agent adapter by provider name."""

from __future__ import annotations

from getworktree.core.agents.base import AgentAdapter
from getworktree.core.agents.local import LocalAgentAdapter
from getworktree.core.agents.ollama import OllamaAgentAdapter
from getworktree.core.config.models import AgentConfig

_SUPPORTED_V1 = ("local", "ollama")


def get_agent_adapter(
    provider: str, *, config: AgentConfig | None = None
) -> AgentAdapter:
    """Return an adapter for ``provider``.

    Args:
        provider: Provider id from loop/config (v1: ``local``, ``ollama``).
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
    supported = ", ".join(_SUPPORTED_V1)
    raise ValueError(
        f"Unsupported agent provider '{provider}' "
        f"(AGENT_PROVIDER_UNSUPPORTED). "
        f"Supported v1 providers: {supported}."
    )
