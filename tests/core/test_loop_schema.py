from __future__ import annotations

from getworktree.core.loop_schema import validate_loop_v1


def test_validate_loop_v1_accepts_starter_template() -> None:
    loop_obj = {
        "version": 1,
        "name": "fix-tests",
        "description": "Iteratively fix failing tests until they pass or attempts are exhausted",
        "trigger": {
            "command": "pytest",
            "args": [],
            "timeout_seconds": 600,
        },
        "agent": {
            "provider": "local",
            "mode": "fix_failure",
            "timeout_seconds": 120,
        },
        "iteration": {
            "max_attempts": 5,
            "stop_when": ["trigger_passes", "unfixable", "user_abort"],
        },
        "sandbox": {
            "auto_clean": True,
            "keep_on_failure": True,
        },
        "approval": {
            "require_before_apply": True,
        },
        "context": {
            "include": ["trigger_output", "changed_files", "relevant_source"],
        },
        "patch": {
            "strategy": "unified_diff",
            "max_files": 30,
            "max_patch_kb": 1024,
        },
    }

    result = validate_loop_v1(loop_obj)

    assert result.ok
    assert result.errors == []


def test_validate_loop_v1_reports_readable_errors() -> None:
    invalid_loop = {
        "version": 1,
        "description": "missing name",
        "trigger": {
            "command": "pytest",
            "args": [],
            "timeout_seconds": 600,
        },
        "agent": {
            "provider": "local",
            "mode": "fix_failure",
            "timeout_seconds": 120,
        },
        "iteration": {
            "max_attempts": 5,
            "stop_when": ["trigger_passes"],
        },
        "sandbox": {
            "auto_clean": True,
            "keep_on_failure": True,
        },
        "approval": {
            "require_before_apply": True,
        },
        "context": {
            "include": ["trigger_output"],
        },
        "patch": {
            "strategy": "unified_diff",
            "max_files": 30,
            "max_patch_kb": 1024,
        },
    }

    result = validate_loop_v1(invalid_loop)

    assert not result.ok
    assert any("name" in error for error in result.errors)
