"""Build bounded agent failure payloads from trigger results and sandbox files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from getworktree.core.loops.models import LoopContextInclude
from getworktree.core.loops.trigger import TriggerRunResult

DEFAULT_MAX_TRIGGER_CHARS = 20_000
DEFAULT_MAX_FILE_BYTES = 64_000
DEFAULT_MAX_FILES = 20

# Prefer pytest-style failure lines when selecting relevant_source files.
_PYTEST_NODE_RE = re.compile(
    r"^(?:FAILED|ERROR)\s+(?P<path>(?:[A-Za-z]:)?(?:(?:\.\.?/)|/)?(?:[\w.-]+/)*[\w.-]+\.py)"
    r"(?:::[^\s]+)?",
    re.MULTILINE,
)
_PYTEST_FILE_LINE_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?(?:(?:\.\.?/)|/)?(?:[\w.-]+/)*[\w.-]+\.py):\d+"
)

_SOURCE_SUFFIXES = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".md",
)
_PATH_CANDIDATE_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?(?:(?:\.\.?/)|/)?(?:[\w.-]+/)*[\w.-]+"
    r"(?:" + "|".join(re.escape(s) for s in _SOURCE_SUFFIXES) + r"))"
)
_BINARY_SNIFF_BYTES = 8 * 1024

OmissionReason = Literal[
    "missing",
    "outside_sandbox",
    "directory",
    "binary",
    "max_files",
    "max_file_bytes",
]


class PayloadOmission(BaseModel):
    """Record of a candidate path that was not included in the payload."""

    model_config = {"extra": "forbid", "strict": True}

    path: str
    reason: OmissionReason


class PayloadFile(BaseModel):
    """Sandbox-relative source file content attached to a failure payload."""

    model_config = {"extra": "forbid", "strict": True}

    path: str
    content: str
    truncated: bool = False


class AgentFailurePayload(BaseModel):
    """Bounded context package for an agent fix request."""

    model_config = {"extra": "forbid", "strict": True}

    command: str
    args: list[str]
    trigger_status: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    changed_files: list[str] = Field(default_factory=list)
    files: list[PayloadFile] = Field(default_factory=list)
    omissions: list[PayloadOmission] = Field(default_factory=list)


def _truncate_text(
    text: str,
    max_chars: int,
    *,
    keep: Literal["head", "tail"] = "tail",
) -> tuple[str, bool]:
    """Truncate ``text`` to ``max_chars`` and mark when shortened.

    Defaults to keeping the *tail* because failure details (e.g. pytest
    summaries and traces) usually appear at the end of trigger output.
    """
    if max_chars < 1:
        marker = f"...[truncated, original_chars={len(text)}]\n"
        return marker, True
    if len(text) <= max_chars:
        return text, False
    marker = f"...[truncated, original_chars={len(text)}]\n"
    if keep == "head":
        body = text[:max_chars]
        return body + "\n" + marker.rstrip("\n"), True
    body = text[-max_chars:]
    return marker + body, True


def _extract_path_candidates(text: str) -> list[str]:
    """Return path-like tokens with known source suffixes from free text."""
    if not text:
        return []
    return [match.group("path") for match in _PATH_CANDIDATE_RE.finditer(text)]


def _extract_failing_test_files(*streams: str) -> list[str]:
    """Return ordered unique test file paths inferred from failure output.

    Prefers explicit pytest ``FAILED`` / ``ERROR`` node lines, then falls back
    to ``file.py:line`` markers. Does not use generic path scraping.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        path = _posix_rel(raw.strip())
        if not path or path in seen:
            return
        seen.add(path)
        ordered.append(path)

    joined = "\n".join(stream for stream in streams if stream)
    if not joined:
        return []

    for match in _PYTEST_NODE_RE.finditer(joined):
        _add(match.group("path"))
    if ordered:
        return ordered

    for match in _PYTEST_FILE_LINE_RE.finditer(joined):
        _add(match.group("path"))
    return ordered


def _posix_rel(path: str) -> str:
    return path.replace("\\", "/")


def _try_sandbox_relative(
    raw: str, sandbox_root: Path
) -> tuple[str | None, str | None]:
    """Map a candidate path into a sandbox-relative posix path.

    Returns:
        (relative_path, omission_reason). Exactly one side is set.
    """
    candidate = Path(raw)
    try:
        sandbox_resolved = sandbox_root.resolve()
    except OSError:
        return None, "missing"

    if not sandbox_resolved.is_dir():
        return None, "missing"

    # Absolute (or drive-rooted) paths: resolve and require under sandbox.
    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
        except OSError:
            return None, "missing"
        try:
            rel = resolved.relative_to(sandbox_resolved)
        except ValueError:
            return None, "outside_sandbox"
        return _posix_rel(rel.as_posix()), None

    # Relative paths are interpreted against the sandbox root.
    joined = sandbox_resolved / candidate
    try:
        resolved = joined.resolve()
    except OSError:
        return None, "missing"
    try:
        rel = resolved.relative_to(sandbox_resolved)
    except ValueError:
        return None, "outside_sandbox"
    return _posix_rel(rel.as_posix()), None


def _is_binary_bytes(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _read_payload_file(
    *,
    rel_path: str,
    sandbox_root: Path,
    max_file_bytes: int,
) -> tuple[PayloadFile | None, PayloadOmission | None]:
    """Read one sandbox file with size/binary guards."""
    try:
        sandbox_resolved = sandbox_root.resolve()
    except OSError:
        return None, PayloadOmission(path=rel_path, reason="missing")

    absolute = (sandbox_resolved / rel_path).resolve()
    try:
        absolute.relative_to(sandbox_resolved)
    except ValueError:
        return None, PayloadOmission(path=rel_path, reason="outside_sandbox")

    if not absolute.exists():
        return None, PayloadOmission(path=rel_path, reason="missing")
    if absolute.is_dir():
        return None, PayloadOmission(path=rel_path, reason="directory")
    if not absolute.is_file():
        return None, PayloadOmission(path=rel_path, reason="missing")

    try:
        with open(absolute, "rb") as handle:
            sample = handle.read(_BINARY_SNIFF_BYTES)
            if _is_binary_bytes(sample):
                return None, PayloadOmission(path=rel_path, reason="binary")
            rest = handle.read() if len(sample) == _BINARY_SNIFF_BYTES else b""
            data = sample + rest
    except OSError:
        return None, PayloadOmission(path=rel_path, reason="missing")

    truncated = False
    if len(data) > max_file_bytes:
        data = data[:max_file_bytes]
        truncated = True

    content = data.decode("utf-8", errors="replace")
    return (
        PayloadFile(path=rel_path, content=content, truncated=truncated),
        None,
    )


def build_failure_payload(
    *,
    trigger: TriggerRunResult,
    sandbox_path: Path,
    include: list[LoopContextInclude],
    changed_files: list[str] | None = None,
    max_trigger_chars: int = DEFAULT_MAX_TRIGGER_CHARS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> AgentFailurePayload:
    """Build a structured, size-bounded failure payload for agent adapters.

    Never raises for missing optional files; skips are recorded in ``omissions``.
    Does not mutate the sandbox or git state.

    Args:
        trigger: Structured trigger run result (any status).
        sandbox_path: Sandbox root used to resolve and bound file reads.
        include: Loop context include tokens to attach.
        changed_files: Caller-supplied repo/sandbox-relative paths.
        max_trigger_chars: Max characters kept per trigger stream.
        max_file_bytes: Max bytes read per source file.
        max_files: Max number of source files attached for ``relevant_source``.

    Returns:
        Populated ``AgentFailurePayload``.
    """
    include_set = set(include)
    caller_changed = list(changed_files) if changed_files is not None else []

    stdout: str | None = None
    stderr: str | None = None
    stdout_truncated = False
    stderr_truncated = False
    if "trigger_output" in include_set:
        stdout, stdout_truncated = _truncate_text(trigger.stdout, max_trigger_chars)
        stderr, stderr_truncated = _truncate_text(trigger.stderr, max_trigger_chars)

    payload_changed: list[str] = []
    if "changed_files" in include_set:
        payload_changed = list(caller_changed)

    files: list[PayloadFile] = []
    omissions: list[PayloadOmission] = []

    if "relevant_source" in include_set:
        # Prefer focused failing-test files when the trigger output identifies
        # them (common pytest case). A single failing test file becomes the
        # only source attachment. Fall back to broad path scraping + changed
        # files when no failing test path can be inferred.
        failing_tests = _extract_failing_test_files(trigger.stdout, trigger.stderr)
        raw_candidates: list[str] = []
        if failing_tests:
            raw_candidates.extend(failing_tests)
        else:
            raw_candidates.extend(_extract_path_candidates(trigger.stdout))
            raw_candidates.extend(_extract_path_candidates(trigger.stderr))
            raw_candidates.extend(caller_changed)

        rel_order: list[str] = []
        seen_rel: set[str] = set()
        seen_fail_keys: set[tuple[str, str]] = set()

        for raw in raw_candidates:
            rel, fail_reason = _try_sandbox_relative(raw, sandbox_path)
            if fail_reason is not None:
                key = (_posix_rel(raw), fail_reason)
                if key not in seen_fail_keys:
                    seen_fail_keys.add(key)
                    omissions.append(
                        PayloadOmission(
                            path=_posix_rel(raw),
                            reason=fail_reason,  # type: ignore[arg-type]
                        )
                    )
                continue
            assert rel is not None
            if rel in seen_rel:
                continue
            seen_rel.add(rel)
            rel_order.append(rel)

        rel_order.sort()

        for index, rel in enumerate(rel_order):
            if index >= max_files:
                omissions.append(PayloadOmission(path=rel, reason="max_files"))
                continue
            file_obj, omission = _read_payload_file(
                rel_path=rel,
                sandbox_root=sandbox_path,
                max_file_bytes=max_file_bytes,
            )
            if omission is not None:
                omissions.append(omission)
            if file_obj is not None:
                files.append(file_obj)

    return AgentFailurePayload(
        command=trigger.command,
        args=list(trigger.args),
        trigger_status=str(trigger.status),
        exit_code=trigger.exit_code,
        timed_out=trigger.timed_out,
        duration_ms=trigger.duration_ms,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        changed_files=payload_changed,
        files=files,
        omissions=omissions,
    )
