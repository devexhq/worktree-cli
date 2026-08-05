"""Discover candidate workflow definition files without parsing contents."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.config.loader import load_config_result

DEFAULT_WORKFLOWS_DIR = ".worktree/workflows"
WORKFLOW_FILE_SUFFIXES = (".yml", ".yaml")


class WorkflowDiscoveryStatus(StrEnum):
    """Classified outcomes for discovering workflow definition files."""

    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_A_DIRECTORY = "not_a_directory"
    UNREADABLE = "unreadable"
    CONFIG_UNAVAILABLE = "config_unavailable"


class WorkflowDiscoveryResult(BaseModel):
    """Non-raising result of scanning a workflows directory for candidate files."""

    model_config = {"extra": "forbid", "strict": True}

    status: WorkflowDiscoveryStatus
    workflows_dir: Path
    paths: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the workflows directory was scanned successfully."""
        return self.status == WorkflowDiscoveryStatus.OK


def _resolve_root(cwd: Path | None) -> Path:
    return (cwd or Path.cwd()).expanduser().resolve()


def _resolve_path(path: Path | str, *, cwd: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve()


def resolve_workflows_dir(
    cwd: Path | None = None,
    *,
    workflows_dir: Path | str | None = None,
    use_config: bool = True,
) -> tuple[Path, list[str]]:
    """Return ``(absolute_workflows_dir, resolution_errors)``.

    If ``workflows_dir`` is set, resolve it and return no errors.
    If ``use_config`` and ``workflows_dir`` is None, load config for
    ``paths.workflows_dir``.
    If not ``use_config`` and ``workflows_dir`` is None, use
    ``cwd / '.worktree/workflows'``.

    Args:
        cwd: Repository root used for relative path resolution.
        workflows_dir: Explicit workflows directory; wins when provided.
        use_config: When True and ``workflows_dir`` is omitted, read
            ``paths.workflows_dir`` from config.

    Returns:
        Absolute workflows directory path and any resolution errors.
    """
    root = _resolve_root(cwd)

    if workflows_dir is not None:
        return _resolve_path(workflows_dir, cwd=root), []

    if not use_config:
        return (root / DEFAULT_WORKFLOWS_DIR).resolve(), []

    load_result = load_config_result(cwd=root)
    if not load_result.ok or load_result.config is None:
        fallback = (root / DEFAULT_WORKFLOWS_DIR).resolve()
        detail = "; ".join(
            msg.splitlines()[0] for msg in load_result.errors if msg
        ) or ("configuration could not be loaded")
        return fallback, [
            f"Workflow directory could not be resolved from config: {detail} "
            f"(WORKFLOW_CONFIG_UNAVAILABLE).\n"
            "Fix:\n"
            "- run `wt init` or `wt config validate`\n"
            "- or pass an explicit workflows directory"
        ]

    return _resolve_path(load_result.config.paths.workflows_dir, cwd=root), []


def _is_candidate_workflow_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("_"):
        return False
    if not name.endswith(WORKFLOW_FILE_SUFFIXES):
        return False
    try:
        return path.is_file()
    except OSError:
        return False


def discover_workflow_files(
    cwd: Path | None = None,
    *,
    workflows_dir: Path | str | None = None,
    use_config: bool = True,
) -> WorkflowDiscoveryResult:
    """Scan a workflows directory for candidate definition files.

    Non-raising primary discovery API. Resolves the workflows directory, enumerates
    direct children only, and returns absolute candidate paths in deterministic
    order. Does not parse YAML, print, exit, or mutate the filesystem.

    Args:
        cwd: Repository root used for relative path and config resolution.
        workflows_dir: Explicit workflows directory override.
        use_config: When True and ``workflows_dir`` is omitted, read
            ``paths.workflows_dir`` from config.

    Returns:
        Classified ``WorkflowDiscoveryResult`` with absolute ``workflows_dir`` and
        candidate ``paths``.
    """
    resolved_dir, resolution_errors = resolve_workflows_dir(
        cwd=cwd,
        workflows_dir=workflows_dir,
        use_config=use_config,
    )

    if resolution_errors:
        return WorkflowDiscoveryResult(
            status=WorkflowDiscoveryStatus.CONFIG_UNAVAILABLE,
            workflows_dir=resolved_dir,
            errors=resolution_errors,
        )

    if resolved_dir.exists() and not resolved_dir.is_dir():
        return WorkflowDiscoveryResult(
            status=WorkflowDiscoveryStatus.NOT_A_DIRECTORY,
            workflows_dir=resolved_dir,
            errors=[
                f"Workflow path exists as a file, not a directory: '{resolved_dir}' "
                f"(WORKFLOW_DIR_NOT_A_DIRECTORY)."
            ],
        )

    if not resolved_dir.exists():
        return WorkflowDiscoveryResult(
            status=WorkflowDiscoveryStatus.NOT_FOUND,
            workflows_dir=resolved_dir,
            errors=[
                f"Workflow directory not found at '{resolved_dir}' "
                f"(WORKFLOW_DIR_NOT_FOUND).\n"
                "Fix:\n"
                "- run `wt init` to create starter workflows\n"
                "- or create the directory and add workflow YAML files"
            ],
        )

    try:
        children = list(resolved_dir.iterdir())
    except OSError as exc:
        return WorkflowDiscoveryResult(
            status=WorkflowDiscoveryStatus.UNREADABLE,
            workflows_dir=resolved_dir,
            errors=[
                f"Unable to read workflow directory at '{resolved_dir}': {exc} "
                f"(WORKFLOW_DIR_UNREADABLE).\n"
                "Fix:\n"
                "- check directory permissions and that the path is listable"
            ],
        )

    candidates: list[Path] = []
    for child in children:
        if not _is_candidate_workflow_file(child):
            continue
        candidates.append(child.resolve())

    candidates.sort(key=lambda path: (path.name, str(path)))

    return WorkflowDiscoveryResult(
        status=WorkflowDiscoveryStatus.OK,
        workflows_dir=resolved_dir,
        paths=candidates,
    )
