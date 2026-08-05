"""Tests for the Ollama agent adapter."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from getworktree.common.schema_validation import CONFIG_VALIDATOR
from getworktree.core.workflows.agents import (
    AgentRequest,
    AgentResponseStatus,
    OllamaAgentAdapter,
    get_agent_adapter,
)
from getworktree.core.workflows.agents.ollama import (
    DEFAULT_OLLAMA_ENDPOINT,
    MODEL_OUTPUT_UNPARSEABLE,
    OLLAMA_HOST_ENV,
    build_ollama_messages,
    extract_json_object,
    parse_ollama_model_text,
    resolve_ollama_endpoint,
    validate_ollama_endpoint,
)
from getworktree.core.workflows.payload import AgentFailurePayload
from getworktree.core.workflows.validate import validate_workflow_document


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
        "model": "smollm2:1.7b",
        "endpoint": "http://127.0.0.1:11434",
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    base.update(kwargs)
    return AgentRequest.model_validate(base)


def _chat_body(content: str) -> str:
    return json.dumps({"message": {"role": "assistant", "content": content}})


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


class FactoryOllamaTests:
    def test_ollama_provider(self) -> None:
        adapter = get_agent_adapter("ollama")
        assert isinstance(adapter, OllamaAgentAdapter)

    def test_unsupported_lists_ollama(self) -> None:
        with pytest.raises(ValueError, match="AGENT_PROVIDER_UNSUPPORTED") as exc:
            get_agent_adapter("openai")
        msg = str(exc.value)
        assert "local" in msg
        assert "ollama" in msg


class ResolveEndpointTests:
    def test_request_wins(self) -> None:
        assert (
            resolve_ollama_endpoint("http://example:11434/", env={})
            == "http://example:11434"
        )

    def test_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(OLLAMA_HOST_ENV, "http://host:1")
        assert resolve_ollama_endpoint(None) == "http://host:1"

    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(OLLAMA_HOST_ENV, raising=False)
        assert resolve_ollama_endpoint(None) == DEFAULT_OLLAMA_ENDPOINT

    def test_validate_scheme(self) -> None:
        assert validate_ollama_endpoint("http://127.0.0.1:11434") is None
        assert validate_ollama_endpoint("https://x") is None
        assert validate_ollama_endpoint("127.0.0.1:11434") is not None
        assert validate_ollama_endpoint("ftp://x") is not None


class ParseHelpersTests:
    def test_extract_fenced(self) -> None:
        text = 'Here:\n```json\n{"unified_diff": "d", "unfixable": false}\n```\n'
        blob = extract_json_object(text)
        assert blob is not None
        assert "unified_diff" in blob

    def test_parse_and_ignore_extra(self) -> None:
        parsed = parse_ollama_model_text(
            '{"unified_diff": "diff", "summary": "ok", "extra": 1}'
        )
        assert parsed is not None
        assert parsed.unified_diff == "diff"

    def test_build_messages_include_payload(self, sandbox: Path) -> None:
        msgs = build_ollama_messages(_request(sandbox))
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "pytest" in msgs[1]["content"]
        assert "boom" in msgs[1]["content"]


class OllamaAdapterTests:
    def test_proposed_patch(self, sandbox: Path) -> None:
        content = json.dumps(
            {"unified_diff": "diff --git a/x b/x\n", "summary": "fixed"}
        )

        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            assert url.endswith("/api/chat")
            assert timeout == 10.0
            payload = json.loads(body.decode("utf-8"))
            assert payload["model"] == "smollm2:1.7b"
            assert payload["stream"] is False
            assert payload["options"]["num_predict"] == 1024
            assert len(payload["messages"]) == 2
            return 200, _chat_body(content)

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.unified_diff == "diff --git a/x b/x\n"
        assert resp.summary == "fixed"
        assert resp.errors == []

    def test_unfixable(self, sandbox: Path) -> None:
        content = json.dumps(
            {
                "unfixable": True,
                "unfixable_reason": "needs redesign",
                "summary": "nope",
            }
        )

        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            return 200, _chat_body(content)

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.UNFIXABLE
        assert resp.unfixable_reason == "needs redesign"

    def test_no_op(self, sandbox: Path) -> None:
        content = json.dumps({"unified_diff": "", "summary": "nothing"})

        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            return 200, _chat_body(content)

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.NO_OP

    def test_fenced_json(self, sandbox: Path) -> None:
        content = '```json\n{"unified_diff": "d\\n", "summary": "x"}\n```'

        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            return 200, _chat_body(content)

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.unified_diff == "d\n"

    def test_garbage_model_text(self, sandbox: Path) -> None:
        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            return 200, _chat_body("sorry I cannot produce JSON today")

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.UNFIXABLE
        assert resp.unfixable_reason == MODEL_OUTPUT_UNPARSEABLE
        assert resp.errors == []

    def test_missing_model(self, sandbox: Path) -> None:
        resp = OllamaAgentAdapter(http_post=lambda *a, **k: (200, "{}")).propose_fix(
            _request(sandbox, model=None)
        )
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("model" in e.lower() for e in resp.errors)
        assert any("agent.model" in e for e in resp.errors)

    def test_invalid_endpoint_scheme(self, sandbox: Path) -> None:
        resp = OllamaAgentAdapter(http_post=lambda *a, **k: (200, "{}")).propose_fix(
            _request(sandbox, endpoint="127.0.0.1:11434")
        )
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("http://" in e for e in resp.errors)

    def test_connection_error(self, sandbox: Path) -> None:
        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            raise URLError("connection refused")

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("connection refused" in e for e in resp.errors)

    def test_http_500(self, sandbox: Path) -> None:
        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            return 500, "internal boom"

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("500" in e for e in resp.errors)
        assert any("internal boom" in e for e in resp.errors)

    def test_timeout(self, sandbox: Path) -> None:
        def http_post(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            raise TimeoutError("timed out")

        resp = OllamaAgentAdapter(http_post=http_post).propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.TIMEOUT
        assert any("timed out" in e.lower() for e in resp.errors)
        assert any("ollama" in e.lower() for e in resp.errors)


class SchemaOllamaTests:
    def test_config_schema_accepts_ollama(self) -> None:
        import copy

        from getworktree.core.config.generator import CANONICAL_V1_DEFAULTS

        data = copy.deepcopy(CANONICAL_V1_DEFAULTS)
        data["agent"]["provider"] = "ollama"
        data["agent"]["model"] = "smollm2:1.7b"
        assert CONFIG_VALIDATOR.validate(data).ok

    def test_workflow_schema_accepts_ollama(self) -> None:
        raw = {
            "version": 1,
            "name": "fix-tests",
            "description": "x",
            "trigger": {"command": "pytest", "args": [], "timeout_seconds": 60},
            "agent": {
                "provider": "ollama",
                "mode": "fix_failure",
                "timeout_seconds": 120,
            },
            "iteration": {
                "max_attempts": 3,
                "stop_when": ["trigger_passes", "unfixable", "user_abort"],
            },
            "sandbox": {"auto_clean": True, "keep_on_failure": True},
            "approval": {"require_before_apply": True},
            "context": {"include": ["trigger_output"]},
            "patch": {
                "strategy": "unified_diff",
                "max_files": 10,
                "max_patch_kb": 64,
            },
        }
        result = validate_workflow_document(raw, source_path=Path("in-memory.yml"))
        assert result.ok, result.errors

    def test_workflow_schema_rejects_openai(self) -> None:
        raw = {
            "version": 1,
            "name": "fix-tests",
            "description": "x",
            "trigger": {"command": "pytest", "args": [], "timeout_seconds": 60},
            "agent": {
                "provider": "openai",
                "mode": "fix_failure",
                "timeout_seconds": 120,
            },
            "iteration": {
                "max_attempts": 3,
                "stop_when": ["trigger_passes"],
            },
            "sandbox": {"auto_clean": True, "keep_on_failure": True},
            "approval": {"require_before_apply": True},
            "context": {"include": ["trigger_output"]},
            "patch": {
                "strategy": "unified_diff",
                "max_files": 10,
                "max_patch_kb": 64,
            },
        }
        result = validate_workflow_document(raw, source_path=Path("in-memory.yml"))
        assert not result.ok
