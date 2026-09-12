"""Fluent test data builders for Worktree CLI test suite."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from worktree.common.filesystem import Filesystem
from worktree.common.models import FailurePolicy, OnFailureSpec
from worktree.core.blueprint.models import BlueprintDefaults, BlueprintDefinition
from worktree.core.bootstrap.services.bootstrap import bootstrap_worktree
from worktree.core.catalog.services.seeder import seed_all_catalog_templates
from worktree.core.config.generator import generate_default_config
from worktree.core.db.connection import DEFAULT_DB_REL_PATH
from worktree.core.db.migrations import init_database
from worktree.core.inputs.models import InputType, ParameterInput
from worktree.core.step.models import (
    LoopStepBlock,
    StepAssert,
    StepDefinition,
    StepType,
)


def _merge_string_items(
    existing: str | list[str] | None,
    new_value: str | list[str],
) -> str | list[str]:
    """Merge string assertion criteria, concatenating into a list if multiple are provided."""
    if existing is None:
        return new_value
    existing_items = [existing] if isinstance(existing, str) else list(existing)
    new_items = [new_value] if isinstance(new_value, str) else list(new_value)
    return existing_items + new_items


def _merge_int_items(
    existing: int | list[int] | None,
    new_value: int | list[int],
) -> int | list[int]:
    """Merge int assertion criteria, concatenating into a list if multiple are provided."""
    if existing is None:
        return new_value
    existing_items = [existing] if isinstance(existing, int) else list(existing)
    new_items = [new_value] if isinstance(new_value, int) else list(new_value)
    return existing_items + new_items


class StepBuilder:
    """Fluent builder for constructing validated StepDefinition models in tests."""

    def __init__(self, command: str = "echo test") -> None:
        self._id: str = "step-1"
        self._name: str | None = None
        self._description: str | None = None
        self._type: StepType | None = StepType.COMMAND
        self._command: str | None = command
        self._prompt: str | None = None
        self._script_path: str | None = None
        self._run: str | None = None
        self._uses: str | None = None
        self._timeout: int = 30
        self._env: dict[str, str] = {}
        self._assert: StepAssert | None = None
        self._on_failure: OnFailureSpec = OnFailureSpec(action=FailurePolicy.ABORT)

    @classmethod
    def command(cls, cmd: str) -> StepBuilder:
        """Create a StepBuilder initialized for command execution."""
        return cls(command=cmd)

    @classmethod
    def run(cls, run_cmd: str) -> StepBuilder:
        """Create a StepBuilder initialized for bare shorthand run execution."""
        builder = cls()
        builder._type = None
        builder._command = None
        builder._run = run_cmd
        return builder

    @classmethod
    def agent(cls, prompt: str) -> StepBuilder:
        """Create a StepBuilder initialized for agent prompt execution."""
        builder = cls()
        builder._type = StepType.AGENT
        builder._command = None
        builder._prompt = prompt
        return builder

    @classmethod
    def script(cls, script_path: str) -> StepBuilder:
        """Create a StepBuilder initialized for script execution."""
        builder = cls()
        builder._type = StepType.SCRIPT
        builder._command = None
        builder._script_path = script_path
        return builder

    @classmethod
    def uses(cls, template_ref: str) -> StepBuilder:
        """Create a StepBuilder initialized for step inheritance via template reference."""
        builder = cls()
        builder._type = None
        builder._command = None
        builder._uses = template_ref
        return builder

    def with_uses(self, template_ref: str) -> StepBuilder:
        """Set the step inheritance template reference."""
        self._uses = template_ref
        self._type = None
        self._command = None
        self._prompt = None
        self._script_path = None
        self._run = None
        return self

    def with_id(self, step_id: str) -> StepBuilder:
        """Set the step identifier."""
        self._id = step_id
        return self

    def with_name(self, name: str) -> StepBuilder:
        """Set the human-readable step name."""
        self._name = name
        return self

    def with_description(self, description: str) -> StepBuilder:
        """Set the step description."""
        self._description = description
        return self

    def with_timeout(self, timeout_seconds: int) -> StepBuilder:
        """Set the execution timeout in seconds."""
        self._timeout = timeout_seconds
        return self

    def with_env(self, key: str, value: str) -> StepBuilder:
        """Add an environment variable key-value pair."""
        self._env[key] = value
        return self

    def with_env_vars(self, env: dict[str, str]) -> StepBuilder:
        """Merge multiple environment variables."""
        self._env.update(env)
        return self

    def with_retry(
        self,
        max_retries: int = 3,
        backoff_ms: int = 100,
        on_max_retries: FailurePolicy | str = FailurePolicy.ABORT,
    ) -> StepBuilder:
        """Configure step retry policy on failure."""
        terminal_policy = FailurePolicy(on_max_retries) if isinstance(on_max_retries, str) else on_max_retries
        self._on_failure = OnFailureSpec(
            action=FailurePolicy.RETRY,
            max_retries=max_retries,
            backoff_ms=backoff_ms,
            on_max_retries=terminal_policy,
        )
        return self

    def with_on_failure(self, on_failure: OnFailureSpec | FailurePolicy | str) -> StepBuilder:
        """Set explicit on_failure specification or policy."""
        if isinstance(on_failure, OnFailureSpec):
            self._on_failure = on_failure
        elif isinstance(on_failure, FailurePolicy):
            self._on_failure = OnFailureSpec(action=on_failure)
        else:
            self._on_failure = OnFailureSpec(action=FailurePolicy(on_failure))
        return self

    def with_assert(self, step_assert: StepAssert) -> StepBuilder:
        """Set explicit StepAssert model."""
        self._assert = step_assert
        return self

    def _update_assert(self, **kwargs: object) -> StepBuilder:
        current = self._assert.model_dump() if self._assert is not None else {}
        current.update(kwargs)
        self._assert = StepAssert(**current)
        return self

    def assert_exit_code(self, exit_code: int | list[int]) -> StepBuilder:
        """Configure expected exit code assertion."""
        current = self._assert.exit_code if self._assert is not None else None
        return self._update_assert(exit_code=_merge_int_items(current, exit_code))

    def assert_output_contains(self, text: str | list[str]) -> StepBuilder:
        """Configure expected output substring assertion."""
        current = self._assert.output_contains if self._assert is not None else None
        return self._update_assert(output_contains=_merge_string_items(current, text))

    def assert_output_not_contains(self, text: str | list[str]) -> StepBuilder:
        """Configure forbidden output substring assertion."""
        current = self._assert.output_not_contains if self._assert is not None else None
        return self._update_assert(output_not_contains=_merge_string_items(current, text))

    def assert_file_exists(self, path: str | list[str]) -> StepBuilder:
        """Configure expected file existence assertion."""
        current = self._assert.file_exists if self._assert is not None else None
        return self._update_assert(file_exists=_merge_string_items(current, path))

    def assert_file_not_exists(self, path: str | list[str]) -> StepBuilder:
        """Configure expected file non-existence assertion."""
        current = self._assert.file_not_exists if self._assert is not None else None
        return self._update_assert(file_not_exists=_merge_string_items(current, path))

    def assert_file_not_empty(self, path: str | list[str]) -> StepBuilder:
        """Configure expected non-empty file assertion."""
        current = self._assert.file_not_empty if self._assert is not None else None
        return self._update_assert(file_not_empty=_merge_string_items(current, path))

    def build(self) -> StepDefinition:
        """Build and validate the StepDefinition instance."""
        if self._run is not None:
            return StepDefinition(
                id=self._id,
                run=self._run,
                name=self._name,
                description=self._description,
                timeout_seconds=self._timeout,
                env=dict(self._env),
                assert_=self._assert,
                on_failure=self._on_failure,
            )
        if self._uses is not None:
            return StepDefinition(
                id=self._id,
                uses=self._uses,
                name=self._name,
                description=self._description,
                timeout_seconds=self._timeout,
                env=dict(self._env),
                assert_=self._assert,
                on_failure=self._on_failure,
            )
        return StepDefinition(
            id=self._id,
            type=self._type,
            command=self._command,
            prompt=self._prompt,
            script_path=self._script_path,
            name=self._name,
            description=self._description,
            timeout_seconds=self._timeout,
            env=dict(self._env),
            assert_=self._assert,
            on_failure=self._on_failure,
        )


class BlueprintBuilder:
    """Fluent builder for constructing validated BlueprintDefinition models in tests."""

    def __init__(self, name: str = "test-blueprint") -> None:
        self._name: str = name
        self._description: str = ""
        self._summary: str = ""
        self._version: int | str = 1
        self._use_sandbox: bool = True
        self._timeout_seconds: int | None = None
        self._env: dict[str, str] = {}
        self._inputs: dict[str, ParameterInput] = {}
        self._defaults: BlueprintDefaults = BlueprintDefaults()
        self._steps: list[StepDefinition | StepBuilder | LoopStepBlock] = []

    @classmethod
    def workflow(cls, name: str = "test-workflow") -> BlueprintBuilder:
        """Create a BlueprintBuilder initialized for workflow blueprints."""
        return cls(name=name)

    @classmethod
    def task(cls, name: str = "test-task") -> BlueprintBuilder:
        """Create a BlueprintBuilder initialized for task blueprints."""
        return cls(name=name)

    def with_name(self, name: str) -> BlueprintBuilder:
        """Set the blueprint name."""
        self._name = name
        return self

    def with_description(self, description: str) -> BlueprintBuilder:
        """Set the blueprint description."""
        self._description = description
        return self

    def with_summary(self, summary: str) -> BlueprintBuilder:
        """Set the blueprint summary."""
        self._summary = summary
        return self

    def with_version(self, version: int | str) -> BlueprintBuilder:
        """Set the blueprint version."""
        self._version = version
        return self

    def with_use_sandbox(self, use_sandbox: bool) -> BlueprintBuilder:
        """Configure whether blueprint executes in an isolated sandbox."""
        self._use_sandbox = use_sandbox
        return self

    def with_timeout(self, timeout_seconds: int) -> BlueprintBuilder:
        """Set execution timeout in seconds."""
        self._timeout_seconds = timeout_seconds
        return self

    def with_env(self, key: str, value: str) -> BlueprintBuilder:
        """Add an environment variable key-value pair."""
        self._env[key] = value
        return self

    def with_env_vars(self, env: dict[str, str]) -> BlueprintBuilder:
        """Merge multiple environment variables."""
        self._env.update(env)
        return self

    def with_input(
        self,
        name: str,
        *,
        input_type: InputType | str = InputType.STRING,
        default: str | int | bool | None = None,
        required: bool = False,
        description: str | None = None,
        aliases: list[str] | None = None,
    ) -> BlueprintBuilder:
        """Declare a typed blueprint input parameter."""
        resolved_type = InputType(input_type) if isinstance(input_type, str) else input_type
        self._inputs[name] = ParameterInput(
            type=resolved_type,
            default=default,
            required=required,
            description=description,
            aliases=aliases or [],
        )
        return self

    def with_step(self, step: StepDefinition | StepBuilder | LoopStepBlock) -> BlueprintBuilder:
        """Append a step to the blueprint."""
        self._steps.append(step)
        return self

    def add_step(self, step: StepDefinition | StepBuilder | LoopStepBlock) -> BlueprintBuilder:
        """Alias for with_step."""
        return self.with_step(step)

    def with_defaults(self, defaults: BlueprintDefaults) -> BlueprintBuilder:
        """Configure blueprint defaults."""
        self._defaults = defaults
        return self

    def build(self) -> BlueprintDefinition:
        """Build and validate the BlueprintDefinition model."""
        resolved_steps: list[StepDefinition | LoopStepBlock] = []
        for step in self._steps:
            if isinstance(step, StepBuilder):
                resolved_steps.append(step.build())
            else:
                resolved_steps.append(step)

        return BlueprintDefinition(
            name=self._name,
            description=self._description,
            summary=self._summary,
            version=self._version,
            use_sandbox=self._use_sandbox,
            timeout_seconds=self._timeout_seconds,
            env=dict(self._env),
            inputs=dict(self._inputs),
            defaults=self._defaults,
            steps=resolved_steps,
        )


class WorkspaceBuilder:
    """Fluent builder for scaffolding test workspaces on the filesystem."""

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path | None = root
        self._project_name: str | None = None
        self._scaffold_config: bool = True
        self._config_overwrite: bool = True
        self._scaffold_database: bool = True
        self._scaffold_catalog: bool = True
        self._catalog_force: bool = True
        self._init_git: bool = False
        self._config_data: dict[str, Any] | None = None
        self._db_rel_path: str = DEFAULT_DB_REL_PATH
        self._git_branch: str = "main"
        self._git_user_name: str = "Test User"
        self._git_user_email: str = "test@example.com"

    def with_project_name(self, name: str) -> WorkspaceBuilder:
        """Set project name for generated configuration."""
        self._project_name = name
        return self

    def with_config(
        self,
        *,
        data: dict[str, Any] | None = None,
        overwrite: bool = True,
    ) -> WorkspaceBuilder:
        """Enable config generation with optional explicit payload."""
        self._scaffold_config = True
        self._config_data = data
        self._config_overwrite = overwrite
        return self

    def without_config(self) -> WorkspaceBuilder:
        """Disable config.json generation."""
        self._scaffold_config = False
        return self

    def with_database(self, db_rel_path: str = DEFAULT_DB_REL_PATH) -> WorkspaceBuilder:
        """Enable SQLite database migration."""
        self._scaffold_database = True
        self._db_rel_path = db_rel_path
        return self

    def without_database(self) -> WorkspaceBuilder:
        """Disable SQLite database creation."""
        self._scaffold_database = False
        return self

    def with_catalog_templates(self, *, force: bool = True) -> WorkspaceBuilder:
        """Enable catalog templates seeding."""
        self._scaffold_catalog = True
        self._catalog_force = force
        return self

    def without_catalog_templates(self) -> WorkspaceBuilder:
        """Disable catalog templates seeding."""
        self._scaffold_catalog = False
        return self

    def with_git(
        self,
        *,
        branch: str = "main",
        user_name: str = "Test User",
        user_email: str = "test@example.com",
    ) -> WorkspaceBuilder:
        """Enable Git repository initialization."""
        self._init_git = True
        self._git_branch = branch
        self._git_user_name = user_name
        self._git_user_email = user_email
        return self

    def build(self) -> Path:
        """Scaffold and return the prepared workspace directory root."""
        if self._root is not None:
            workspace_root = self._root.resolve()
            workspace_root.mkdir(parents=True, exist_ok=True)
        else:
            workspace_root = Path(tempfile.mkdtemp(prefix="wt_workspace_")).resolve()

        dot_worktree = workspace_root / ".worktree"
        dot_worktree.mkdir(parents=True, exist_ok=True)
        bootstrap_worktree(dot_worktree)

        (dot_worktree / "sandboxes").mkdir(parents=True, exist_ok=True)
        (dot_worktree / "catalog").mkdir(parents=True, exist_ok=True)

        if self._init_git:
            self._scaffold_git_repository(workspace_root)

        if self._scaffold_config:
            self._scaffold_workspace_config(workspace_root, dot_worktree)

        if self._scaffold_database:
            init_database(workspace_root, db_rel_path=self._db_rel_path)

        if self._scaffold_catalog:
            seed_all_catalog_templates(workspace_root, force=self._catalog_force)

        return workspace_root

    def _scaffold_git_repository(self, workspace_root: Path) -> None:
        subprocess.run(
            ["git", "init", "-b", self._git_branch],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", self._git_user_name],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", self._git_user_email],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )

        readme_path = workspace_root / "README.md"
        if not readme_path.exists():
            readme_path.write_text("# Test Repo\n", encoding="utf-8")

        subprocess.run(
            ["git", "add", "README.md"],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )

    def _scaffold_workspace_config(self, workspace_root: Path, dot_worktree: Path) -> None:
        config_path = dot_worktree / "config.json"
        if self._config_data is not None:
            if not self._config_overwrite and config_path.exists():
                return
            Filesystem.atomic_write_json(config_path, self._config_data)
        else:
            project_name = self._project_name or workspace_root.name
            generate_default_config(config_path, project_name=project_name, overwrite=self._config_overwrite)
