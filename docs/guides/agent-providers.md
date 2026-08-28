# AI Agent Providers

Worktree integrates with various AI model providers and developer tools to power agentic steps (`type: agent`).

---

## Supported Providers

| Provider | Identifier | Required Env Var | Notes |
|---|---|---|---|
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | Direct LLM code generation and sandbox editing. |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | Supports GPT-4o, o3-mini, and compatible models. |
| **Anthropic Claude** | `anthropic` | `ANTHROPIC_API_KEY` | Supports Claude 3.5 Sonnet, Claude 3.7 Sonnet, etc. |
| **Cursor CLI** | `cursor` | `CURSOR_API_KEY` | Integrates with Cursor agentic tools. |
| **GitHub Copilot** | `copilot` | `GITHUB_TOKEN` or `GH_TOKEN` | Integrates with Copilot CLI capabilities. |
| **Ollama** | `ollama` | `OLLAMA_HOST` (optional) | Local open-weights models (e.g. Llama 3.3, Qwen 2.5). Default: `http://localhost:11434`. |
| **Local Mock** | `local` | None | Built-in offline testing mock adapter. |

---

## Configuring Default Provider in `config.json`

Set your project's default AI provider in `.worktree/config.json`:

```json
{
  "agent": {
    "provider": "gemini",
    "model": "gemini-2.5-pro",
    "endpoint": null,
    "temperature": 0.2,
    "max_tokens": 4096
  }
}
```

You can update these settings via `wt config set`:

```bash
wt config set agent.provider anthropic
wt config set agent.model claude-3-7-sonnet-20250219
wt config set agent.temperature 0.1
```

---

## Overriding the Agent Provider at Runtime

You can override the provider for a specific run using the `--agent` CLI flag:

```bash
wt run fix-bug --agent ollama
```

---

## Local LLMs with Ollama

To run tasks with full local privacy using Ollama:

1. Start your local Ollama instance:
   ```bash
   ollama run llama3.1
   ```

2. Configure Worktree:
   ```bash
   wt config set agent.provider ollama
   wt config set agent.model llama3.1
   wt config set agent.endpoint http://localhost:11434
   ```

3. Run your workflow:
   ```bash
   wt run code-reviewer
   ```

---

## Next Steps

- Explore the [Blueprint Schema Reference](../reference/blueprint-schema.md).
- Check out the [TDD Loop Recipe](../recipes/tdd-loop.md).
