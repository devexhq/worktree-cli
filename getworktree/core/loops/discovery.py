"""Discover candidate loop definition files without parsing contents."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from getworktree.core.config.loader import load_config_result

DEFAULT_LOOPS_DIR = ".worktree/loops"
LOOP_FILE_SUFFIXES = (".yml", ".yaml")


class LoopDiscoveryStatus(StrEnum):
    """Classified outcomes for discovering loop definition files."""

    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_A_DIRECTORY = "not_a_directory"
    UNREADABLE = "unreadable"
    CONFIG_UNAVAILABLE = "config_unavailable"


class LoopDiscoveryResult(BaseModel):
    """Non-raising result of scanning a loops directory for candidate files."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopDiscoveryStatus
    loops_dir: Path
    paths: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the loops directory was scanned successfully."""
        return self.status == LoopDiscoveryStatus.OK


def _resolve_root(cwd: Path | None) -> Path:
    return (cwd or Path.cwd()).expanduser().resolve()


def _resolve_path(path: Path | str, *, cwd: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve()


def _error_not_found(path: Path) -> str:
    return (
        f"Loop directory not found at '{path}' (LOOP_DIR_NOT_FOUND).\n"
        "Fix:\n"
        "- run `wt init` to create starter loops\n"
        "- or create the directory and add loop YAML files"
    )


def _error_not_a_directory(path: Path) -> str:
    return (
        f"Loop path exists as a file, not a directory: '{path}' "
        f"(LOOP_DIR_NOT_A_DIRECTORY)."
    )


def _error_unreadable(path: Path, detail: str) -> str:
    return (
        f"Unable to read loop directory at '{path}': {detail} "
        f"(LOOP_DIR_UNREADABLE).\n"
        "Fix:\n"
        "- check directory permissions and that the path is listable"
    )


def _error_config_unavailable(messages: list[str]) -> str:
    detail = "; ".join(msg.splitlines()[0] for msg in messages if msg) or (
        "configuration could not be loaded"
    )
    return (
        f"Loop directory could not be resolved from config: {detail} "
        f"(LOOP_CONFIG_UNAVAILABLE).\n"
        "Fix:\n"
        "- run `wt init` or `wt config validate`\n"
        "- or pass an explicit loops directory"
    )


def resolve_loops_dir(
    cwd: Path | None = None,
    *,
    loops_dir: Path | str | None = None,
    use_config: bool = True,
) -> tuple[Path, list[str]]:
    """Return ``(absolute_loops_dir, resolution_errors)``.

    If ``loops_dir`` is set, resolve it and return no errors.
    If ``use_config`` and ``loops_dir`` is None, load config for
    ``paths.loops_dir``.
    If not ``use_config`` and ``loops_dir`` is None, use
    ``cwd / '.worktree/loops'``.

    Args:
        cwd: Repository root used for relative path resolution.
        loops_dir: Explicit loops directory; wins when provided.
        use_config: When True and ``loops_dir`` is omitted, read
            ``paths.loops_dir`` from config.

    Returns:
        Absolute loops directory path and any resolution errors.
    """
    root = _resolve_root(cwd)

    if loops_dir is not None:
        return _resolve_path(loops_dir, cwd=root), []

    if not use_config:
        return (root / DEFAULT_LOOPS_DIR).resolve(), []

    load_result = load_config_result(cwd=root)
    if not load_result.ok or load_result.config is None:
        fallback = (root / DEFAULT_LOOPS_DIR).resolve()
        return fallback, [_error_config_unavailable(load_result.errors)]

    return _resolve_path(load_result.config.paths.loops_dir, cwd=root), []


def _is_candidate_loop_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("_"):
        return False
    if not name.endswith(LOOP_FILE_SUFFIXES):
        return False
    try:
        return path.is_file()
    except OSError:
        return False


def discover_loop_files(
    cwd: Path | None = None,
    *,
    loops_dir: Path | str | None = None,
    use_config: bool = True,
) -> LoopDiscoveryResult:
    """Scan a loops directory for candidate definition files.

    Non-raising primary discovery API. Resolves the loops directory, enumerates
    direct children only, and returns absolute candidate paths in deterministic
    order. Does not parse YAML, print, exit, or mutate the filesystem.

    Args:
        cwd: Repository root used for relative path and config resolution.
        loops_dir: Explicit loops directory override.
        use_config: When True and ``loops_dir`` is omitted, read
            ``paths.loops_dir`` from config.

    Returns:
        Classified ``LoopDiscoveryResult`` with absolute ``loops_dir`` and
        candidate ``paths``.
    """
    resolved_dir, resolution_errors = resolve_loops_dir(
        cwd=cwd,
        loops_dir=loops_dir,
        use_config=use_config,
    )

    if resolution_errors:
        return LoopDiscoveryResult(
            status=LoopDiscoveryStatus.CONFIG_UNAVAILABLE,
            loops_dir=resolved_dir,
            errors=resolution_errors,
        )

    if resolved_dir.exists() and not resolved_dir.is_dir():
        return LoopDiscoveryResult(
            status=LoopDiscoveryStatus.NOT_A_DIRECTORY,
            loops_dir=resolved_dir,
            errors=[_error_not_a_directory(resolved_dir)],
        )

    if not resolved_dir.exists():
        return LoopDiscoveryResult(
            status=LoopDiscoveryStatus.NOT_FOUND,
            loops_dir=resolved_dir,
            errors=[_error_not_found(resolved_dir)],
        )

    try:
        children = list(resolved_dir.iterdir())
    except OSError as exc:
        return LoopDiscoveryResult(
            status=LoopDiscoveryStatus.UNREADABLE,
            loops_dir=resolved_dir,
            errors=[_error_unreadable(resolved_dir, str(exc))],
        )

    candidates: list[Path] = []
    for child in children:
        if not _is_candidate_loop_file(child):
            continue
        candidates.append(child.resolve())

    candidates.sort(key=lambda path: (path.name, str(path)))

    return LoopDiscoveryResult(
        status=LoopDiscoveryStatus.OK,
        loops_dir=resolved_dir,
        paths=candidates,
    )
