from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from rich.text import Text

from tests.helpers import FileSystem, make_dispatcher_with_buffer
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.events import LockWaitEvent
from worktree.cli.ui.formatters.catalog import register_catalog_formatters
from worktree.cli.ui.formatters.config import (
    ConfigSetFormatter,
    ConfigShowFormatter,
    ConfigValidateFormatter,
    register_config_formatters,
)
from worktree.cli.ui.formatters.diff import (
    DiffResultFormatter,
    register_diff_formatters,
)
from worktree.cli.ui.formatters.events.lock_wait import LockWaitFormatter
from worktree.cli.ui.formatters.history import (
    HistoryListFormatter,
    HistoryShowFormatter,
    register_history_formatters,
)
from worktree.cli.ui.formatters.init import (
    InitOutcomeFormatter,
    WorkspaceInitFormatter,
    register_init_formatters,
)
from worktree.cli.ui.formatters.status import (
    WorktreeStatusFormatter,
    register_status_formatters,
)
from worktree.common.types import ComponentFormatter
from worktree.core.blueprint import BlueprintKind
from worktree.core.bootstrap import (
    BootstrapResult,
    WorkspaceInitResult,
)
from worktree.core.catalog.models import (
    CatalogCreateResult,
    CatalogDeleteResult,
    CatalogListResult,
    CatalogShowResult,
    SeedResult,
)
from worktree.core.config.generator import ConfigGenerationResult
from worktree.core.config.loader import ConfigLoadResult, ConfigLoadStatus
from worktree.core.config.models import (
    AgentConfig,
    ProjectConfig,
    WorktreeConfig,
)
from worktree.core.config.mutate import ConfigSetResult, ConfigSetStatus
from worktree.core.config.validate import (
    ConfigValidationResult,
    ConfigValidationStatus,
)
from worktree.core.db import (
    CatalogItemType,
    CatalogRecord,
    RunRecord,
    RunStatus,
)
from worktree.core.diff.models import DiffResult, DiffStatus
from worktree.core.history.models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    DatabaseStatusInfo,
    GitStatusInfo,
    SandboxStatusInfo,
    WorktreeStatusResult,
)

_SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass  # intentionally long line exceeding 120 characters to ensure diff raw output does not wrap at terminal columns boundaries
"""


class DummyItem(BaseModel):
    name: str
    count: int


@dataclass
class SimpleItem:
    value: str


class DummyItemFormatter(ComponentFormatter[DummyItem]):
    def to_rich(self, data: DummyItem) -> Text:
        style = self._STYLE_MAP.get("success", "green")
        return Text(f"Item: {data.name} ({data.count})", style=style)

    def to_json_serializable(self, data: DummyItem) -> dict[str, Any]:
        return data.model_dump(mode="json")


def test_dispatcher_direct_registration_instance() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()
    formatter = DummyItemFormatter()

    dispatcher.register(DummyItem, formatter)
    item = DummyItem(name="test", count=5)

    dispatcher.dispatch(item, output_format="terminal")
    assert "Item: test (5)" in buffer.getvalue()


def test_dispatcher_direct_registration_class() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()

    dispatcher.register(DummyItem, DummyItemFormatter)
    item = DummyItem(name="test2", count=10)

    dispatcher.dispatch(item, output_format="terminal")
    assert "Item: test2 (10)" in buffer.getvalue()


def test_dispatcher_decorator_registration() -> None:
    dispatcher, buffer = make_dispatcher_with_buffer()

    @dispatcher.register(SimpleItem)
    class DecItemFormatter(ComponentFormatter[SimpleItem]):
        def to_rich(self, data: SimpleItem) -> Text:
            return Text(f"Decorated: {data.value}")

        def to_json_serializable(self, data: SimpleItem) -> dict[str, Any]:
            return {"dec_value": data.value}

    item = SimpleItem(value="hello")
    dispatcher.dispatch(item, output_format="terminal")
    assert "Decorated: hello" in buffer.getvalue()


def test_dispatcher_json_ndjson_output(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    dispatcher.register(DummyItem, DummyItemFormatter())

    item = DummyItem(name="widget", count=42)
    dispatcher.dispatch(item, output_format="json")

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed == {
        "event_type": "DummyItem",
        "payload": {"name": "widget", "count": 42},
    }


def test_dispatcher_unregistered_type_raises() -> None:
    dispatcher = UiDispatcher()
    with pytest.raises(ValueError, match="No formatter registered for type: DummyItem"):
        dispatcher.dispatch(DummyItem(name="unregistered", count=0))


def test_dispatcher_set_output_format(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    dispatcher.register(DummyItem, DummyItemFormatter())
    assert dispatcher.output_format == "terminal"

    dispatcher.set_output_format("json")
    assert dispatcher.output_format == "json"

    item = DummyItem(name="gear", count=1)
    dispatcher.dispatch(item)  # Omitting output_format uses active format ("json")

    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed == {
        "event_type": "DummyItem",
        "payload": {"name": "gear", "count": 1},
    }


def _sample_catalog_record() -> CatalogRecord:
    return CatalogRecord(
        id=1,
        sha="workflow_1234567",
        item_type=CatalogItemType.WORKFLOW,
        name="test-workflow",
        path=Path("workflows/test-workflow.yml"),
        checksum="1234567890abcdef",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
    )


class CatalogDispatcherIntegrationTests:
    """Integration tests for UiDispatcher catalog formatters and JSON/terminal output."""

    def test_register_catalog_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)

        assert CatalogListResult in dispatcher._registry
        assert CatalogShowResult in dispatcher._registry
        assert CatalogDeleteResult in dispatcher._registry
        assert CatalogCreateResult in dispatcher._registry

    def test_ui_dispatcher_default_registrations(self) -> None:
        assert CatalogListResult in ui_dispatcher._registry
        assert CatalogShowResult in ui_dispatcher._registry
        assert CatalogDeleteResult in ui_dispatcher._registry
        assert CatalogCreateResult in ui_dispatcher._registry

    def test_dispatcher_list_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item], type_filter="workflow")

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogListResult"
        assert len(payload["payload"]["items"]) == 1
        assert payload["payload"]["items"][0]["name"] == "test-workflow"

    def test_dispatcher_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogShowResult(item=item, content="name: test\n")

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogShowResult"
        assert payload["payload"]["item"]["sha"] == item.sha

    def test_dispatcher_delete_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogDeleteResult(item=item, deleted=True)

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogDeleteResult"
        assert payload["payload"]["deleted"] is True

    def test_dispatcher_create_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_catalog_formatters(dispatcher)
        item = _sample_catalog_record()
        result = CatalogCreateResult(item=item)

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "CatalogCreateResult"
        assert payload["payload"]["item"]["name"] == "test-workflow"

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        item = _sample_catalog_record()
        result = CatalogListResult(items=[item])

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "test-workflow" in output
        assert "workflow_1234567" in output


class ConfigRegistrationAndDispatchTests:
    """Tests for registration and dispatcher integration."""

    def test_register_config_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        assert ConfigLoadResult in dispatcher._registry
        assert WorktreeConfig in dispatcher._registry
        assert ConfigValidationResult in dispatcher._registry
        assert ConfigSetResult in dispatcher._registry
        assert isinstance(dispatcher._registry[WorktreeConfig], ConfigShowFormatter)
        assert isinstance(dispatcher._registry[ConfigValidationResult], ConfigValidateFormatter)
        assert isinstance(dispatcher._registry[ConfigSetResult], ConfigSetFormatter)

    def test_ui_dispatcher_registration(self) -> None:
        assert WorktreeConfig in ui_dispatcher._registry
        assert ConfigValidationResult in ui_dispatcher._registry
        assert ConfigSetResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[WorktreeConfig], ConfigShowFormatter)
        assert isinstance(ui_dispatcher._registry[ConfigValidationResult], ConfigValidateFormatter)
        assert isinstance(ui_dispatcher._registry[ConfigSetResult], ConfigSetFormatter)

    def test_dispatcher_config_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="ndjson-proj"))

        dispatcher.dispatch(config, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "WorktreeConfig"
        assert payload["payload"]["version"] == 1
        assert payload["payload"]["project"]["name"] == "ndjson-proj"

    def test_dispatcher_config_show_terminal(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        config = WorktreeConfig(version=1, project=ProjectConfig(name="terminal-proj"))

        dispatcher.dispatch(config, output_format="terminal")

        output = buffer.getvalue()
        assert "Config:" in output
        assert "Status: valid" in output
        assert "terminal-proj" in output

    def test_dispatcher_config_validate_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        result = ConfigValidationResult(
            status=ConfigValidationStatus.VALID,
            config_path=Path("/workspace/.worktree/config.json"),
            config=WorktreeConfig(version=1, project=ProjectConfig(name="ndjson-validate")),
            warnings=["warn-1"],
            errors=[],
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigValidationResult"
        assert payload["payload"]["status"] == "valid"
        assert payload["payload"]["config_path"] == "/workspace/.worktree/config.json"
        assert payload["payload"]["warnings"] == ["warn-1"]

    def test_dispatcher_config_set_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_config_formatters(dispatcher)
        result = ConfigSetResult(
            status=ConfigSetStatus.OK,
            config_path=Path("/workspace/.worktree/config.json"),
            key="agent.model",
            value="gpt-4o",
            errors=[],
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "ConfigSetResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["key"] == "agent.model"
        assert payload["payload"]["value"] == "gpt-4o"


def _sample_run_record() -> RunRecord:
    return RunRecord(
        id=1,
        session_id="sess-12345678",
        blueprint_name="deploy-task",
        kind=BlueprintKind.TASK,
        status=RunStatus.COMPLETED,
        branch_name="feature/test",
        started_at="2026-08-19 01:00:00",
        completed_at="2026-08-19 01:00:10",
        error_message=None,
        checkpoint_json=None,
    )


class HistoryDispatcherIntegrationTests:
    """Integration tests for UiDispatcher history formatters and JSON/terminal output."""

    def test_register_history_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)

        assert HistoryListResult in dispatcher._registry
        assert HistoryShowResult in dispatcher._registry
        assert isinstance(dispatcher._registry[HistoryListResult], HistoryListFormatter)
        assert isinstance(dispatcher._registry[HistoryShowResult], HistoryShowFormatter)

    def test_ui_dispatcher_default_registrations(self) -> None:
        assert HistoryListResult in ui_dispatcher._registry
        assert HistoryShowResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[HistoryListResult], HistoryListFormatter)
        assert isinstance(ui_dispatcher._registry[HistoryShowResult], HistoryShowFormatter)

    def test_dispatcher_list_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "HistoryListResult"
        assert payload["payload"]["status"] == "ok"
        assert len(payload["payload"]["runs"]) == 1
        assert payload["payload"]["runs"][0]["session_id"] == "sess-12345678"

    def test_dispatcher_show_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_history_formatters(dispatcher)
        run = _sample_run_record()
        result = HistoryShowResult(
            status=HistoryShowStatus.OK,
            session_id="sess-12345678",
            run=run,
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "HistoryShowResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["session_id"] == "sess-12345678"
        assert payload["payload"]["run"]["session_id"] == "sess-12345678"

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        run = _sample_run_record()
        result = HistoryListResult(status=HistoryListStatus.OK, runs=[run])

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "Execution History" in output
        assert "sess-12345678" in output


class DiffDispatcherIntegrationTests:
    """Integration tests for UiDispatcher diff formatters and JSON/terminal/raw output."""

    def test_register_diff_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_diff_formatters(dispatcher)

        assert DiffResult in dispatcher._registry
        assert isinstance(dispatcher._registry[DiffResult], DiffResultFormatter)

    def test_ui_dispatcher_registration(self) -> None:
        assert DiffResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[DiffResult], DiffResultFormatter)

    def test_dispatcher_json_format_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_diff_formatters(dispatcher)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_ndjson",
            artifact_path=Path("/repo/.worktree/sessions/sbx_ndjson/diff.patch"),
            diff_text=_SAMPLE_DIFF,
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "DiffResult"
        assert payload["payload"]["status"] == "ok"
        assert payload["payload"]["session_id"] == "sbx_ndjson"
        assert payload["payload"]["diff_text"] == _SAMPLE_DIFF

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_term",
            artifact_path=Path("/repo/.worktree/sessions/sbx_term/diff.patch"),
            diff_text=_SAMPLE_DIFF,
        )

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "Session: sbx_term" in output
        assert "def old(): pass" in output

    def test_dispatcher_raw_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_diff_formatters(dispatcher)
        result = DiffResult(
            status=DiffStatus.OK,
            session_id="sbx_raw_dispatch",
            artifact_path=Path("/repo/.worktree/sessions/sbx_raw_dispatch/diff.patch"),
            diff_text=_SAMPLE_DIFF,
            raw=True,
        )

        dispatcher.dispatch(result, output_format="raw")

        captured = capsys.readouterr()
        assert captured.out == _SAMPLE_DIFF


class WorkspaceInitDispatcherIntegrationTests:
    """Integration tests for UiDispatcher workspace init formatters and JSON/terminal output."""

    def test_register_init_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_init_formatters(dispatcher)

        assert WorkspaceInitResult in dispatcher._registry
        assert isinstance(dispatcher._registry[WorkspaceInitResult], WorkspaceInitFormatter)

    def test_ui_dispatcher_registration(self) -> None:
        assert WorkspaceInitResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[WorkspaceInitResult], WorkspaceInitFormatter)
        assert InitOutcomeFormatter is WorkspaceInitFormatter

    def test_dispatcher_json_format_ndjson(self, fs: FileSystem, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_init_formatters(dispatcher)
        result = WorkspaceInitResult(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree", root_created=True),
            config_result=ConfigGenerationResult(config_path=fs.base_path / ".worktree" / "config.json", created=True),
            seed_result=SeedResult(),
        )

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "WorkspaceInitResult"
        assert payload["payload"]["bootstrap_result"]["root_created"] is True
        assert payload["payload"]["config_result"]["created"] is True

    def test_dispatcher_terminal_format(self, fs: FileSystem) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        result = WorkspaceInitResult(
            bootstrap_result=BootstrapResult(root_path=fs.base_path / ".worktree", root_created=True),
            config_result=ConfigGenerationResult(config_path=fs.base_path / ".worktree" / "config.json", created=True),
            seed_result=SeedResult(),
        )

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "Initialized Worktree" in output
        assert "Generated config" in output


def _sample_status_result() -> WorktreeStatusResult:
    base = Path("/workspace/my-repo")
    return WorktreeStatusResult(
        root_dir=base,
        is_initialized=True,
        git=GitStatusInfo(
            is_git_repo=True,
            branch="feature/status-cmd",
            is_dirty=False,
            uncommitted_files=0,
        ),
        config=ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=base / ".worktree" / "config.json",
            is_valid=True,
            config=WorktreeConfig(
                version=1,
                project=ProjectConfig(name="worktree-cli"),
                agent=AgentConfig(model="gemini-2.5-flash"),
            ),
        ),
        catalog=CatalogStatusInfo(
            exists=True,
            catalog_dir=base / ".worktree" / "catalog",
            total_items=2,
            workflows_count=1,
            tasks_count=1,
            steps_count=0,
            invalid_items=0,
            item_names=["deploy", "lint"],
        ),
        database=DatabaseStatusInfo(
            exists=True,
            db_path=base / ".worktree" / "data.db",
            is_accessible=True,
            total_runs=1,
        ),
        sandboxes=SandboxStatusInfo(
            active_sandboxes=1,
            total_sandboxes=1,
            max_active_sandboxes=5,
        ),
    )


class StatusDispatcherIntegrationTests:
    """Integration tests for UiDispatcher status formatters and JSON/terminal output."""

    def test_register_status_formatters_custom_dispatcher(self) -> None:
        dispatcher = UiDispatcher()
        register_status_formatters(dispatcher)

        assert WorktreeStatusResult in dispatcher._registry
        assert isinstance(dispatcher._registry[WorktreeStatusResult], WorktreeStatusFormatter)

    def test_ui_dispatcher_registration(self) -> None:
        assert WorktreeStatusResult in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[WorktreeStatusResult], WorktreeStatusFormatter)

    def test_dispatcher_json_format_ndjson(self, capsys: pytest.CaptureFixture[str]) -> None:
        dispatcher = UiDispatcher()
        register_status_formatters(dispatcher)
        result = _sample_status_result()

        dispatcher.dispatch(result, output_format="json")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1

        payload = json.loads(lines[0])
        assert payload["event_type"] == "WorktreeStatusResult"
        assert payload["payload"]["root_dir"] == "/workspace/my-repo"
        assert payload["payload"]["config_status"] == "ok"

    def test_dispatcher_terminal_format(self) -> None:
        dispatcher, buffer = make_dispatcher_with_buffer(force_terminal=True)
        result = _sample_status_result()

        dispatcher.dispatch(result, output_format="terminal")

        output = buffer.getvalue()
        assert "Worktree Workspace Status" in output
        assert "worktree-cli" in output


class EventsDispatcherIntegrationTests:
    """Integration tests for UiDispatcher event formatters."""

    def test_lock_wait_event_registration(self) -> None:
        assert LockWaitEvent in ui_dispatcher._registry
        assert isinstance(ui_dispatcher._registry[LockWaitEvent], LockWaitFormatter)
