from abc import ABC, abstractmethod
from typing import Any, ClassVar


class ComponentFormatter[T](ABC):
    """Interface for formatting a specific type of domain data."""

    _STYLE_MAP: ClassVar[dict[str, str]] = {
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "info": "cyan",
        "default": "default",
    }

    def to_raw(self, data: T) -> str:
        """Render as raw text.

        Args:
            data: Domain data object to render to terminal output.

        Returns:
            A raw text string.
        """
        raise NotImplementedError

    @abstractmethod
    def to_rich(self, data: T) -> Any:
        """Render to a Rich renderable (Text, Table, Panel, etc.).

        Args:
            data: Domain data object to format for terminal output.

        Returns:
            A Rich renderable object.
        """
        raise NotImplementedError

    @abstractmethod
    def to_json_serializable(self, data: T) -> Any:
        """Convert to a primitive Python structure safe for json.dumps.

        Args:
            data: Domain data object to convert for JSON serialization.

        Returns:
            A primitive Python structure.
        """
        raise NotImplementedError
