# GitHub Issue Creation and Updates

Use this guide when opening or revising GitHub issues for `getworktree`.
Canonical example of structure, depth, and tone:
[issue #3](https://github.com/getworktree/getworktree/issues/3).

Issues should be **implementation-ready**: an agent or human can implement from
the issue alone without guessing product intent, schemas, or CLI wording.

## When to create vs update

- **Create** a new issue for a distinct feature, behavior change, or bug with
  its own acceptance boundary.
- **Update** an existing issue when scope, requirements, predetermined data,
  CLI copy, or acceptance criteria change—edit the body in place rather than
  scattering decisions across comments only.
- Prefer one focused issue over a grab-bag. Split large work into linked issues
  when acceptance criteria would otherwise mix unrelated outcomes.

## Title

- Imperative or outcome-focused, concise (e.g. `Seed starter loop definitions`).
- No ticket-ID prefixes or noisy tags in the title.

## Body structure

Use the sections below in order. Omit a section only when it truly does not
apply (e.g. no CLI for a pure library change); do not omit Scope, Acceptance
Criteria, or Definition of Done for feature work.

### 1. Goal / User Story

Short narrative of **why** and **who benefits**. Prefer 2–4 sentences:

- User-facing outcome when the work ships
- Friction removed or capability unlocked
- Constraints that must hold (e.g. idempotent, non-destructive)

Optional one-liner form when useful:

```markdown
**As a** <user>,
**I want** <capability>,
**so that** <benefit>.
```

### 2. Scope

Explicit boundaries.

```markdown
### In scope
- ...

### Out of scope
- ...
```

Call out optional/v1 stretch items separately (e.g. “force mode if implemented
in v1”) so implementers do not treat them as silent requirements.

### 3. Functional / Non-Functional Requirements

Number requirements so discussion and PRs can reference them (`FR-1`, `NFR-2`).

**Functional (FR-*)** — observable behaviors, branching, and outcomes:

- Happy path
- Idempotent / rerun behavior
- Partial success
- Validation gates
- Flag-controlled behavior

Each FR should state **condition → action → result** (and structured errors
where relevant).

**Non-functional (NFR-*)** — quality attributes, for example:

- Idempotency and non-destructive defaults
- Deterministic file names and content
- Atomic writes / durability
- Performance or size limits (if any)
- Security or trust boundaries (if any)
- Compatibility (schema versions, CLI stability)

### 4. Pre-determined data

Lock values the implementer must not invent. Include only what this issue
owns; link to schemas/docs for shared contracts.

Typical contents:

| Kind | Examples |
|------|----------|
| DTO / result shapes | field names, types, lists vs scalars |
| Config keys / defaults | JSON paths, default values |
| Templates | full YAML/JSON bodies or paths to package templates |
| Constants | filenames, loop `name` values, error codes |
| Paths | `.worktree/loops/fix-tests.yml`, etc. |
| Suggested APIs | function signatures, helper responsibilities |

Use fenced code blocks for schemas, templates, and APIs. Keep template content
valid against the relevant schema version when the issue claims validity.

### 5. CLI Output Expectations

Show **exact or near-exact** user-visible copy for important outcomes:

- Fresh / success
- Already present / no-op
- Partial success
- Validation or hard failure (include a short “Fix:” hint when useful)

Prefer bullet trees that match existing `wt` console style. If output is
structured data only (no new copy), say so and describe the fields rendered.

### 6. Error Cases to Handle

Numbered list of failure modes, not only the happy path. Include:

- Missing or unwritable paths
- Type/path collisions (file vs directory)
- Schema or validation failures
- Permission / atomic-write failures
- Concurrency or reruns when relevant
- Invalid user input or conflicting flags

For each case, the issue should make the expected product behavior obvious
(abort, skip, partial continue, error code/message).

### 7. Acceptance Criteria

Checklist of **testable** outcomes. Prefer verifiable statements:

1. Command X in state Y produces Z.
2. Rerun does not destroy user data.
3. Artifacts validate against schema vN.
4. Tests cover fresh, existing, partial, and failure paths.

Avoid vague criteria (“works well”, “good UX”) unless paired with a concrete
check.

### 8. Definition of Done

Ship bar beyond “code exists”:

- Behavior implemented and wired to the right command(s)
- Predetermined data/templates match the issue and pass validation
- Default behavior matches stated safety properties
- CLI reporting matches expectations
- Tests pass; docs updated when behavior is described under `docs/agents/`
- Related issues/PRs linked if needed

## Optional sections (when they add clarity)

Add after the core sections only if useful—do not pad:

| Section | Use when |
|---------|----------|
| **Test plan** | Non-obvious unit/integration cases worth listing |
| **Dependencies** | Upstream prerequisites or downstream consumers |
| **Write / rollout strategy** | Atomic writes, migration, feature flags |
| **Suggested API** | Multi-module design needs an agreed surface |

## Tone and style

Match [issue #3](https://github.com/getworktree/getworktree/issues/3):

- Direct, specification-like; minimal marketing language
- Short bullets over long prose
- Concrete paths, command names (`wt init`), and schema versions
- Requirements as behaviors, not implementation micromanagement—unless
  predetermined data or safety (atomic write, non-destructive) requires it
- “If implemented in v1” for optional slices; do not bury must-haves as options

## Updates and PR linkage

- When implementation discovers a decision change, **update the issue body**
  (scope, FR/NFR, templates, acceptance criteria) so the issue stays the
  source of truth.
- Reference requirement IDs in PR descriptions when helpful (`Implements FR-2`).
- Close the issue only when Definition of Done is met (or explicitly waived in
  the issue with rationale).

## Minimal skeleton

```markdown
## Goal / User Story

<why, who, outcome, key constraints>

## Scope

### In scope
- ...

### Out of scope
- ...

## Functional requirements

### FR-1: <name>
...

## Non-functional requirements

### NFR-1: <name>
...

## Pre-determined data

<DTOs, config, templates, constants, paths, APIs>

## CLI output expectations

### <scenario>
```
...
```

## Error cases to handle

1. ...

## Acceptance criteria

1. ...

## Definition of done

- ...
```
