"""Tier 2 presentation contracts for WorktreeStatusFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, make_status_result, render_rich
from worktree.cli.ui.formatters.status import (
    StatusHealth,
    StatusView,
    WorktreeStatusFormatter,
)
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import AgentConfig, ProjectConfig, WorktreeConfig
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    GitStatusInfo,
    WorktreeStatusResult,
)

ROOT = Path("/workspace/my-repo")
CONFIG_PATH = ROOT / ".worktree" / "config.json"

HEALTHY = FormatterCase(
    data=make_status_result(root_dir=ROOT),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

UNINITIALIZED_NON_GIT = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        is_initialized=False,
        git=GitStatusInfo(is_git_repo=False, branch="none", is_dirty=False, uncommitted_files=0),
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
        ),
        warnings=["Worktree workspace is not initialized. Run 'wt init' to configure."],
        fixes=[
            "Run 'wt init' to initialize Worktree in this repository.",
            "Run 'git init' or navigate to a Git repository.",
        ],
    ),
    view=StatusView(
        health=StatusHealth.UNINITIALIZED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.NOT_FOUND,
        config_path_relative=".worktree/config.json",
        git_branch=None,
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Worktree workspace is not initialized. Run 'wt init' to configure."],
        remediations=[
            "Run 'wt init' to initialize Worktree in this repository.",
            "Run 'git init' or navigate to a Git repository.",
        ],
    ),
)

DEGRADED_SCHEMA_INVALID = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
            errors=["Invalid value at 'agent.model': expected string"],
        ),
        warnings=["Invalid value: expected string"],
        fixes=["Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.SCHEMA_INVALID,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Invalid value: expected string"],
        remediations=[
            "Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys."
        ],
    ),
)

DEGRADED_MALFORMED_JSON = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.MALFORMED_JSON,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
            errors=["Malformed config.json: Expecting property name"],
        ),
        warnings=["Malformed config.json"],
        fixes=["Repair JSON syntax in .worktree/config.json or restore from backup."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.MALFORMED_JSON,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Malformed config.json"],
        remediations=["Repair JSON syntax in .worktree/config.json or restore from backup."],
    ),
)

DEGRADED_ROOT_NOT_OBJECT = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.ROOT_NOT_OBJECT,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
            errors=["Malformed config.json: root must be an object"],
        ),
        warnings=["Malformed config.json: root must be an object"],
        fixes=["Ensure .worktree/config.json contains a JSON object root."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.ROOT_NOT_OBJECT,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Malformed config.json: root must be an object"],
        remediations=["Ensure .worktree/config.json contains a JSON object root."],
    ),
)

DEGRADED_PATH_IS_DIRECTORY = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.PATH_IS_DIRECTORY,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
            errors=["Config path is a directory, not a file"],
        ),
        warnings=["Config path is a directory, not a file"],
        fixes=["Remove directory at .worktree/config.json and run 'wt init'."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.PATH_IS_DIRECTORY,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Config path is a directory, not a file"],
        remediations=["Remove directory at .worktree/config.json and run 'wt init'."],
    ),
)

DEGRADED_UNREADABLE = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.UNREADABLE,
            config_path=CONFIG_PATH,
            is_valid=False,
            config=None,
            errors=["Unable to read config.json: Permission denied"],
        ),
        warnings=["Unable to read config.json: Permission denied"],
        fixes=["Check file permissions for .worktree/config.json."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.UNREADABLE,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Unable to read config.json: Permission denied"],
        remediations=["Check file permissions for .worktree/config.json."],
    ),
)

DIRTY_BRANCH = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        git=GitStatusInfo(is_git_repo=True, branch="feature/dirty-branch", is_dirty=True, uncommitted_files=3),
    ),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/dirty-branch",
        git_is_dirty=True,
        uncommitted_files=3,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

NOT_A_GIT_REPO = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        git=GitStatusInfo(is_git_repo=False, branch="none", is_dirty=False, uncommitted_files=0),
        fixes=["Run 'git init' or navigate to a Git repository."],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch=None,
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=["Run 'git init' or navigate to a Git repository."],
    ),
)

UNNAMED_PROJECT = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=CONFIG_PATH,
            is_valid=True,
            config=WorktreeConfig(
                version=1,
                project=ProjectConfig(name=""),
                agent=AgentConfig(model="gemini-2.5-flash"),
            ),
        ),
    ),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name=None,
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

AGENT_MODEL_UNSET = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=CONFIG_PATH,
            is_valid=True,
            config=WorktreeConfig(
                version=1,
                project=ProjectConfig(name="worktree-cli"),
                agent=AgentConfig(model=None),
            ),
        ),
    ),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

EMPTY_CATALOG = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        catalog=CatalogStatusInfo(
            exists=False,
            catalog_dir=ROOT / ".worktree" / "catalog",
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        ),
    ),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=0,
        total_catalog_items=0,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

INVALID_CATALOG_ITEMS = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        catalog=CatalogStatusInfo(
            exists=True,
            catalog_dir=ROOT / ".worktree" / "catalog",
            total_items=5,
            workflows_count=2,
            tasks_count=2,
            steps_count=1,
            invalid_items=2,
            item_names=["w1", "w2", "t1", "t2", "s1"],
        ),
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=3,
        total_catalog_items=5,
        total_runs=1,
        errors=[],
        warnings=[],
        remediations=[],
    ),
)

WITH_WARNINGS_AND_FIXES = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        warnings=["max_active_sandboxes (10) is unusually high."],
        fixes=["Reduce max_active_sandboxes in .worktree/config.json."],
    ),
    view=StatusView(
        health=StatusHealth.OK,
        root_dir=ROOT,
        project_name="worktree-cli",
        config_status=ConfigLoadStatus.OK,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model="gemini-2.5-flash",
        active_sandboxes=1,
        max_active_sandboxes=5,
        valid_catalog_items=2,
        total_catalog_items=2,
        total_runs=1,
        errors=[],
        warnings=["max_active_sandboxes (10) is unusually high."],
        remediations=["Reduce max_active_sandboxes in .worktree/config.json."],
    ),
)

DEGRADED_RAW_CONFIG_PROJECT = FormatterCase(
    data=make_status_result(
        root_dir=ROOT,
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=CONFIG_PATH,
            is_valid=False,
            raw={"project": {"name": "raw-project"}},
            config=None,
            errors=["Invalid schema"],
        ),
        warnings=["Invalid schema"],
        fixes=["Fix schema errors"],
    ),
    view=StatusView(
        health=StatusHealth.DEGRADED,
        root_dir=ROOT,
        project_name="raw-project",
        config_status=ConfigLoadStatus.SCHEMA_INVALID,
        config_path_relative=".worktree/config.json",
        git_branch="feature/status-cmd",
        git_is_dirty=False,
        uncommitted_files=0,
        agent_model=None,
        active_sandboxes=None,
        max_active_sandboxes=None,
        valid_catalog_items=None,
        total_catalog_items=None,
        total_runs=1,
        errors=[],
        warnings=["Invalid schema"],
        remediations=["Fix schema errors"],
    ),
)

STATUS_CASES = [
    pytest.param(HEALTHY, id="healthy_workspace"),
    pytest.param(UNINITIALIZED_NON_GIT, id="uninitialized_non_git"),
    pytest.param(DEGRADED_SCHEMA_INVALID, id="degraded_schema_invalid"),
    pytest.param(DEGRADED_MALFORMED_JSON, id="degraded_malformed_json"),
    pytest.param(DEGRADED_ROOT_NOT_OBJECT, id="degraded_root_not_object"),
    pytest.param(DEGRADED_PATH_IS_DIRECTORY, id="degraded_path_is_directory"),
    pytest.param(DEGRADED_UNREADABLE, id="degraded_unreadable"),
    pytest.param(DIRTY_BRANCH, id="dirty_branch"),
    pytest.param(NOT_A_GIT_REPO, id="not_a_git_repo"),
    pytest.param(UNNAMED_PROJECT, id="unnamed_project"),
    pytest.param(AGENT_MODEL_UNSET, id="agent_model_unset"),
    pytest.param(EMPTY_CATALOG, id="empty_catalog"),
    pytest.param(INVALID_CATALOG_ITEMS, id="invalid_catalog_items"),
    pytest.param(WITH_WARNINGS_AND_FIXES, id="with_warnings_and_fixes"),
    pytest.param(DEGRADED_RAW_CONFIG_PROJECT, id="degraded_raw_config_project"),
]

STATUS_PAYLOAD_CASES = [
    pytest.param(
        HEALTHY,
        {
            "health": "ok",
            "root_dir": "/workspace/my-repo",
            "project_name": "worktree-cli",
            "config_status": "ok",
            "config_path_relative": ".worktree/config.json",
            "git_branch": "feature/status-cmd",
            "git_is_dirty": False,
            "uncommitted_files": 0,
            "agent_model": "gemini-2.5-flash",
            "active_sandboxes": 1,
            "max_active_sandboxes": 5,
            "valid_catalog_items": 2,
            "total_catalog_items": 2,
            "total_runs": 1,
            "errors": [],
            "warnings": [],
            "remediations": [],
        },
        id="healthy_workspace",
    ),
    pytest.param(
        UNINITIALIZED_NON_GIT,
        {
            "health": "uninitialized",
            "root_dir": "/workspace/my-repo",
            "project_name": None,
            "config_status": "not_found",
            "config_path_relative": ".worktree/config.json",
            "git_branch": None,
            "git_is_dirty": False,
            "uncommitted_files": 0,
            "agent_model": None,
            "active_sandboxes": None,
            "max_active_sandboxes": None,
            "valid_catalog_items": None,
            "total_catalog_items": None,
            "total_runs": 1,
            "errors": [],
            "warnings": ["Worktree workspace is not initialized. Run 'wt init' to configure."],
            "remediations": [
                "Run 'wt init' to initialize Worktree in this repository.",
                "Run 'git init' or navigate to a Git repository.",
            ],
        },
        id="uninitialized_non_git",
    ),
]


class WorktreeStatusFormatterTests:
    @pytest.mark.parametrize("case", STATUS_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[WorktreeStatusResult, StatusView]) -> None:
        """Verify transform derives the exact StatusView model representation."""
        assert WorktreeStatusFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), STATUS_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WorktreeStatusResult, StatusView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert WorktreeStatusFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", STATUS_CASES)
    def test_rich_render_shows_every_view_value(self, case: FormatterCase[WorktreeStatusResult, StatusView]) -> None:
        """Verify that all non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(WorktreeStatusFormatter().to_rich(case.data))
        view = case.view

        if view.project_name is not None:
            assert view.project_name in rendered
        if view.git_branch is not None:
            assert view.git_branch in rendered
        if view.agent_model is not None:
            assert view.agent_model in rendered
        if view.active_sandboxes is not None:
            assert str(view.active_sandboxes) in rendered
            assert str(view.max_active_sandboxes) in rendered
        if view.valid_catalog_items is not None:
            assert str(view.valid_catalog_items) in rendered
            assert str(view.total_catalog_items) in rendered
        for warning in view.warnings:
            assert warning in rendered
        for remediation in view.remediations:
            assert remediation in rendered
