from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

type AssertModel = Callable[[BaseModel, dict[str, Any]], None]
