"""Validate unified diffs against size/count/binary/path limits (no git apply)."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
_MINUS_RE = re.compile(r"^--- (?:a/)?(.+)$")
_PLUS_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_RENAME_FROM_RE = re.compile(r"^rename from (.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (.+)$")
_COPY_FROM_RE = re.compile(r"^copy from (.+)$")
_COPY_TO_RE = re.compile(r"^copy to (.+)$")
_BINARY_FILES_RE = re.compile(r"^Binary files (?:a/)?(.+) and (?:b/)?(.+) differ\s*$")
_GIT_BINARY_PATCH_RE = re.compile(r"^GIT binary patch\s*$")
_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:")


class PatchApplyStatus(StrEnum):
    """Classified outcomes for validating or applying a unified diff."""

    APPLIED = "applied"
    CHECKED_OK = "checked_ok"
    EMPTY_DIFF = "empty_diff"
    TOO_LARGE = "too_large"
    TOO_MANY_FILES = "too_many_files"
    BINARY_REJECTED = "binary_rejected"
    UNSAFE_PATH = "unsafe_path"
    INVALID_DIFF = "invalid_diff"
    CONFLICT = "conflict"
    GIT_TIMEOUT = "git_timeout"
    SANDBOX_MISSING = "sandbox_missing"


class PatchApplyResult(BaseModel):
    """Non-raising result of patch validation / apply."""

    model_config = {"extra": "forbid", "strict": True}

    status: PatchApplyStatus
    touched_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the patch applied or dry-check succeeded."""
        return self.status in {
            PatchApplyStatus.APPLIED,
            PatchApplyStatus.CHECKED_OK,
        }


def _normalize_diff_path(raw: str) -> str | None:
    """Normalize a path token from a diff header to a relative posix path.

    Returns:
        Normalized path, or ``None`` when the token is a null device marker.
    """
    path = raw.strip()
    if not path or path == "/dev/null":
        return None
    if "\t" in path:
        path = path.split("\t", 1)[0]
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1]
    return path.replace("\\", "/")


def _add_path(paths: set[str], raw: str) -> None:
    norm = _normalize_diff_path(raw)
    if norm is not None:
        paths.add(norm)


def _strip_ab_prefix(token: str) -> str:
    if token.startswith("a/") or token.startswith("b/"):
        return token[2:]
    return token


def _parse_unified_diff(
    unified_diff: str,
) -> tuple[list[str], list[str], str | None]:
    """Parse a unified diff for target paths and binary markers.

    Returns:
        (touched_paths_sorted_unique, binary_paths, parse_error_or_none)
    """
    text = unified_diff.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    has_file_header = False
    paths: set[str] = set()
    binary_paths: set[str] = set()
    # Paths belonging to the current ``diff --git`` file section.
    section_paths: set[str] = set()

    for line in lines:
        m = _DIFF_GIT_RE.match(line)
        if m:
            has_file_header = True
            section_paths = set()
            for group in m.groups():
                _add_path(paths, group)
                _add_path(section_paths, group)
            continue

        if line.startswith("diff --git "):
            rest = line[len("diff --git ") :].strip()
            parts = rest.split(" ", 1)
            if len(parts) != 2:
                return [], [], "malformed diff --git header"
            has_file_header = True
            section_paths = set()
            for part in parts:
                token = _strip_ab_prefix(part)
                _add_path(paths, token)
                _add_path(section_paths, token)
            continue

        if line.startswith("--- "):
            has_file_header = True
            body = line[4:]
            if body != "/dev/null":
                m = _MINUS_RE.match(line)
                raw = m.group(1) if m else body
                _add_path(paths, raw)
                _add_path(section_paths, raw)
            continue

        if line.startswith("+++ "):
            has_file_header = True
            body = line[4:]
            if body != "/dev/null":
                m = _PLUS_RE.match(line)
                raw = m.group(1) if m else body
                _add_path(paths, raw)
                _add_path(section_paths, raw)
            continue

        m = _RENAME_FROM_RE.match(line) or _COPY_FROM_RE.match(line)
        if m:
            _add_path(paths, m.group(1))
            _add_path(section_paths, m.group(1))
            continue

        m = _RENAME_TO_RE.match(line) or _COPY_TO_RE.match(line)
        if m:
            _add_path(paths, m.group(1))
            _add_path(section_paths, m.group(1))
            continue

        m = _BINARY_FILES_RE.match(line)
        if m:
            has_file_header = True
            for group in m.groups():
                _add_path(paths, group)
                _add_path(section_paths, group)
                _add_path(binary_paths, group)
            continue

        if _GIT_BINARY_PATCH_RE.match(line):
            if section_paths:
                binary_paths.update(section_paths)
            elif paths:
                binary_paths.update(paths)
            else:
                binary_paths.add("(unknown)")
            continue

        if line.startswith("literal ") or line.startswith("delta "):
            if section_paths:
                binary_paths.update(section_paths)
            elif paths:
                binary_paths.update(paths)
            else:
                binary_paths.add("(unknown)")
            continue

    if not has_file_header:
        return (
            [],
            [],
            "no file headers found (expected diff --git or --- / +++ )",
        )

    if not paths and not binary_paths:
        return [], [], "no target file paths found in diff headers"

    return sorted(paths), sorted(binary_paths), None


def _is_unsafe_path(rel_path: str, sandbox_path: Path) -> bool:
    """Return True if ``rel_path`` is absolute or would escape ``sandbox_path``."""
    if not rel_path or rel_path == "(unknown)":
        return True
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return True
    if _DRIVE_PATH_RE.match(rel_path):
        return True
    if any(part == ".." for part in candidate.parts):
        return True
    try:
        sandbox_resolved = sandbox_path.resolve()
        resolved = (sandbox_resolved / candidate).resolve()
        resolved.relative_to(sandbox_resolved)
    except (OSError, ValueError):
        return True
    return False


def validate_patch_text(
    unified_diff: str,
    *,
    max_files: int,
    max_patch_kb: int,
    reject_binary_changes: bool,
    sandbox_path: Path,
) -> PatchApplyResult:
    """Validate diff text against size/count/binary/path limits, no git apply.

    Returns ``PatchApplyResult(status=CHECKED_OK, touched_files=...)`` when all
    checks pass; otherwise a result carrying the failing status. Reused both as
    the pre-``git apply`` gate for diff-returning providers and as the
    post-hoc gate for direct-mutation providers, whose changes are already
    reflected on disk.

    Args:
        unified_diff: Full unified diff text.
        max_files: Maximum distinct target files allowed.
        max_patch_kb: Maximum UTF-8 byte size of the diff in KiB.
        reject_binary_changes: When True, reject binary file markers.
        sandbox_path: Sandbox root used for the unsafe-path check.

    Returns:
        Structured :class:`PatchApplyResult` with status, touched files, errors.
    """
    if not isinstance(unified_diff, str) or not unified_diff.strip():
        return PatchApplyResult(
            status=PatchApplyStatus.EMPTY_DIFF,
            errors=["Patch is empty or whitespace-only.\nFix:\n- ensure the agent returned a non-empty unified diff"],
        )

    size_bytes = len(unified_diff.encode("utf-8"))
    max_bytes = max_patch_kb * 1024
    if size_bytes > max_bytes:
        return PatchApplyResult(
            status=PatchApplyStatus.TOO_LARGE,
            errors=[
                f"Patch exceeds max_patch_kb ({max_patch_kb} KiB) "
                f"(size={size_bytes} bytes).\n"
                "Fix:\n"
                "- reduce agent change size or raise patch.max_patch_kb / "
                "workflow patch.max_patch_kb"
            ],
        )

    touched, binary_paths, parse_error = _parse_unified_diff(unified_diff)
    if parse_error is not None:
        return PatchApplyResult(
            status=PatchApplyStatus.INVALID_DIFF,
            errors=[
                f"Patch is not a valid unified diff: {parse_error}\n"
                "Fix:\n"
                "- return a standard unified diff (diff --git / --- +++ / @@ hunks)"
            ],
        )

    if len(touched) > max_files:
        return PatchApplyResult(
            status=PatchApplyStatus.TOO_MANY_FILES,
            errors=[
                f"Patch touches {len(touched)} files; max_files is {max_files}.\n"
                "Fix:\n"
                "- split the change or raise patch.max_files"
            ],
        )

    if reject_binary_changes and binary_paths:
        joined = ", ".join(binary_paths) if binary_paths else "(binary change)"
        return PatchApplyResult(
            status=PatchApplyStatus.BINARY_REJECTED,
            touched_files=list(touched),
            errors=[
                f"Patch includes binary file changes which are rejected: {joined}.\n"
                "Fix:\n"
                "- avoid binary edits in the agent patch, or set "
                "reject_binary_changes=false when allowed"
            ],
        )

    try:
        sandbox_ok = sandbox_path.is_dir()
    except OSError:
        sandbox_ok = False
    if not sandbox_ok:
        return PatchApplyResult(
            status=PatchApplyStatus.SANDBOX_MISSING,
            touched_files=list(touched),
            errors=[
                f"Sandbox path does not exist or is not a directory: "
                f"'{sandbox_path}'.\n"
                "Fix:\n"
                "- create the sandbox before applying a patch"
            ],
        )

    for rel in touched:
        if _is_unsafe_path(rel, sandbox_path):
            return PatchApplyResult(
                status=PatchApplyStatus.UNSAFE_PATH,
                touched_files=list(touched),
                errors=[
                    f"Patch path is absolute or escapes the sandbox: '{rel}'.\n"
                    "Fix:\n"
                    "- use sandbox-relative paths only "
                    "(no absolute paths or '..' segments)"
                ],
            )

    return PatchApplyResult(
        status=PatchApplyStatus.CHECKED_OK,
        touched_files=list(touched),
    )
