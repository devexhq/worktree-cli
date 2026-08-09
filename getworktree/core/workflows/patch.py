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


class _MalformedDiffHeader(Exception):
    """Raised when a ``diff --git`` header cannot be parsed."""


class GitDiffParser:
    """Parse a unified diff for target paths and binary markers."""

    # Tried in order for each line; first handler to return truthy wins.
    _HANDLERS = (
        "_parse_diff_git_header",
        "_parse_loose_diff_git_header",
        "_parse_old_file_header",
        "_parse_new_file_header",
        "_parse_rename_or_copy_from",
        "_parse_rename_or_copy_to",
        "_parse_binary_files_header",
        "_mark_git_binary_patch_paths",
        "_mark_literal_or_delta_binary_paths",
    )

    def __init__(self, unified_diff: str):
        self.has_file_header = False
        self.paths: set[str] = set()
        self.binary_paths: set[str] = set()
        # Paths belonging to the current ``diff --git`` file section.
        self.section_paths: set[str] = set()
        self.unified_diff = unified_diff

    def _record_path(
        self, raw: str, *, paths: bool = False, section_paths: bool = False, binary_paths: bool = False
    ) -> None:
        if paths:
            _add_path(self.paths, raw)

        if section_paths:
            _add_path(self.section_paths, raw)

        if binary_paths:
            _add_path(self.binary_paths, raw)

    def _record_binary_fallback(self) -> None:
        """Mark the current section (or all known paths) as binary."""
        if self.section_paths:
            self.binary_paths.update(self.section_paths)
        elif self.paths:
            self.binary_paths.update(self.paths)
        else:
            self.binary_paths.add("(unknown)")

    def _parse_diff_git_header(self):
        m = _DIFF_GIT_RE.match(self.line)
        if m:
            self.has_file_header = True
            self.section_paths = set()

            for group in m.groups():
                self._record_path(group, paths=True, section_paths=True)

            return True

    def _parse_loose_diff_git_header(self):
        if not self.line.startswith("diff --git "):
            return False

        rest = self.line[len("diff --git ") :].strip()
        parts = rest.split(" ", 1)

        if len(parts) != 2:
            raise _MalformedDiffHeader("malformed diff --git header")

        self.has_file_header = True
        self.section_paths = set()

        for part in parts:
            token = _strip_ab_prefix(part)
            self._record_path(token, paths=True, section_paths=True)

        return True

    def _parse_old_file_header(self):
        if self.line.startswith("--- "):
            self.has_file_header = True
            body = self.line[4:]

            if body != "/dev/null":
                m = _MINUS_RE.match(self.line)
                raw = m.group(1) if m else body
                self._record_path(raw, paths=True, section_paths=True)

            return True

    def _parse_new_file_header(self):
        if self.line.startswith("+++ "):
            self.has_file_header = True
            body = self.line[4:]
            if body != "/dev/null":
                m = _PLUS_RE.match(self.line)
                raw = m.group(1) if m else body
                self._record_path(raw, paths=True, section_paths=True)
            return True

    def _parse_rename_or_copy_from(self):
        m = _RENAME_FROM_RE.match(self.line) or _COPY_FROM_RE.match(self.line)
        if m:
            self._record_path(m.group(1), paths=True, section_paths=True)
            return True

    def _parse_rename_or_copy_to(self):
        m = _RENAME_TO_RE.match(self.line) or _COPY_TO_RE.match(self.line)
        if m:
            self._record_path(m.group(1), paths=True, section_paths=True)
            return True

    def _parse_binary_files_header(self):
        m = _BINARY_FILES_RE.match(self.line)
        if m:
            self.has_file_header = True
            for group in m.groups():
                self._record_path(group, paths=True, section_paths=True, binary_paths=True)
            return True

    def _mark_git_binary_patch_paths(self):
        if _GIT_BINARY_PATCH_RE.match(self.line):
            self._record_binary_fallback()
            return True

    def _mark_literal_or_delta_binary_paths(self):
        if self.line.startswith("literal ") or self.line.startswith("delta "):
            self._record_binary_fallback()
            return True

    def _parse_line(self) -> None:
        """Try each header handler in turn, stopping at the first match."""
        for name in self._HANDLERS:
            if getattr(self, name)():
                return

    def parse(self):
        """Run the parse operation."""
        text = self.unified_diff.replace("\r\n", "\n").replace("\r", "\n")

        try:
            for line in text.split("\n"):
                self.line = line
                self._parse_line()
        except _MalformedDiffHeader as exc:
            return [], [], str(exc)

        if not self.has_file_header:
            return (
                [],
                [],
                "no file headers found (expected diff --git or --- / +++ )",
            )

        if not self.paths and not self.binary_paths:
            return [], [], "no target file paths found in diff headers"

        return sorted(self.paths), sorted(self.binary_paths), None


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

    git_diff_parser = GitDiffParser(unified_diff)
    touched, binary_paths, parse_error = git_diff_parser.parse()
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
