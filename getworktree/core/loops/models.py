"""Pydantic models for full loop definition V1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LoopAgentMode = Literal["fix_failure", "review_remediation"]
LoopAgentProvider = Literal["local", "ollama"]
LoopContextInclude = Literal["trigger_output", "changed_files", "relevant_source"]
LoopPatchStrategy = Literal["unified_diff"]
LoopStopWhen = Literal["trigger_passes", "unfixable", "user_abort"]


class LoopTrigger(BaseModel):
    """Trigger command settings for a loop definition."""

    model_config = {"extra": "forbid", "strict": True}

    command: str = Field(min_length=1)
    args: list[str]
    timeout_seconds: int = Field(ge=1)


class LoopAgent(BaseModel):
    """Agent provider settings for a loop definition."""

    model_config = {"extra": "forbid", "strict": True}

    provider: LoopAgentProvider
    mode: LoopAgentMode
    timeout_seconds: int = Field(ge=1)


class LoopIteration(BaseModel):
    """Iteration limits and stop conditions."""

    model_config = {"extra": "forbid", "strict": True}

    max_attempts: int = Field(ge=1)
    stop_when: list[LoopStopWhen] = Field(min_length=1)


class LoopSandbox(BaseModel):
    """Sandbox lifecycle settings for one loop."""

    model_config = {"extra": "forbid", "strict": True}

    auto_clean: bool
    keep_on_failure: bool


class LoopApproval(BaseModel):
    """Approval gate before applying loop patches."""

    model_config = {"extra": "forbid", "strict": True}

    require_before_apply: bool


class LoopContext(BaseModel):
    """Context payloads included for the agent."""

    model_config = {"extra": "forbid", "strict": True}

    include: list[LoopContextInclude] = Field(min_length=1)


class LoopPatch(BaseModel):
    """Patch strategy and size limits."""

    model_config = {"extra": "forbid", "strict": True}

    strategy: LoopPatchStrategy
    max_files: int = Field(ge=1)
    max_patch_kb: int = Field(ge=1)
    reject_binary_changes: bool | None = None


class LoopDefinition(BaseModel):
    """Full loop definition V1 surface from ``loop_v1.json``."""

    model_config = {"extra": "forbid", "strict": True}

    version: Literal[1]
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    trigger: LoopTrigger
    agent: LoopAgent
    iteration: LoopIteration
    sandbox: LoopSandbox
    approval: LoopApproval
    context: LoopContext
    patch: LoopPatch
