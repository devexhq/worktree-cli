"""Tier 4 architectural invariants enforcing Pydantic model configurations."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Final, TypeIs

import pytest
from pydantic import BaseModel
from sqlmodel import SQLModel

SRC_ROOT: Final[Path] = Path(__file__).parent.parent.parent / "src" / "worktree"

# Whitelisted models with justified exceptions (e.g. forward-compatible YAML or LLM output)
WHITELISTED_MODELS: Final[frozenset[str]] = frozenset(
    {
        "BlueprintDefinition",
        "BlueprintDefaults",
        "LoopStepBlock",
        "OllamaModelStdout",
        "FilesystemPaths",
    }
)

pytestmark = pytest.mark.invariant


def _is_target_model_class(obj: type, module_name: str) -> TypeIs[type[BaseModel]]:
    """Check if class is a project Pydantic model defined in module."""
    if not issubclass(obj, BaseModel):
        return False
    if issubclass(obj, SQLModel):
        return False
    return obj.__module__ == module_name


def _check_model_strictness(name: str, obj: type[BaseModel], module_name: str) -> str | None:
    """Check if model specifies extra='forbid' and strict=True."""
    if name in WHITELISTED_MODELS:
        return None
    cfg = getattr(obj, "model_config", {})
    extra = cfg.get("extra")
    strict = cfg.get("strict")
    if extra != "forbid" or strict is not True:
        return f"{module_name}.{name}: extra={extra!r}, strict={strict!r}"
    return None


def _inspect_module_models(file_path: Path) -> list[str]:
    """Inspect model classes in a module for strict config compliance."""
    parts = file_path.with_suffix("").parts
    src_idx = parts.index("worktree")
    module_name = ".".join(parts[src_idx:])

    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        return [f"Could not import {module_name}: {exc}"]

    violations: list[str] = []
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if _is_target_model_class(obj, module_name):
            err = _check_model_strictness(name, obj, module_name)
            if err:
                violations.append(err)
    return violations


def test_all_pydantic_models_have_strict_config() -> None:
    """Ensure all Result, Outcome, and DTO Pydantic models specify strict configuration."""
    model_files = [
        p
        for p in SRC_ROOT.rglob("*.py")
        if ("models.py" in p.name or p.name.endswith("_models.py")) and "core/db" not in str(p)
    ]

    violations: list[str] = []
    for file_path in model_files:
        violations.extend(_inspect_module_models(file_path))

    assert not violations, (
        "Found Pydantic models missing strict model_config (extra='forbid', strict=True):\n" + "\n".join(violations)
    )
