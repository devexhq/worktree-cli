from pathlib import Path
from typing import Any

from pydantic import BaseModel


class YamlFile(BaseModel):
    """Representation of a yaml file from a directory scan."""

    path: Path
    name: str
    content: str | None = ""
    parsed: Any | None = None
    error: str | None = None
