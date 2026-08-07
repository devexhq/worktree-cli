from typing import ClassVar
from pathlib import Path
from typing import Any
from pydantic import BaseModel


class ErrorRenderMixin:
    # Global fallback if a child model doesn't define its own
    DEFAULT_ERROR_STRING: ClassVar[str] = "No errors found"

    def render_errors(self) -> str:
        """Dynamically retrieves the default string from the child model's class scope."""
        # Look up the attribute on the runtime class itself
        default_string = getattr(type(self), "DEFAULT_ERROR_STRING", self.DEFAULT_ERROR_STRING)

        errors = getattr(self, "errors", [])
        if not errors:
            return default_string

        return "\n".join(errors)
