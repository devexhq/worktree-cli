"""Pydantic models for full workflow definition V1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowAgentMode = Literal["fix_failure", "review_remediation"]
WorkflowAgentProvider = Literal["local", "ollama", "cursor", "gemini", "copilot"]
WorkflowContextInclude = Literal["trigger_output", "changed_files", "relevant_source"]
WorkflowPatchStrategy = Literal["unified_diff"]
WorkflowStopWhen = Literal["trigger_passes", "unfixable", "user_abort"]


class WorkflowTrigger(BaseModel):
    """Trigger command settings for a workflow definition."""

    model_config = {"extra": "forbid", "strict": True}

    command: str = Field(min_length=1)
    args: list[str]
    timeout_seconds: int = Field(ge=1)


class WorkflowAgent(BaseModel):
    """Agent provider settings for a workflow definition."""

    model_config = {"extra": "forbid", "strict": True}

    provider: WorkflowAgentProvider
    mode: WorkflowAgentMode
    timeout_seconds: int = Field(ge=1)


class WorkflowIteration(BaseModel):
    """Iteration limits and stop conditions."""

    model_config = {"extra": "forbid", "strict": True}

    max_attempts: int = Field(ge=1)
    stop_when: list[WorkflowStopWhen] = Field(min_length=1)


class WorkflowSandbox(BaseModel):
    """Sandbox lifecycle settings for one workflow."""

    model_config = {"extra": "forbid", "strict": True}

    auto_clean: bool
    keep_on_failure: bool


class WorkflowApproval(BaseModel):
    """Approval gate before applying workflow patches."""

    model_config = {"extra": "forbid", "strict": True}

    require_before_apply: bool


class WorkflowContext(BaseModel):
    """Context payloads included for the agent."""

    model_config = {"extra": "forbid", "strict": True}

    include: list[WorkflowContextInclude] = Field(min_length=1)


class WorkflowPatch(BaseModel):
    """Patch strategy and size limits."""

    model_config = {"extra": "forbid", "strict": True}

    strategy: WorkflowPatchStrategy
    max_files: int = Field(ge=1)
    max_patch_kb: int = Field(ge=1)
    reject_binary_changes: bool | None = None


class WorkflowDefinition(BaseModel):
    """Full workflow definition V1 surface from ``workflow_v1.json``."""

    model_config = {"extra": "forbid", "strict": True}

    version: Literal[1]
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    trigger: WorkflowTrigger
    agent: WorkflowAgent
    iteration: WorkflowIteration
    sandbox: WorkflowSandbox
    approval: WorkflowApproval
    context: WorkflowContext
    patch: WorkflowPatch
