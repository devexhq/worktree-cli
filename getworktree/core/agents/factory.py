"""Factory for selecting an agent adapter by provider name."""

from __future__ import annotations

from getworktree.core.agents.base import AgentAdapter
from getworktree.core.agents.local import LocalAgentAdapter
from getworktree.core.config.models import AgentConfig

_SUPPORTED_V1 = ("local",)


def get_agent_adapter(
    provider: str, *, config: AgentConfig | None = None
) -> AgentAdapter:
    """Return an adapter for ``provider``.

    Args:
        provider: Provider id from loop/config (v1 supports ``local`` only).
        config: Optional agent config; unused for local today, reserved for
            future providers.

    Returns:
        An ``AgentAdapter`` implementation.

    Raises:
        ValueError: When ``provider`` is not supported in v1.
    """
    _ = config  # reserved for future non-local providers
    if provider == "local":
        return LocalAgentAdapter()
    supported = ", ".join(_SUPPORTED_V1)
    raise ValueError(
        f"Unsupported agent provider '{provider}' "
        f"(AGENT_PROVIDER_UNSUPPORTED). "
        f"Supported v1 providers: {supported}."
    )
