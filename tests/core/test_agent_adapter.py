"""Tests for agent adapter interface, factory, and local provider."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from getworktree.core.agents import (
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
    CopilotAgentAdapter,
    GeminiAgentAdapter,
    LocalAgentAdapter,
    get_agent_adapter,
)
from getworktree.core.agents.local import (
    DEFAULT_LOCAL_AGENT_CMD,
    LOCAL_AGENT_CMD_ENV,
    LocalAgentStdout,
    resolve_local_agent_argv_for_tests,
)
from getworktree.core.loops.payload import AgentFailurePayload


def _payload() -> AgentFailurePayload:
    return AgentFailurePayload(
        command="pytest",
        args=["-q"],
        trigger_status="failed",
        exit_code=1,
        timed_out=False,
        duration_ms=10,
        stdout="boom",
        stderr="",
    )


def _request(sandbox: Path, **kwargs: object) -> AgentRequest:
    base: dict[str, object] = {
        "mode": "fix_failure",
        "payload": _payload(),
        "sandbox_path": sandbox,
        "timeout_seconds": 10,
    }
    base.update(kwargs)
    return AgentRequest.model_validate(base)


def _write_agent_script(path: Path, body: str) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n" + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


class GetAgentAdapterTests:
    def test_local_provider(self) -> None:
        adapter = get_agent_adapter("local")
        assert isinstance(adapter, LocalAgentAdapter)

    def test_unsupported_provider(self) -> None:
        with pytest.raises(ValueError, match="AGENT_PROVIDER_UNSUPPORTED") as exc:
            get_agent_adapter("openai")
        msg = str(exc.value)
        assert "local" in msg
        assert "ollama" in msg
        assert "cursor" in msg
        assert "gemini" in msg
        assert "copilot" in msg
        assert "openai" in msg

    def test_gemini_provider(self) -> None:
        adapter = get_agent_adapter("gemini")
        assert isinstance(adapter, GeminiAgentAdapter)

    def test_copilot_provider(self) -> None:
        adapter = get_agent_adapter("copilot")
        assert isinstance(adapter, CopilotAgentAdapter)

    def test_config_optional(self) -> None:
        from getworktree.core.config.models import AgentConfig

        adapter = get_agent_adapter("local", config=AgentConfig())
        assert isinstance(adapter, LocalAgentAdapter)


class LocalAgentArgvTests:
    def test_default_cmd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(LOCAL_AGENT_CMD_ENV, raising=False)
        assert resolve_local_agent_argv_for_tests() == [DEFAULT_LOCAL_AGENT_CMD]

    def test_env_shlex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, "/bin/my-agent --flag 'a b'")
        assert resolve_local_agent_argv_for_tests() == [
            "/bin/my-agent",
            "--flag",
            "a b",
        ]


class LocalAgentAdapterTests:
    def test_proposed_patch(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            req = json.load(sys.stdin)
            assert req["mode"] == "fix_failure"
            assert "payload" in req
            print(json.dumps({
                "unified_diff": "diff --git a/x b/x\\n",
                "summary": "fixed",
            }))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.ok
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.unified_diff == "diff --git a/x b/x\n"
        assert resp.summary == "fixed"
        assert resp.duration_ms >= 0
        assert resp.errors == []
        assert resp.raw_text is not None

    def test_no_op(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            print(json.dumps({"unified_diff": "", "summary": "nothing"}))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert not resp.ok
        assert resp.status == AgentResponseStatus.NO_OP

    def test_unfixable(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            print(json.dumps({
                "unfixable": True,
                "unfixable_reason": "needs human",
            }))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.UNFIXABLE
        assert resp.unfixable_reason == "needs human"
        assert resp.unified_diff is None

    def test_timeout(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import time
            time.sleep(30)
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox, timeout_seconds=1))
        assert resp.status == AgentResponseStatus.TIMEOUT
        assert "timed out after 1s" in resp.errors[0]
        assert "provider=local" in resp.errors[0]
        assert "agent.timeout_seconds" in resp.errors[0]
        assert resp.duration_ms < 15_000

    def test_missing_command(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, "definitely-not-a-real-agent-cmd-xyz")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert "AGENT_PROVIDER_ERROR" in resp.errors[0]

    def test_invalid_json(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import sys
            sys.stdout.write("not-json")
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert "invalid JSON" in resp.errors[0]
        assert resp.raw_text == "not-json"

    def test_extra_keys_rejected(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            print(json.dumps({"unified_diff": "x", "extra": 1}))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert "schema validation" in resp.errors[0]

    def test_nonzero_exit_without_json(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import sys
            sys.stderr.write("crash")
            sys.exit(2)
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR

    def test_cwd_is_sandbox(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        marker = sandbox / "marker.txt"
        marker.write_text("hi", encoding="utf-8")
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, os, sys
            assert os.path.isfile("marker.txt")
            print(json.dumps({"unified_diff": "diff", "summary": "ok"}))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH

    def test_missing_sandbox_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        resp = LocalAgentAdapter().propose_fix(_request(missing))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert "sandbox path" in resp.errors[0]

    def test_no_sandbox_mutation(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (sandbox / "keep.py").write_text("x\n", encoding="utf-8")
        before = sorted(p.name for p in sandbox.iterdir())
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            print(json.dumps({"unified_diff": "diff --git a/a b/a\\n"}))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        LocalAgentAdapter().propose_fix(_request(sandbox))
        after = sorted(p.name for p in sandbox.iterdir())
        assert before == after

    def test_unfixable_takes_priority_over_diff(
        self, sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script = _write_agent_script(
            tmp_path / "agent.py",
            """
            import json, sys
            print(json.dumps({
                "unfixable": True,
                "unfixable_reason": "no",
                "unified_diff": "diff",
            }))
            """,
        )
        monkeypatch.setenv(LOCAL_AGENT_CMD_ENV, f"{sys.executable} {script}")
        resp = LocalAgentAdapter().propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.UNFIXABLE

    def test_local_stdout_model_forbids_extra(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LocalAgentStdout.model_validate({"unified_diff": "x", "nope": 1})

    def test_response_ok_property(self) -> None:
        assert AgentResponse(status=AgentResponseStatus.PROPOSED_PATCH).ok
        assert not AgentResponse(status=AgentResponseStatus.NO_OP).ok
