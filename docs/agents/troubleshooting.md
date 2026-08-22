# Troubleshooting: agent provider setup

Every provider's `propose_fix` (or, for the direct-mutation providers, `_preflight` /
`_default_run`) returns a classified `AgentResponse` with `status` and a human-readable
`errors[0]` — it never raises for a setup problem. This doc collects each provider's
current failure modes so an agent debugging a failing run can match the symptom to the
fix without re-deriving it from five separate adapter files. Source of truth for each is
`core/agents/<provider>.py`; if the exact wording drifts from this table, trust the
source and fix this doc.

## `local`

Adapter: `LocalAgentAdapter` (`core/agents/local.py`). Runs a subprocess (default
`worktree-local-agent`, override via `WORKTREE_LOCAL_AGENT_CMD`) over JSON stdin/stdout.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=provider_error`, `"failed to start '<argv[0]>'"` | The resolved command isn't on `PATH` | Install/build the local agent binary, or set `WORKTREE_LOCAL_AGENT_CMD` to the correct path |
| `status=timeout` | Subprocess exceeded `agent.timeout_seconds` (or the request's) | Raise `agent.timeout_seconds` (`wt config set agent.max_tokens`... see `agent.*` keys) or speed up the local agent |
| `status=provider_error`, `"invalid JSON on stdout"` / `"empty stdout"` | The local agent didn't print a JSON object on stdout | Fix the local agent to print exactly one JSON object matching `LocalAgentStdout` (`unfixable`, `unfixable_reason`, `unified_diff`, `summary`) |
| `status=provider_error`, `"stdout JSON failed schema validation"` | Output has the wrong types/extra keys (`LocalAgentStdout` is `extra: "forbid", strict: True`) | Match the exact field names/types; no additional keys |

## `ollama`

Adapter: `OllamaAgentAdapter` (`core/agents/ollama.py`). In-process HTTP call to
`<endpoint>/api/chat`, no subprocess/CLI dependency.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=provider_error`, `"ollama requires a non-empty model"` | `agent.model` is unset | `wt config set agent.model <name>` |
| `status=provider_error`, `"invalid Ollama endpoint"` | Resolved endpoint isn't an absolute `http(s)://` URL | Fix `agent.endpoint` or `OLLAMA_HOST` |
| `status=provider_error`, `"failed to reach Ollama at '<url>'"` | Connection refused/DNS failure | Start the Ollama server, or point `agent.endpoint` / `OLLAMA_HOST` at a running one (default `http://127.0.0.1:11434`) |
| `status=timeout` | HTTP call exceeded `timeout_seconds` | Raise `agent.timeout_seconds`, or use a smaller/faster model |
| `status=provider_error`, `"Ollama HTTP <nnn>"` | Non-2xx response (e.g. model not pulled) | Check the embedded response snippet; `ollama pull <model>` if it's a missing-model error |
| `status=unfixable`, `unfixable_reason=model_output_unparseable` | Model didn't return the expected JSON object shape | Not a setup problem — the model ignored the system prompt's JSON contract; retry or switch models |

Endpoint resolution order: explicit request endpoint → `OLLAMA_HOST` env var →
`http://127.0.0.1:11434` default.

## `cursor`

Adapter: `CursorAgentAdapter` (`core/agents/cursor.py`), via the shared
`CliDirectMutationAdapter` base. Uses the `cursor-sdk` Python package, not a CLI binary.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=provider_error`, `"cursor requires a non-empty model"` | `agent.model` is unset | `wt config set agent.model <name>` |
| `status=provider_error`, `"missing CURSOR_API_KEY"` | Env var not set (checked at preflight, before any SDK call) | `export CURSOR_API_KEY=...` |
| `status=provider_error`, `"cursor-sdk is not installed"` | Python package missing | `pip install src[cursor]` (per the adapter's own message) |
| `status=timeout` | SDK run didn't finish within `timeout_seconds` (adapter runs it on a worker thread and best-effort cancels) | Raise `agent.timeout_seconds` |

`CURSOR_API_KEY` is read fresh from the environment on every call — it is never
persisted in `config.json`, and never stored on any request/response model. See
[architecture.md](architecture.md#secrets-handling).

## `gemini`

Adapter: `GeminiAgentAdapter` (`core/agents/gemini.py`), via `CliDirectMutationAdapter`.
Shells out to the `gemini` CLI.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=provider_error`, `"missing GEMINI_API_KEY"` | Env var not set | `export GEMINI_API_KEY=...` |
| `status=provider_error`, `"gemini is not installed or not on PATH"` | CLI binary missing | Install the Gemini CLI (link is in the error message) |
| `status=timeout` | CLI process exceeded `timeout_seconds` | Raise `agent.timeout_seconds` |
| `status=provider_error`, exit-code detail (stderr/stdout snippet) | Non-zero CLI exit | Read the embedded stderr/stdout snippet — this is the CLI's own error, not worktree's |
| `status=provider_error`, `"invalid JSON from Gemini CLI"` / `"...missing response"` | CLI's `--output-format json` output didn't parse or lacked a usable field | Likely a Gemini CLI version mismatch; check `gemini --version` against what this adapter expects |

## `copilot`

Adapter: `CopilotAgentAdapter` (`core/agents/copilot.py`), via `CliDirectMutationAdapter`.
Shells out to `gh copilot`.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=provider_error`, `"missing GH_TOKEN or GITHUB_TOKEN"` | Neither env var set | `export GH_TOKEN=...` (checked in that order; either satisfies preflight) |
| `status=provider_error`, `"gh is not installed or not on PATH"` | GitHub CLI missing | Install `gh` (link is in the error message) |
| `status=timeout` | CLI process exceeded `timeout_seconds` | Raise `agent.timeout_seconds` |
| `status=provider_error`, `"invalid JSONL from Copilot CLI"` | `gh copilot`'s streamed JSONL output had a malformed line | Likely a `gh`/Copilot extension version mismatch |
| `status=provider_error`, `"Copilot CLI result exit code <n>"` | The CLI's own `result` event reported non-zero | Copilot's own failure, not worktree's — inspect `raw_text` |

## Cross-provider notes

- All five preflight/error paths are non-raising and land in `AgentResponse.errors[0]`
  (or, for the direct-mutation trio, get wrapped as `PROVIDER_ERROR` by the shared base) —
  if you're seeing an actual Python traceback instead of a classified `AgentResponse`,
  that's a bug in the adapter (an unhandled exception path), not a setup problem; file it
  rather than working around it.
- The config-valid-but-unimplemented provider tokens (`openai`, `anthropic`,
  `azure_openai`, `custom`) fail at `get_agent_adapter` resolution with a bare `ValueError`
  ("Unsupported agent provider... `AGENT_PROVIDER_UNSUPPORTED`"), before any of the
  per-provider preflight above runs. If you're hitting this, the provider genuinely isn't
  built yet — see
  [architecture.md](architecture.md#adding-a-new-agent-provider).
- Every direct-mutation provider's timeout comes from the same source
  (`agent.timeout_seconds`, request-scoped), so "raise the timeout" always means the same
  config key regardless of which provider you're debugging.
