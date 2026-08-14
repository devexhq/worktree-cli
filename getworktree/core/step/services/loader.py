from pathlib import Path

import yaml
from pydantic import ValidationError

from getworktree.core.step.exceptions import StepNotFoundError, StepValidationError
from getworktree.core.step.models import StepDefinition


def load_step_definition(path: Path) -> StepDefinition:
    """Load and validate a StepDefinition from a YAML file.

    Args:
        path: Path to the YAML step definition file.

    Returns:
        Validated StepDefinition instance.

    Raises:
        StepNotFoundError: If the file does not exist or is not a regular file.
        StepValidationError: If YAML parsing fails or schema validation fails.
    """
    path = path.resolve()
    if not path.exists() or not path.is_file():
        raise StepNotFoundError(f"Step definition file not found at '{path}'.")

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except (OSError, yaml.YAMLError) as exc:
        raise StepValidationError(f"Failed to read or parse YAML step definition at '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise StepValidationError(f"Root of step definition YAML at '{path}' must be a mapping object.")

    try:
        return StepDefinition.model_validate(data)
    except (ValidationError, ValueError) as exc:
        raise StepValidationError(f"Step definition validation failed for '{path}': {exc}") from exc


def _direct_step_path(steps_dir: Path, step_id_or_name: str) -> Path | None:
    """Return a direct filename match under ``steps_dir``, if present."""
    for ext in (".yaml", ".yml"):
        direct_path = steps_dir / f"{step_id_or_name}{ext}"
        if direct_path.exists() and direct_path.is_file():
            return direct_path
    return None


def _step_matches(step: StepDefinition, step_id_or_name: str) -> bool:
    return step.id == step_id_or_name or step.name == step_id_or_name


def _find_step_by_scan(steps_dir: Path, step_id_or_name: str) -> StepDefinition | None:
    """Scan YAML step files for an id/name match, skipping unrelated invalid files."""
    for path in sorted(steps_dir.iterdir()):
        if not (path.is_file() and path.suffix in (".yaml", ".yml")):
            continue
        try:
            step = load_step_definition(path)
        except StepValidationError:
            # Invalid siblings are ignored during scan; direct path load still raises.
            continue
        if _step_matches(step, step_id_or_name):
            return step
    return None


def load_step_by_id(step_id_or_name: str, cwd: Path | None = None) -> StepDefinition:
    """Resolve a StepDefinition from .worktree/templates/steps/ by ID or name.

    Args:
        step_id_or_name: Identifier or name slug of the step.
        cwd: Optional working directory root (defaults to Path.cwd()).

    Returns:
        Resolved StepDefinition instance.

    Raises:
        StepNotFoundError: If step directory does not exist or step is not found.
        StepValidationError: If matching file has schema validation errors.
    """
    root_dir = cwd or Path.cwd()
    steps_dir = root_dir / ".worktree" / "catalog" / "steps"

    if not steps_dir.exists() or not steps_dir.is_dir():
        raise StepNotFoundError(f"Step '{step_id_or_name}' not found. Directory '{steps_dir}' does not exist.")

    direct_path = _direct_step_path(steps_dir, step_id_or_name)
    if direct_path is not None:
        return load_step_definition(direct_path)

    matched = _find_step_by_scan(steps_dir, step_id_or_name)
    if matched is not None:
        return matched

    raise StepNotFoundError(f"Step '{step_id_or_name}' not found in '{steps_dir}'.")
