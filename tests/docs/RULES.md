<!-- AUTO-GENERATED FROM rules_spec.yaml. DO NOT EDIT DIRECTLY. -->
# Architectural & Coding Invariants (Tests Domain)

> **Notice for Agents:** Code violating `BLOCKER` rules will fail verification.

- **[ARCH-001] Strict Layered Import Flow (BLOCKER):**
  Dependencies flow strictly one way: common/ -> core/{db,git,sandbox,catalog,inputs,patch,history,diff,status}/ -> core/agents/ -> core/step/ -> {core/runtime/, core/blueprint/} -> core/engine/ -> cli/. Upward imports are strictly prohibited.

```python
# ✅ DO: from worktree.core.runtime.engine import run_steps  # in core/engine/
# ❌ DO NOT: from worktree.core.engine.engine import Engine  # upward import in core/runtime/
```

- **[RENDER-003] Inline Error and Warning String Construction (SUGGESTION):**
  Construct errors, warnings, and fixes strings using inline f-strings or literals at call sites. Do not create private single-message formatting wrappers.

```python
# ✅ DO: errors.append(f"Blueprint '{path}' invalid: {err}")
# ❌ DO NOT: errors.append(self._format_validation_error(path, err))
```

- **[MODEL-001] Scoped Model Exceptions with Justifying Comment (BLOCKER):**
  Scoped exceptions allowing extra='ignore' are restricted to hand-authored YAML models (BlueprintDefinition, BlueprintDefaults, LoopStepBlock) and LLM JSON output (OllamaModelStdout), and MUST carry a justifying comment.

```python
# ✅ DO:
# User YAML models permit forward-compatible extra keys
model_config = {'extra': 'ignore'}
# ❌ DO NOT: model_config = {'extra': 'ignore'}  # missing justifying comment
```

- **[CODE-001] Identifier Readability and Approved Abbreviations (BLOCKER):**
  Code must read naturally. Reject cryptic, arbitrary truncations (e.g. val_res, err_msg, acc). Permitted abbreviations: iteration variables (p, x, i, v, c, k, v), standard programming idioms (req, res, fn, fn_node, idx, mod, mod_name, loc, tmp/temp, str, arr, num, len, val, msg), and domain conventions (exc, rel_path, fs, cwd, db, ctx).

```python
# ✅ DO: validation_result = validator.validate(document)
# ❌ DO NOT: val_res = validator.validate(document); acc = []
```

- **[CODE-002] Logical Blank Lines Separation (NIT):**
  Separate distinct logical phases (setup, validate, persist, return) with a blank line. Keep cohesive, tightly coupled lines together.

```python
# ✅ DO:
record = SandboxRecord(...)

self.db.sandboxes.save(record)

return result
# ❌ DO NOT:
record = SandboxRecord(...)
self.db.sandboxes.save(record)
return result
```

- **[TYPE-001] Ban on -> Any Return Annotations (BLOCKER):**
  -> Any on a public function is treated as a defect because it disables type checking transitively at every call site. Prefer object when values are only stored, compared, or passed through.

```python
# ✅ DO: def get_payload(self) -> object: ...
# ❌ DO NOT: def get_payload(self) -> Any: ...
```

- **[TYPE-002] Strict Scoping of Permitted Any (BLOCKER):**
  Any is permitted strictly in: (1) Pydantic mode='before' validators, (2) dict[str, Any] at serialization boundaries, (3) values read from user documents and compared, and (4) **kwargs: Any pass-throughs.

```python
# ✅ DO:
@field_validator('pattern', mode='before')
def _val(cls, v: Any) -> Any: ...
# ❌ DO NOT: def execute_step(step: Any) -> StepResult: ...
```

- **[TYPE-003] Banned Uses of Any (BLOCKER):**
  Banned: Any dodging import boundaries, Any as a test seam, Any where a model already exists, Any in third-party overrides (e.g. ctx: Any for click.Context), and Any filling a known generic (e.g. Popen[Any]).

```python
# ✅ DO: proc: subprocess.Popen[str] = ...
# ❌ DO NOT: proc: subprocess.Popen[Any] = ...
```

- **[TYPE-005] Precise Parameterization for Generator Types (NIT):**
  Avoid overly broad generic type annotations like Generator[Session] without complete yield/send/return parameterization. Specify all three generic parameters.

```python
# ✅ DO: def get_session() -> Generator[Session, None, None]: ...
# ❌ DO NOT: def get_session() -> Generator[Session]: ...
```

- **[ENCAP-001] Expose Public Query Properties (SUGGESTION):**
  Expose public boolean query properties (e.g. is_interactive, is_enabled, has_*) on classes rather than referencing private members from external callers.

```python
# ✅ DO:
@property
def is_running(self) -> bool: return self._proc is not None and self._proc.poll() is None
# ❌ DO NOT: if runner._process is not None: ...  # caller inspecting private state
```

- **[ENCAP-002] No Test Seams in Production Signatures (BLOCKER):**
  Never add a parameter, kwarg, or callback solely for test injection. A parameter production never reads is dead code with a test attached. Monkeypatch collaborators at module boundaries instead.

```python
# ✅ DO: def run(self, cwd: Path) -> RunOutcome: ...  # tests monkeypatch at boundary
# ❌ DO NOT: def run(self, cwd: Path, _runner: GitRunner | None = None) -> RunOutcome: ...
```

- **[PERF-001] No Ad-Hoc DB Instantiations in Loops (BLOCKER):**
  Never instantiate a repository or WorktreeDb inside loops or test helpers. Inject pre-initialized instances to prevent N+1 SQLite connection/migration checks.

```python
# ✅ DO:
repo = RunsRepository(path)
for item in items: repo.create(item)
# ❌ DO NOT: for item in items: repo = RunsRepository(path); repo.create(item)
```

- **[FS-001] Atomic File Writes via Temporary Sibling (BLOCKER):**
  Never write config or state files directly in-place. Write to a .tmp sibling, flush, os.fsync, and atomically swap via Path.replace using Filesystem.atomic_write_json and Filesystem.atomic_write_text.

```python
# ✅ DO: Filesystem.atomic_write_json(config_path, data)
# ❌ DO NOT: with open(config_path, 'w') as f: json.dump(data, f)
```

- **[FS-002] Advisory Cross-Process Locking (BLOCKER):**
  Multi-process sandbox, catalog, or state mutations must acquire the .worktree/.lock advisory lock using common/lock.py and handle LockTimeoutError.

```python
# ✅ DO: with file_lock(lock_path, timeout=10.0): sandbox_service.create(...)
# ❌ DO NOT: sandbox_service.create(...)  # mutating shared dir without acquiring lock
```

- **[COMPAT-001] Strict Public-Only Backwards Compatibility (BLOCKER):**
  Maintain backwards compatibility ONLY for surfaces users interact with directly: CLI command surface (commands, subcommands, arguments, flags), configuration files and blueprint YAMLs (config.json), and stable machine-readable output formats (JSON event envelopes).

```python
# ✅ DO: output_format: OutputFormat = typer.Option(OutputFormat.RICH, '--output-format', '-o')
# ❌ DO NOT: # Renaming user CLI option --timeout to --wait without alias
```

- **[COMPAT-002] Ban on Internal Compatibility Shims and Aliases (BLOCKER):**
  Do NOT preserve backwards compatibility aliases, compatibility properties, or shim layers for internal code (common/, core/, or internal CLI modules) when refactoring or renaming symbols. Update callers and tests directly.

```python
# ✅ DO: # Renamed _unlock_fd directly and updated all internal callers
# ❌ DO NOT:
def _unlock_fd(self): ...
_unlock = _unlock_fd  # internal shim alias
```

- **[COMPAT-003] Greenfield Architecture Default (BLOCKER):**
  Treat the repository as greenfield by default: plan no dual code paths, fallback adapters, or deprecation windows unless an issue explicitly demands one. Replace superseded paths and update callers in the same change set.

```python
# ✅ DO: # Directly replaces legacy loader with new unified loader
# ❌ DO NOT: if config.use_legacy: return LegacyLoader().load()  # unnecessary compatibility branch
```

- **[TEST-001] Test at Contracts, Not Implementation (BLOCKER):**
  Assert on deliberate contracts (BaseResult object, exact JSON dict, exit code, file on disk, git ref), never implementation details (rendered layout, private helpers, call ordering, constructor assignments).

```python
# ✅ DO: assert result == BlueprintLoadResult(status=BlueprintLoadStatus.OK, blueprint=expected_bp)
# ❌ DO NOT: assert service._internal_cache_size == 1; assert mock_parser.call_count == 1
```

- **[TEST-002] 1:1 Source Parity Layout (BLOCKER):**
  Test structure mirrors src/worktree/ 1:1 under tests/. Exactly one test file per source module. Every test directory gets an __init__.py.

```python
# ✅ DO: src/worktree/core/sandbox/services/lifecycle.py -> tests/core/sandbox/services/test_lifecycle.py
# ❌ DO NOT: tests/test_all_sandboxes.py  # unmirrored grab-bag test file
```

- **[TEST-003] Standardized Test Naming and Vague Name Ban (BLOCKER):**
  Test classes must be named *Tests. Methods must follow test_<condition>_<outcome>. Banned vague names with no outcome: test_ok, test_success, test_present, test_missing, test_blank, test_basic, test_default, test_works, test_timeout, test_no_op, test_help. No 'should' prefix.

```python
# ✅ DO:
class ConfigLoaderTests:
    def test_missing_config_returns_not_found_status(self): ...
# ❌ DO NOT:
class TestConfig:
    def test_ok(self): ...
    def test_should_timeout(self): ...
```

- **[TEST-004] Dual-Tier CLI Matrix Testing (BLOCKER):**
  Every CLI command module must implement both *RootTests (direct unit tests for pure Python command handlers taking CliContext) and *CliIntegrationTests (invoking runner.invoke to verify Click/Typer options, exit codes, and output dispatching).

```python
# ✅ DO:
class DiffCommandRootTests: ...  # unit
class DiffCliIntegrationTests: ...  # runner invoke
# ❌ DO NOT: # Only runner.invoke tested; handler logic not unit tested directly
```

- **[TEST-005] Three Tests Per Formatter Protocol (BLOCKER):**
  Every formatter under cli/ui/formatters/<domain>/ must have three tests using FormatterCase: (1) view model transform equality, (2) JSON wire format as an EXACT literal dict, and (3) Rich render at pinned width 160 asserting only semantic values from case.view.

```python
# ✅ DO: test_transform_derives_expected_view(); test_json_payload_matches(); test_rich_render_shows_view()
# ❌ DO NOT: assert 'healthy' in render_rich(formatter.to_rich(data))  # only 1 test
```

- **[TEST-006] Parameterization-First for Sibling Variations (BLOCKER):**
  Parameterization is the primary approach for testing variations of the same contract or function. Never duplicate test functions across input variants, polymorphic target types (e.g. BaseModel vs dict), or invalid payload permutations. Never use `for` loops or stacked assertions over scenarios. Use `@pytest.mark.parametrize` with explicit `pytest.param(..., id="...")` labels. Separate `def test_*` methods are reserved for fundamentally distinct lifecycles, differing fixture requirements, or divergent assertion contracts.

```python
# ✅ DO: @pytest.mark.parametrize("target", [pytest.param(model, id="model"), pytest.param(dict, id="dict")])
# ❌ DO NOT: def test_eval_model(self): ...; def test_eval_dict(self): ...  # duplicate sibling methods
```

- **[TEST-007] Whole Object Comparison (BLOCKER):**
  Compare whole objects (assert result == Expected(...) or assert_model_equal(result, expected)) rather than asserting individual fields. One comparison fails on unexpected extra fields and gives clear diffs. Never use piece-wise attribute assertions on operation results.

```python
# ✅ DO: assert_model_equal(result, StepResult(status=StepStatus.OK, exit_code=0, duration=1.2))
# ❌ DO NOT: assert result.status == StepStatus.OK; assert result.exit_code == 0; assert result.duration == 1.2
```

- **[TEST-008] Test Double Realism and Production Types (BLOCKER):**
  Test doubles must be types production actually passes or implement a Protocol production is typed against. Never build a stub whose interface is the union of every branch in a hasattr chain.

```python
# ✅ DO: class FakeAgentAdapter(AgentAdapter): def propose_fix(self, req: AgentRequest) -> AgentResponse: ...
# ❌ DO NOT: class MockAdapter: def __getattr__(self, name): return MagicMock()
```

- **[TEST-009] Ban on Negative Existence Tests for Deleted Symbols (BLOCKER):**
  Tests prove what the live codebase does, never the historical outcome of a refactor. When dead or obsolete functions, classes, or aliases are removed from production, delete the tests that called them. Never write assert not hasattr(mod, 'old_fn').

```python
# ✅ DO: # Deleted test_old_helper when old_helper was removed from production
# ❌ DO NOT: assert not hasattr(filesystem, 'old_helper')  # negative existence test
```

- **[TEST-010] Complete Assertions Invariant (BLOCKER):**
  assert obj is not None is not an assertion; if it is the only assert, the test is unfinished. Use isinstance only when it distinguishes two real code paths (basedpyright already proves the rest).

```python
# ✅ DO: assert result.session_id == 'wf_abcdef12'
# ❌ DO NOT: assert result is not None; assert isinstance(result, RunOutcome)
```

- **[TEST-011] Determinism and Clock Virtualization (BLOCKER):**
  No hardcoded sleeps (time.sleep) in tests. Step backoff and retry intervals must monkeypatch the clock (time.monotonic / asyncio.sleep) or use VirtualClock.

```python
# ✅ DO: runner = StepRunner(clock=VirtualClock())
# ❌ DO NOT: time.sleep(2.0)  # waiting for process timeout
```

- **[TEST-012] Rich Render Width Pinning (BLOCKER):**
  render_rich(renderable, width=160) is the only supported way to capture rendered output. Console width for rendered assertions is authoritatively pinned to 160. Tests must not rely on ambient terminal size or in-process os.environ['COLUMNS'] mutations.

```python
# ✅ DO: rendered = render_rich(formatter.to_rich(data)); assert 'Session ID' in rendered
# ❌ DO NOT: console = Console(); console.print(formatter.to_rich(data))  # unpinned width
```

- **[TEST-013] No Sole Consumer Tests (BLOCKER):**
  No test may be the sole consumer of a production symbol. If deleting the test would make production code unreachable, the production code is dead. Delete both.

```python
# ✅ DO: # Sandbox.create() called by Engine.run() and tested in test_sandbox.py
# ❌ DO NOT: # Sandbox.debug_dump() called ONLY in test_debug_dump()
```

- **[TEST-014] Strict Typing on Test Helpers and Fixtures (BLOCKER):**
  Annotate test helpers and fixtures as tightly as production code. Give fixtures real return types and type helper parameters against what production passes. No MagicMock in helper signatures.

```python
# ✅ DO: def create_test_session(db: WorktreeDb, session_id: str) -> RunRecord: ...
# ❌ DO NOT: def create_test_session(db: Any, mock_obj: MagicMock) -> Any: ...
```

- **[TEST-015] Orchestration Path Test Coverage (WARNING):**
  Modified command orchestration paths and multi-step dispatch workflows must include covering integration tests. Merging changes with gaps in end-to-end orchestration tests leaves regression risks.

```python
# ✅ DO: class ResumeCommandCliIntegrationTests: def test_resume_executes_remaining_steps(self): ...
# ❌ DO NOT: # PR modifying Engine.resume() without integration tests for resumed step loop
```

- **[DOC-001] Architecture Doc Structural Gate (BLOCKER):**
  Update docs/agents/architecture.md structure sections ONLY when package layout, domain ownership, or import boundaries change. Do not append feature behavior essays there. Pure refactors need no architecture diff.

```python
# ✅ DO: # Updating layers tree in architecture.md for new core/prune/ domain
# ❌ DO NOT: # 100 lines of narrative prose explaining pruning heuristics in architecture.md
```

- **[DOC-003] Schema and Entity Documentation Gate (BLOCKER):**
  Update docs/agents/schemas.md whenever .worktree/config.json keys, blueprint YAML fields, domain DTOs, or database record shapes change.

```python
# ✅ DO: # Adding SandboxPruneResult to section 2 of schemas.md
# ❌ DO NOT: # Adding new Result model in core/models.py without updating schemas.md
```

- **[DOC-004] Ban on Duplicating Source in Docs (SUGGESTION):**
  Docs must not hand-copy Pydantic model signatures, field tables, or enum lists that a Read of the source already gives unambiguously. Link to the model file and document only unexpressed behavior (validators, resolution order).

```python
# ✅ DO: See [`SandboxSession`](src/worktree/core/sandbox/models.py). Sandboxes live under .worktree/sandboxes/.
# ❌ DO NOT:
| Field | Type | Default |
| session_id | str | required |
```

- **[DOC-005] Unavoidable Spec Tables Require Parity Tests (BLOCKER):**
  When a field table is genuinely unavoidable (it is the specification for an external JSON Schema or stable CLI output format), add or extend an automated test that fails when table and source disagree.

```python
# ✅ DO: # test_doc_parity.py guarantees README.md and RULES.md match source and spec
# ❌ DO NOT: # Adding manual table of CLI flags or schemas with no automated parity test
```

- **[DOC-006] Prefer Deletion Over Accretion (SUGGESTION):**
  When updating docs, replace or delete stale bullets rather than appending parallel conflicting truths. Flag any doc that states contradictory rules.

```python
# ✅ DO: # Replaced outdated formatters.py reference with cli/ui/formatters/
# ❌ DO NOT: # Appended new rule while leaving old formatters.py text intact
```

- **[DOC-007] Canonical Terminology Invariant (SUGGESTION):**
  Adhere strictly to definitions in docs/agents/glossary.md. Do not conflate Task (linear steps only) vs Workflow (allows loop steps), Blueprint (unified document), Step, Run, Session, Sandbox, Checkpoint.

```python
# ✅ DO: 'Task blueprint containing only linear step definitions.'
# ❌ DO NOT: 'Task blueprint containing a loop block.'  # tasks are strictly linear
```

- **[CI-001] Pre-Commit Quality Suite Gate (BLOCKER):**
  Before committing, all five gates must pass: ruff format, ruff check, basedpyright src --level error (0 errors), inv complexity --paths <changed> --plain --failed (complexity <= 10), and inv test -c (coverage >= 80%).

```python
# ✅ DO: uv run inv test -c && ruff format . && ruff check . && basedpyright src --level error && inv complexity
# ❌ DO NOT: git commit -m 'fix' with a failing basedpyright or complexity error
```

- **[CI-002] Git and Pull Request Attribution Hygiene (BLOCKER):**
  Commit messages must be semantic, imperative, and contain NO AI trailers (Co-authored-by: Cursor, Co-authored-by: ...). PRs must have single responsibility and contain concise Why, Approach, and Linkage sections.

```python
# ✅ DO: feat(sandbox): add prune subcommand for stale sandboxes
# ❌ DO NOT:
feat: prune sandboxes

Co-authored-by: Cursor <cursor@cursor.sh>
```

- **[CI-003] Agentic Process State Declaration (WARNING):**
  Before executing commands or editing files, the agent must state: (1) The specific directive/doc governing this action, and (2) The target scope (e.g. specific test package or module).

```python
# ✅ DO:
Governing directive: docs/agents/testing.md
Target scope: tests/core/sandbox/test_lifecycle.py
# ❌ DO NOT: Running write_to_file without stating governing directive or target scope
```
