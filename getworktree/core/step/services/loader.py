from pathlib import Path

import yaml
from pydantic import ValidationError

from getworktree.core.step import StepDefinition, StepNotFoundError, StepValidationError


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

    # Check direct filename match first (<step_id_or_name>.yaml / .yml)
    for ext in (".yaml", ".yml"):
        direct_path = steps_dir / f"{step_id_or_name}{ext}"
        if direct_path.exists() and direct_path.is_file():
            return load_step_definition(direct_path)

    # Scan step files in steps_dir for matching id or name
    for path in sorted(steps_dir.iterdir()):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            try:
                step = load_step_definition(path)
                if step.id == step_id_or_name or step.name == step_id_or_name:
                    return step
            except StepValidationError:
                # If searching by ID, invalid files will raise when directly selected,
                # but during directory scan we log/ignore unrelated broken files.
                continue

    raise StepNotFoundError(f"Step '{step_id_or_name}' not found in '{steps_dir}'.")
