"""Tier 2 presentation contract tests for WorkspaceInitFormatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FormatterCase, render_rich
from worktree.cli.ui.formatters.init import (
    WorkspaceInitFormatter,
    WorkspaceInitView,
)
from worktree.core.bootstrap.models import (
    BootstrapOutcome,
    BootstrapResult,
    InitFailureMode,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import SeedResult
from worktree.core.config.generator import ConfigGenerationResult

ROOT = Path("/workspace/my-repo")
WORKTREE = ROOT / ".worktree"
CONFIG_PATH = WORKTREE / "config.json"


def make_init_view(**overrides: Any) -> WorkspaceInitView:
    """Helper to construct a WorkspaceInitView with baseline initialized defaults."""
    defaults: dict[str, Any] = {
        "ok": True,
        "root_path": WORKTREE,
        "root_path_relative": ".worktree",
        "bootstrap_outcome": BootstrapOutcome.INITIALIZED,
        "dirs_created": [".worktree/sessions"],
        "config_created": True,
        "config_overwritten": False,
        "config_repaired": False,
        "config_skipped_existing": False,
        "config_path_relative": ".worktree/config.json",
        "inserted_keys": [],
        "seeded_files": [".worktree/workflows/test.yml"],
        "skipped_seed_files": [],
        "overwritten_seed_files": [],
        "failure_mode": None,
        "errors": [],
        "warnings": [],
        "fixes": [],
    }
    defaults.update(overrides)
    return WorkspaceInitView(**defaults)


INITIALIZED = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            root_created=True,
            dirs_created=[WORKTREE / "sessions"],
        ),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            created=True,
        ),
        seed_result=SeedResult(
            created_files=[WORKTREE / "workflows" / "test.yml"],
        ),
    ),
    view=make_init_view(),
)

REPAIRED = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            repaired=True,
            dirs_created=[WORKTREE / "sessions"],
        ),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            repaired=True,
            inserted_keys=["telemetry.enabled"],
        ),
        seed_result=SeedResult(
            skipped_existing_files=[WORKTREE / "workflows" / "fix-tests.yml"],
        ),
    ),
    view=make_init_view(
        bootstrap_outcome=BootstrapOutcome.REPAIRED,
        config_created=False,
        config_repaired=True,
        inserted_keys=["telemetry.enabled"],
        seeded_files=[],
        skipped_seed_files=[".worktree/workflows/fix-tests.yml"],
    ),
)

ALREADY_INITIALIZED_OVERWRITTEN = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            outcome=BootstrapOutcome.ALREADY_INITIALIZED,
            dirs_created=[],
        ),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            overwritten=True,
        ),
        seed_result=SeedResult(
            overwritten_files=[WORKTREE / "workflows" / "x.yml"],
        ),
    ),
    view=make_init_view(
        bootstrap_outcome=BootstrapOutcome.ALREADY_INITIALIZED,
        dirs_created=[],
        config_created=False,
        config_overwritten=True,
        seeded_files=[],
        overwritten_seed_files=[".worktree/workflows/x.yml"],
    ),
)

CONFIG_SKIPPED_EXISTING = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            outcome=BootstrapOutcome.INITIALIZED,
            dirs_created=[],
        ),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            skipped_existing=True,
        ),
        seed_result=SeedResult(),
    ),
    view=make_init_view(
        dirs_created=[],
        config_created=False,
        config_skipped_existing=True,
        seeded_files=[],
    ),
)

NO_CONFIG_PATH = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            outcome=BootstrapOutcome.INITIALIZED,
            dirs_created=[],
        ),
        config_result=ConfigGenerationResult(config_path=None),
        seed_result=SeedResult(),
    ),
    view=make_init_view(
        dirs_created=[],
        config_created=False,
        config_path_relative=None,
        seeded_files=[],
    ),
)

SEEDING_ERROR = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=WORKTREE),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            created=True,
        ),
        seed_result=SeedResult(errors=["could not seed"]),
    ),
    view=make_init_view(
        ok=False,
        bootstrap_outcome=BootstrapOutcome.ALREADY_INITIALIZED,
        dirs_created=[],
        seeded_files=[],
        errors=["could not seed"],
    ),
)

PREFLIGHT_FAILURE = FormatterCase(
    data=WorkspaceInitResult(
        errors=["The current directory is not a valid Git repository."],
        fixes=["Run 'git init' before running 'wt init'."],
        failure_mode=InitFailureMode.PREFLIGHT,
    ),
    view=make_init_view(
        ok=False,
        root_path=None,
        root_path_relative=None,
        bootstrap_outcome=None,
        dirs_created=[],
        config_created=False,
        config_path_relative=None,
        seeded_files=[],
        failure_mode=InitFailureMode.PREFLIGHT,
        errors=["The current directory is not a valid Git repository."],
        fixes=["Run 'git init' before running 'wt init'."],
    ),
)

BOOTSTRAP_FAILURE = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(
            root_path=WORKTREE,
            errors=["path conflict: .worktree is a file"],
            fixes=["Remove the conflicting file."],
        ),
        errors=["path conflict: .worktree is a file"],
        fixes=["Remove the conflicting file."],
        failure_mode=InitFailureMode.BOOTSTRAP,
    ),
    view=make_init_view(
        ok=False,
        bootstrap_outcome=BootstrapOutcome.FAILED,
        dirs_created=[],
        config_created=False,
        config_path_relative=None,
        seeded_files=[],
        failure_mode=InitFailureMode.BOOTSTRAP,
        errors=["path conflict: .worktree is a file"],
        fixes=["Remove the conflicting file."],
    ),
)

CONFIG_GENERATION_FAILURE = FormatterCase(
    data=WorkspaceInitResult(
        bootstrap_result=BootstrapResult(root_path=WORKTREE),
        config_result=ConfigGenerationResult(
            config_path=CONFIG_PATH,
            errors=["CONFIG_WRITE_FAILED: permission denied"],
            fixes=["Check file permissions for .worktree/config.json."],
        ),
        errors=["CONFIG_WRITE_FAILED: permission denied"],
        fixes=["Check file permissions for .worktree/config.json."],
        failure_mode=InitFailureMode.CONFIG_GENERATION,
    ),
    view=make_init_view(
        ok=False,
        bootstrap_outcome=BootstrapOutcome.ALREADY_INITIALIZED,
        dirs_created=[],
        config_created=False,
        config_path_relative=".worktree/config.json",
        seeded_files=[],
        failure_mode=InitFailureMode.CONFIG_GENERATION,
        errors=["CONFIG_WRITE_FAILED: permission denied"],
        fixes=["Check file permissions for .worktree/config.json."],
    ),
)

INIT_CASES = [
    pytest.param(INITIALIZED, id="initialized"),
    pytest.param(REPAIRED, id="repaired"),
    pytest.param(ALREADY_INITIALIZED_OVERWRITTEN, id="already_initialized_overwritten"),
    pytest.param(CONFIG_SKIPPED_EXISTING, id="config_skipped_existing"),
    pytest.param(NO_CONFIG_PATH, id="no_config_path"),
    pytest.param(SEEDING_ERROR, id="seeding_error"),
    pytest.param(PREFLIGHT_FAILURE, id="preflight_failure"),
    pytest.param(BOOTSTRAP_FAILURE, id="bootstrap_failure"),
    pytest.param(CONFIG_GENERATION_FAILURE, id="config_generation_failure"),
]

INIT_PAYLOAD_CASES = [
    pytest.param(
        INITIALIZED,
        {
            "ok": True,
            "root_path": "/workspace/my-repo/.worktree",
            "root_path_relative": ".worktree",
            "bootstrap_outcome": "initialized",
            "dirs_created": [".worktree/sessions"],
            "config_created": True,
            "config_overwritten": False,
            "config_repaired": False,
            "config_skipped_existing": False,
            "config_path_relative": ".worktree/config.json",
            "inserted_keys": [],
            "seeded_files": [".worktree/workflows/test.yml"],
            "skipped_seed_files": [],
            "overwritten_seed_files": [],
            "failure_mode": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="initialized_payload",
    ),
    pytest.param(
        REPAIRED,
        {
            "ok": True,
            "root_path": "/workspace/my-repo/.worktree",
            "root_path_relative": ".worktree",
            "bootstrap_outcome": "repaired",
            "dirs_created": [".worktree/sessions"],
            "config_created": False,
            "config_overwritten": False,
            "config_repaired": True,
            "config_skipped_existing": False,
            "config_path_relative": ".worktree/config.json",
            "inserted_keys": ["telemetry.enabled"],
            "seeded_files": [],
            "skipped_seed_files": [".worktree/workflows/fix-tests.yml"],
            "overwritten_seed_files": [],
            "failure_mode": None,
            "errors": [],
            "warnings": [],
            "fixes": [],
        },
        id="repaired_payload",
    ),
    pytest.param(
        PREFLIGHT_FAILURE,
        {
            "ok": False,
            "root_path": None,
            "root_path_relative": None,
            "bootstrap_outcome": None,
            "dirs_created": [],
            "config_created": False,
            "config_overwritten": False,
            "config_repaired": False,
            "config_skipped_existing": False,
            "config_path_relative": None,
            "inserted_keys": [],
            "seeded_files": [],
            "skipped_seed_files": [],
            "overwritten_seed_files": [],
            "failure_mode": "preflight",
            "errors": ["The current directory is not a valid Git repository."],
            "warnings": [],
            "fixes": ["Run 'git init' before running 'wt init'."],
        },
        id="preflight_failure_payload",
    ),
]


def _assert_view_collections_in_rendered(view: WorkspaceInitView, rendered: str) -> None:
    """Assert all path and key collections in the view appear in rendered output."""
    items = view.dirs_created + view.inserted_keys + view.seeded_files + view.skipped_seed_files
    for item in items:
        assert item in rendered


def _assert_success_view_values_in_rendered(view: WorkspaceInitView, rendered: str) -> None:
    """Assert non-null success view values appear in rendered output."""
    if view.root_path_relative is not None:
        assert view.root_path_relative in rendered
    if view.config_path_relative is not None:
        assert view.config_path_relative in rendered
    _assert_view_collections_in_rendered(view, rendered)


def _assert_messages_in_rendered(messages: list[str], rendered: str) -> None:
    """Assert all messages in a list appear in rendered output."""
    for message in messages:
        assert message in rendered


class WorkspaceInitFormatterTests:
    """Tier 2 presentation contract tests for WorkspaceInitFormatter."""

    @pytest.mark.parametrize("case", INIT_CASES)
    def test_transform_derives_expected_view(self, case: FormatterCase[WorkspaceInitResult, WorkspaceInitView]) -> None:
        """Verify transform derives the exact WorkspaceInitView model representation."""
        assert WorkspaceInitFormatter().transform(case.data) == case.view

    @pytest.mark.parametrize(("case", "expected_payload"), INIT_PAYLOAD_CASES)
    def test_json_payload_matches_published_shape(
        self,
        case: FormatterCase[WorkspaceInitResult, WorkspaceInitView],
        expected_payload: dict[str, Any],
    ) -> None:
        """Verify to_json_serializable matches the exact published wire-format literal dict."""
        assert WorkspaceInitFormatter().to_json_serializable(case.data) == expected_payload

    @pytest.mark.parametrize("case", INIT_CASES)
    def test_rich_render_shows_every_view_value(
        self, case: FormatterCase[WorkspaceInitResult, WorkspaceInitView]
    ) -> None:
        """Verify that non-null semantic view model values reach the Rich renderable output."""
        rendered = render_rich(WorkspaceInitFormatter().to_rich(case.data))
        view = case.view

        if view.failure_mode is None:
            _assert_success_view_values_in_rendered(view, rendered)

        _assert_messages_in_rendered(view.errors, rendered)
        _assert_messages_in_rendered(view.fixes, rendered)
