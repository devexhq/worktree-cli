"""Tests for sandbox unified-diff patch apply engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from getworktree.core.workflows.patch import (
    PatchApplyResult,
    PatchApplyStatus,
    apply_patch_result,
    summarize_unified_diff,
)


def _mod_diff(
    *,
    old: str = "print('old')\n",
    new: str = "print('new')\n",
    path: str = "pkg/mod.py",
) -> str:
    """Build a simple single-hunk unified diff for a one-line file rewrite."""
    old_body = old if old.endswith("\n") else old + "\n"
    new_body = new if new.endswith("\n") else new + "\n"
    old_lines = old_body.splitlines(keepends=True)
    new_lines = new_body.splitlines(keepends=True)
    minus = "".join(f"-{line}" if line.endswith("\n") else f"-{line}\n" for line in old_lines)
    plus = "".join(f"+{line}" if line.endswith("\n") else f"+{line}\n" for line in new_lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@\n"
        f"{minus}{plus}"
    )


def _new_file_diff(path: str = "pkg/new.py", content: str = "x = 1\n") -> str:
    body = content if content.endswith("\n") else content + "\n"
    lines = body.splitlines(keepends=True)
    plus = "".join(f"+{line}" if line.endswith("\n") else f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{plus}"
    )


def _multi_file_diff(paths: list[str], content: str = "line\n") -> str:
    chunks: list[str] = []
    for path in paths:
        chunks.append(_new_file_diff(path=path, content=content))
    return "".join(chunks)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text("print('old')\n", encoding="utf-8")
    return root


def _apply(
    sandbox: Path,
    diff: str,
    *,
    max_files: int = 30,
    max_patch_kb: int = 1024,
    reject_binary_changes: bool = True,
    check_only: bool = False,
) -> PatchApplyResult:
    return apply_patch_result(
        sandbox_path=sandbox,
        unified_diff=diff,
        max_files=max_files,
        max_patch_kb=max_patch_kb,
        reject_binary_changes=reject_binary_changes,
        check_only=check_only,
    )


class PatchApplyResultModelTests:
    """Shape and ok property for PatchApplyResult."""

    def test_ok_for_applied_and_checked(self) -> None:
        assert PatchApplyResult(status=PatchApplyStatus.APPLIED).ok is True
        assert PatchApplyResult(status=PatchApplyStatus.CHECKED_OK).ok is True
        assert PatchApplyResult(status=PatchApplyStatus.CONFLICT).ok is False
        assert PatchApplyResult(status=PatchApplyStatus.EMPTY_DIFF).ok is False

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            PatchApplyResult(status=PatchApplyStatus.APPLIED, extra=True)  # type: ignore[call-arg]


class ApplyPatchResultTests:
    """Unit tests covering all PatchApplyStatus outcomes."""

    def test_applied_success_updates_file_and_touched(self, sandbox: Path) -> None:
        diff = _mod_diff()
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.APPLIED
        assert result.ok is True
        assert result.errors == []
        assert result.touched_files == ["pkg/mod.py"]
        assert (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8") == "print('new')\n"

    def test_checked_ok_does_not_write(self, sandbox: Path) -> None:
        before = (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8")
        result = _apply(sandbox, _mod_diff(), check_only=True)
        assert result.status == PatchApplyStatus.CHECKED_OK
        assert result.ok is True
        assert result.touched_files == ["pkg/mod.py"]
        assert (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8") == before

    def test_empty_diff(self, sandbox: Path) -> None:
        for payload in ("", "   ", "\n\t\n"):
            result = _apply(sandbox, payload)
            assert result.status == PatchApplyStatus.EMPTY_DIFF
            assert result.ok is False
            assert result.touched_files == []
            assert any("empty" in e.lower() for e in result.errors)

    def test_too_large(self, sandbox: Path) -> None:
        diff = _mod_diff()
        # Force limit below actual utf-8 size.
        size_kb = max(1, (len(diff.encode("utf-8")) // 1024))
        # Use 0-effective by setting max to force exceed: max 1 byte via tiny kb
        # max_patch_kb=1 means 1024 bytes; craft oversized.
        big = "x" * 2048
        oversized = (
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1 +1 @@\n"
            f"-print('old')\n"
            f"+{big}\n"
        )
        assert len(oversized.encode("utf-8")) > 1024
        result = _apply(sandbox, oversized, max_patch_kb=1)
        assert result.status == PatchApplyStatus.TOO_LARGE
        assert result.ok is False
        assert any("max_patch_kb" in e for e in result.errors)
        # tree unchanged
        assert (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8") == "print('old')\n"
        _ = size_kb

    def test_too_many_files(self, sandbox: Path) -> None:
        paths = [f"f{i}.txt" for i in range(5)]
        diff = _multi_file_diff(paths)
        result = _apply(sandbox, diff, max_files=3)
        assert result.status == PatchApplyStatus.TOO_MANY_FILES
        assert result.ok is False
        assert any("max_files is 3" in e for e in result.errors)
        for path in paths:
            assert not (sandbox / path).exists()

    def test_binary_rejected_binary_files_differ(self, sandbox: Path) -> None:
        diff = "diff --git a/pkg/data.bin b/pkg/data.bin\nBinary files a/pkg/data.bin and b/pkg/data.bin differ\n"
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.BINARY_REJECTED
        assert result.ok is False
        assert "pkg/data.bin" in result.touched_files
        assert any("binary" in e.lower() for e in result.errors)

    def test_binary_rejected_git_binary_patch(self, sandbox: Path) -> None:
        diff = (
            "diff --git a/pkg/data.bin b/pkg/data.bin\n"
            "index 1234567..abcdef0 100644\n"
            "GIT binary patch\n"
            "literal 4\n"
            "Mc${NkU|L!+0000A\n"
            "\n"
        )
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.BINARY_REJECTED
        assert result.ok is False

    def test_binary_allowed_when_reject_false_still_may_conflict(self, sandbox: Path) -> None:
        # Without a real binary blob, git apply will fail → conflict, not binary.
        diff = "diff --git a/pkg/data.bin b/pkg/data.bin\nBinary files a/pkg/data.bin and b/pkg/data.bin differ\n"
        result = _apply(sandbox, diff, reject_binary_changes=False)
        assert result.status in {
            PatchApplyStatus.CONFLICT,
            PatchApplyStatus.APPLIED,
            PatchApplyStatus.CHECKED_OK,
        }
        assert result.status != PatchApplyStatus.BINARY_REJECTED

    def test_unsafe_path_parent_escape(self, sandbox: Path) -> None:
        diff = (
            "diff --git a/../escape.txt b/../escape.txt\n"
            "--- a/../escape.txt\n"
            "+++ b/../escape.txt\n"
            "@@ -0,0 +1 @@\n"
            "+pwned\n"
        )
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.UNSAFE_PATH
        assert result.ok is False
        assert any("escape" in e.lower() or ".." in e for e in result.errors)
        assert not (sandbox.parent / "escape.txt").exists()

    def test_unsafe_path_absolute(self, sandbox: Path) -> None:
        abs_diff = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-root\n+rootx\n"
        result = _apply(sandbox, abs_diff)
        assert result.status == PatchApplyStatus.UNSAFE_PATH
        assert result.ok is False

    def test_invalid_diff(self, sandbox: Path) -> None:
        result = _apply(sandbox, "this is not a patch at all")
        assert result.status == PatchApplyStatus.INVALID_DIFF
        assert result.ok is False
        assert result.touched_files == []

    def test_git_timeout_on_apply(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import getworktree.core.workflows.patch as patch_mod

        def _timeout(**_kwargs: object) -> tuple[bool, str, bool]:
            return False, "git apply timed out after 120s", True

        monkeypatch.setattr(patch_mod, "_run_git_apply", _timeout)
        result = _apply(sandbox, _mod_diff())
        assert result.status == PatchApplyStatus.GIT_TIMEOUT
        assert result.ok is False
        assert result.touched_files == ["pkg/mod.py"]
        assert any("PATCH_GIT_TIMEOUT" in e for e in result.errors)
        assert (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8") == "print('old')\n"

    def test_conflict_leaves_tree_unchanged(self, sandbox: Path) -> None:
        before = (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8")
        # Hunk context does not match file contents.
        diff = (
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1 +1 @@\n"
            "-print('NOPE')\n"
            "+print('new')\n"
        )
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.CONFLICT
        assert result.ok is False
        assert result.touched_files == ["pkg/mod.py"]
        assert (sandbox / "pkg" / "mod.py").read_text(encoding="utf-8") == before

    def test_sandbox_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        result = _apply(missing, _mod_diff())
        assert result.status == PatchApplyStatus.SANDBOX_MISSING
        assert result.ok is False
        assert any("Sandbox path" in e for e in result.errors)

    def test_new_file_hunk(self, sandbox: Path) -> None:
        result = _apply(sandbox, _new_file_diff(path="pkg/brand_new.py", content="ok\n"))
        assert result.status == PatchApplyStatus.APPLIED
        assert result.touched_files == ["pkg/brand_new.py"]
        assert (sandbox / "pkg" / "brand_new.py").read_text(encoding="utf-8") == "ok\n"

    def test_touched_files_sorted_unique(self, sandbox: Path) -> None:
        # Two-file create; ensure sorted order regardless of header order.
        diff = _multi_file_diff(["z_last.txt", "a_first.txt"])
        result = _apply(sandbox, diff)
        assert result.status == PatchApplyStatus.APPLIED
        assert result.touched_files == ["a_first.txt", "z_last.txt"]

    def test_never_raises_on_classified(self, sandbox: Path) -> None:
        cases = [
            "",
            "not a diff",
            _mod_diff(old="mismatch\n"),
            ("diff --git a/x.bin b/x.bin\nBinary files a/x.bin and b/x.bin differ\n"),
        ]
        for diff in cases:
            result = apply_patch_result(
                sandbox_path=sandbox,
                unified_diff=diff,
                max_files=30,
                max_patch_kb=1024,
            )
            assert isinstance(result, PatchApplyResult)


class SummarizeUnifiedDiffTests:
    def test_counts_files_and_line_stats(self) -> None:
        diff = _mod_diff(old="a\nb\n", new="a\nc\nd\n", path="pkg/mod.py")
        touched, additions, deletions = summarize_unified_diff(diff)
        assert touched == ["pkg/mod.py"]
        assert additions == 3
        assert deletions == 2

    def test_multi_file_sorted_unique(self) -> None:
        diff = _multi_file_diff(["z_last.txt", "a_first.txt"])
        touched, _, _ = summarize_unified_diff(diff)
        assert touched == ["a_first.txt", "z_last.txt"]

    def test_unparseable_diff_returns_empty_files(self) -> None:
        touched, additions, deletions = summarize_unified_diff("not a diff")
        assert touched == []
        assert additions == 0
        assert deletions == 0

    def test_empty_diff(self) -> None:
        assert summarize_unified_diff("") == ([], 0, 0)

    def test_header_lines_excluded_from_stats(self) -> None:
        diff = _mod_diff(old="x\n", new="y\n", path="pkg/mod.py")
        # Header lines start with "---"/"+++" and must not be counted as
        # content additions/deletions.
        assert "--- a/pkg/mod.py" in diff
        assert "+++ b/pkg/mod.py" in diff
        _, additions, deletions = summarize_unified_diff(diff)
        assert additions == 1
        assert deletions == 1
