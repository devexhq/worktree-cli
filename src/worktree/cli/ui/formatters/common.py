"""Common formatting utilities and styles across formatters."""

from __future__ import annotations

from typing import Any, Protocol, overload

DEFAULT_PANEL_STYLE = "blue"
ERROR_PANEL_STYLE = "red"
WARNING_STYLE = "yellow"
SUCCESS_STYLE = "green"


class DispatcherProtocol(Protocol):
    """Protocol for dispatcher registration entrypoint."""

    @overload
    def register(
        self,
        model_cls: type[Any],
        formatter: Any,
    ) -> Any: ...

    @overload
    def register(
        self,
        model_cls: type[Any],
        formatter: None = None,
    ) -> Any: ...

    def register(
        self,
        model_cls: type[Any],
        formatter: Any = None,
    ) -> Any:
        """Register a formatter for a specific result or event type."""
        ...
