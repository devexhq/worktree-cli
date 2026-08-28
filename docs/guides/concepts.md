# Core Concepts & Mental Model

Worktree (`wt`) is designed around a clean separation between **isolated sandboxes**, **declarative blueprints**, and a **stateful runtime engine**.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Worktree CLI (wt)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  wt run <blueprint>                                                     │
│       │                                                                 │
│       ▼                                                                 │
│  ┌───────────────────────┐         ┌─────────────────────────────────┐  │
│  │ Blueprint Catalog     │         │ Git Sandbox Manager             │  │
│  │ (.worktree/catalog/)  │         │                                 │  │
│  │  - workflows/*.yml    │         │  Creates isolated worktree      │  │
│  │  - tasks/*.yml        │         │  Branch: wt/<blueprint>-<id>    │  │
│  │  - steps/*.yml        │         │  Path: .worktree/sandboxes/...  │  │
│  └───────────┬───────────┘         └────────────────┬────────────────┘  │
│              │                                      │                   │
│              └──────────────────┬───────────────────┘                   │
│                                 │                                       │
│                                 ▼                                       │
│                   ┌───────────────────────────┐                         │
│                   │ Runtime Engine & Observer │                         │
│                   │                           │                         │
│                   │  - Evaluates inputs       │                         │
│                   │  - Runs steps in sequence │                         │
│                   │  - Checks assertions      │                         │
│                   │  - Checkpoints on pause   │                         │
│                   │  - Records to SQLite DB   │                         │
│                   └───────────────────────────┘                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Ephemeral Git Sandboxes

When you execute a blueprint or task, Worktree creates an isolated **Git worktree** using a dedicated branch (prefixed with `wt/`).

### Why Sandboxes?
- **Zero Pollution**: Your active working directory and branch remain untouched while automated tasks run or AI agents edit files.
- **Safety**: Broken code, test failures, or unintended edits are contained within the sandbox.
- **Automatic Lifecycle**: Unless `--keep` is specified or execution is paused, the sandbox worktree and branch are automatically cleaned up when the run finishes.

If you ever want to run a blueprint directly in your current working directory without sandbox isolation (e.g. in CI or a container), use the `--no-sandbox` flag:

```bash
wt run my-workflow --no-sandbox
```

---

## 2. Blueprint Taxonomy

A **Blueprint** is a declarative YAML document that defines an automated task or multi-step workflow.

```text
Blueprint
 ├── Task (Single discrete job; sequential list of steps)
 └── Workflow (Multi-step pipeline; supports loops, assertions, and checkpoints)
```

| Concept | Type | Description | File Location |
|---|---|---|---|
| **Step** | Primitive | The smallest unit of execution: a shell command, an AI agent prompt, or a script. | `.worktree/catalog/steps/` |
| **Task** | Blueprint | A sequential list of steps targeting a single goal (e.g., formatting, running tests). Cannot contain loop steps. | `.worktree/catalog/tasks/` |
| **Workflow** | Blueprint | A multi-step orchestration pipeline with assertions, error handling policies, and session pause/resumption. | `.worktree/catalog/workflows/` |

---

## 3. The Blueprint Catalog

Blueprints live in your project's `.worktree/catalog/` directory:

```text
.worktree/catalog/
├── workflows/          # Workflow blueprints (e.g. fix-tests.yml)
├── tasks/              # Task blueprints (e.g. audit-code.yml)
└── steps/              # Reusable step definitions (e.g. run-tests.yml)
```

### Local Blueprints vs. Curated Templates
- **Local Blueprints**: Created and maintained within your repository for project-specific automation.
- **Curated Templates (`wt/*`)**: Built-in steps and workflows provided out of the box (e.g., `wt/git-sync-base`, `wt/ai-planner`, `wt/ai-code-patcher`, `wt/ai-reviewer`). Blueprints can reference these using `uses: wt/<name>`.

---

## 4. Execution Lifecycle & Sessions

Every execution via `wt run` is tracked as a **Session**:

1. **Input Resolution**: Declared parameters and CLI flags are parsed and validated.
2. **Sandbox Creation**: Ephemeral Git worktree branch is provisioned.
3. **Step Execution**: Steps run sequentially inside the sandbox working directory.
4. **Assertions & Quality Gates**: Output and filesystem state are validated after each step.
5. **Resilience & Resumption**:
   - On error, `on_failure` policies determine whether to `abort`, `continue`, `retry`, or `prompt_user`.
   - If an interactive prompt is interrupted or paused, a **checkpoint** is saved in `.worktree/data.db`.
   - The session can be resumed at any time using `wt resume <session-id>`.
6. **Audit History**: All runs, durations, and outputs are recorded and accessible via `wt history`.

---

## Next Steps

- Learn how to [Author Blueprints](authoring-blueprints.md).
- Dive into [Working with Steps](working-with-steps.md).
- Understand [Failure Handling and Session Resumption](failure-handling-and-resume.md).
