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
  Test structure mirrors src/worktree/ 1:1 under tests/, one test file per source module, and every test directory carries an __init__.py because basenames repeat across the tree. Three mappings are fixed: src/worktree/common/<m>.py to tests/common/test_<m>.py, src/worktree/core/<domain>/<m>.py to tests/core/<domain>/test_<m>.py, and src/worktree/cli/ui/formatters/<domain>/<name>.py to tests/cli/ui/formatters/<domain>/test_<name>.py. The single collapse exception is CLI command actions: src/worktree/cli/<command>/commands/*.py map together to tests/cli/commands/test_<command>.py. Any source module with no test file must appear in the PARITY_EXEMPT list in tests/lint/ with a justification, so the gap is visible rather than implicit. Grouping several formatters or domains into one part-numbered file is prohibited.

```python
# ✅ DO: src/worktree/cli/ui/formatters/status/status.py -> tests/cli/ui/formatters/status/test_status.py
# ❌ DO NOT: tests/cli/formatters/test_command_formatters_part1.py  # 12 formatters in one unmirrored file
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

- **[TEST-004] CLI Tier Matrix and Handler Test Necessity (BLOCKER):**
  Every CLI command action requires *CliIntegrationTests invoking runner.invoke to pin option and argument binding, exit codes, and dispatcher output, covering four scenarios: happy path exit 0, failure path with the expected non-zero exit code, --format json emitting the wire schema, and any interactive confirmation or abort branch. *RootTests calling the handler directly with a CliContext are required only when the handler owns logic the domain layer does not: input coercion, branch selection across services, result composition from more than one call, or an interactive abort path. A pass-through handler gets no root test. A root test may never restate a contract already asserted under tests/core/ for the same result type.

```python
# ✅ DO: class ConfigSetRootTests: ...  # handler owns string-to-bool coercion, so it earns a root test
# ❌ DO NOT: class ConfigShowRootTests: ...  # pass-through handler re-asserting the ConfigLoadResult from tests/core/config/
```

- **[TEST-005] Formatter Presentation Contract Protocol (BLOCKER):**
  Every formatter under cli/ui/formatters/<domain>/ is tested in its own file at tests/cli/ui/formatters/<domain>/test_<name>.py against three contracts built from FormatterCase: view model transform equality, JSON wire format as an exact literal dict pinned at both a fully populated and an empty or sparse boundary state, and a Rich render at pinned width 160 asserting only semantic values taken from case.view. Where the formatter has no derived view model, meaning transform is provably the identity and the declared view type is the input event type, the transform test is omitted and the remaining two contracts are mandatory; an alias such as SomeView = SomeEvent must not be introduced to manufacture a third test. Never assert to_json_serializable(data) == transform(data).model_dump(), and never assert a label, border, glyph, padding, or full sentence in the render test.

```python
# ✅ DO: assert formatter.to_json_serializable(data) == {"health": "ok", "warnings": []}  # exact literal
# ❌ DO NOT: ErrorPanelView = ErrorPanelEvent  # alias so an identity transform can be asserted
```

- **[TEST-006] Parameterization-First for Sibling Variations (BLOCKER):**
  Parameterization is the primary approach for testing variations of the same contract or function. Never duplicate test functions across input variants, polymorphic target types (e.g. BaseModel vs dict), or invalid payload permutations. Never use `for` loops or stacked assertions over scenarios. Use `@pytest.mark.parametrize` with explicit `pytest.param(..., id="...")` labels. Separate `def test_*` methods are reserved for fundamentally distinct lifecycles, differing fixture requirements, or divergent assertion contracts.

```python
# ✅ DO: @pytest.mark.parametrize("target", [pytest.param(model, id="model"), pytest.param(dict, id="dict")])
# ❌ DO NOT: def test_eval_model(self): ...; def test_eval_dict(self): ...  # duplicate sibling methods
```

- **[TEST-007] No Unasserted Fields on the Result Under Test (BLOCKER):**
  Every field of the result under test is asserted. The result under test is the Pydantic model or BaseResult returned by a core service or domain entrypoint, or a formatter's JSON wire payload; click.testing.Result is not one, so asserting res.exit_code is required by TEST-004 and TEST-017 rather than forbidden here. Satisfy the invariant with assert_model_equal(result, Expected(...)) naming every field, or for a wire payload an exact literal dict. Asserting a subset of the result and stopping is prohibited: a piecewise assertion is blind to every field it does not name, which is where the regression you did not anticipate lands. Piecewise assertions are permitted alongside a whole-object comparison, never instead of one, and on values that are not the result under test (exit codes, preconditions, an incidental single-column read). Non-determinism is removed at its seam first: inject the clock and the id factory per TEST-011 so a timestamp or generated id is a literal the test can state. Only for a value the test genuinely cannot own (a real git SHA, an OS pid, an id minted by the database) use a matcher from tests/harness/matchers.py at that field's own position, which still pins the value's type or shape. assert_model_equal has no exclude parameter; a waiver expressed outside the comparison is prohibited because a reader cannot see it at the field and it asserts nothing about the waived value. An expected object that leaves a field to its default is rejected, since a changed default would otherwise pass unnoticed.

```python
# ✅ DO: assert_model_equal(result, SandboxCreateResult.model_construct(status=CREATED, sandbox_id=ANY_UUID, head_sha=ANY_GIT_SHA, worktree_path=tmp_path / 'alpha', created_at=ANY_DATETIME, errors=[]))
# ❌ DO NOT: assert_model_equal(result, expected, exclude={'errors'})  # invisible waiver, asserts nothing about errors
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
  No hardcoded sleeps in test bodies. Retry and backoff intervals use VirtualClock or monkeypatch the clock at the module boundary (time.monotonic, asyncio.sleep), and a retry test asserts the resulting schedule rather than that a retry eventually happened. Inject the clock and the id factory anywhere their output reaches a result field, so timestamps and generated ids are literals a test can state rather than values TEST-007 has to waive with a matcher. Waiting on an operating system event that has no virtual equivalent, such as a process group being reaped after SIGKILL, is permitted only through a shared harness helper that owns the poll interval and deadline; tests must not open-code a poll loop. Registering spawned processes with the harness process registry is mandatory so a failing test cannot leak a process group.

```python
# ✅ DO: assert wait_pid_dead(child_pid) is True
# ❌ DO NOT:
while time.monotonic() < deadline:
    time.sleep(0.05)  # open-coded poll loop in a test module
```

- **[TEST-012] Rich Render Width Pinning (BLOCKER):**
  render_rich(renderable, width=160) is the only supported way to capture rendered output, and console width for rendered assertions is authoritatively pinned to 160. Tests must not rely on ambient terminal size or in-process os.environ['COLUMNS'] mutations. A render assertion checks semantic values carried by the view model, such as an identifier, count, or status token; it never checks a panel title, field caption, border glyph, padding, or prose sentence, because those are layout and change without any contract changing.

```python
# ✅ DO:
rendered = render_rich(formatter.to_rich(data))
assert 'wf_abcdef12' in rendered  # view value, not a caption
# ❌ DO NOT: assert 'Session ID' in rendered  # panel caption, changes with layout and pins no contract
```

- **[TEST-013] No Sole Consumer Tests (BLOCKER):**
  No test may be the sole consumer of a production symbol. If deleting the test would make production code unreachable, the production code is dead and both go. The same applies to the test harness: a builder method, fixture, or assertion helper whose only caller is its own verification test is dead harness. Delete the capability rather than testing it, and prove harness behavior through the first domain test that needs it.

```python
# ✅ DO: # WorkspaceBuilder.with_git() used by tests/core/sandbox/test_services.py
# ❌ DO NOT: # StepBuilder.with_retry() exercised only by tests/harness/test_builders.py
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

- **[TEST-016] Marker Taxonomy Fidelity (BLOCKER):**
  Every test carries exactly one primary marker reflecting its real execution cost, optionally combined with slow. unit covers in-memory logic including reads and writes under tmp_path. integration is reserved for subprocess git, on-disk SQLite transactions, and cross-process file locks. cli covers Typer runner invocation. invariant is reserved for tests/lint/ static analysis. slow is additive for process group signal escalation, real timeouts, and network boundaries. Declare the marker with a module-level pytestmark when the whole module shares a tier; when a module mixes tiers, such as a CLI file holding both handler and runner tests, declare markers at class level so each tier is selectable. Writing JSON under tmp_path does not make a test integration.

```python
# ✅ DO: pytestmark = pytest.mark.unit  # writes config.json under tmp_path, no git or sqlite
# ❌ DO NOT: pytestmark = pytest.mark.cli  # module-level, hiding *RootTests from `pytest -m unit`
```

- **[TEST-017] CLI Runner Assertion Boundary (BLOCKER):**
  CLI runner tests assert wiring and machine contracts only: exit codes, --format json payloads as exact literal dicts, and resulting disk or git state. A published error code token such as CONFIG_SCHEMA_INVALID may be asserted present in output because it is a documented contract. Panel titles, status labels, field captions, prose, glyphs, and padding must not be asserted; those are presentation contracts belonging to the formatter test for that view under tests/cli/ui/formatters/. Never assert help text wording; assert command registration and option names through Click metadata instead.

```python
# ✅ DO:
assert res.exit_code == 1
assert "CONFIG_SCHEMA_INVALID" in res.stdout  # published error code
# ❌ DO NOT: assert "Status: valid with warnings" in res.stdout  # human label scraped in a runner test
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
  When a field table is genuinely unavoidable, meaning it is the specification for an external JSON Schema or a stable CLI output format, add or extend an automated test under tests/lint/ that fails when the table and the source disagree. The test must exist in the tree at the moment the doc claim lands, and the doc must name it by path. Citing a parity test that has not been written is a DOC-008 breach, not a pending task.

```python
# ✅ DO: # tests/lint/test_architecture_boundaries.py exists and is named by the doc claim it backs
# ❌ DO NOT: # "enforced by tests/lint/test_doc_parity.py" where that module is nowhere in the tree
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

- **[DOC-008] Verifiable Doc and Rule Claims (BLOCKER):**
  A doc, skill, or rule sentence asserting that something is enforced, gated, or checked must name the enforcing artifact by path, and that path must resolve to a file in the tree. The same applies to any helper, fixture, builder, or assertion function a doc instructs an implementer to use: the symbol exists before the instruction ships. Documentation of behavior that is planned rather than built is prohibited, including in rule examples, because an exemplar is copied more often than the guideline is read. When a claim becomes false, the fix is to delete or correct the sentence in the same change, never to leave it as aspiration.

```python
# ✅ DO: # "COLUMNS is pinned to 160 by [tool.pytest_env] in pyproject.toml" - resolvable and true
# ❌ DO NOT: # "enforced by tests/lint/test_doc_parity.py" in AGENTS.md, where the module does not exist
```

- **[CI-001] Pre-Commit Quality Suite Gate (BLOCKER):**
  Before committing, all five gates must pass: ruff format, ruff check, basedpyright src tests --level error with zero errors, inv complexity with complexity at or under 10, and inv test -c meeting the coverage floor configured in pyproject.toml under [tool.coverage.report] fail_under. That floor is the contract, it ratchets upward only as real contract tests land, and it is never lowered to make a commit pass. Coverage is a regression backstop, not a target: do not add tests to raise the percentage, and read a coverage drop caused by deleting duplicated or dead tests as a success.

```python
# ✅ DO: uv run inv test -c && ruff format . && ruff check . && basedpyright src tests --level error && inv complexity
# ❌ DO NOT: # fail_under lowered so a commit can pass, or tests added purely to reach a percentage
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

- **[CI-004] Mechanical Enforcement Parity (BLOCKER):**
  A BLOCKER rule that can be checked mechanically must have an executing check: an invariant test under tests/lint/, a prek hook, or a CI step. A declared gate whose configuration disables it, such as a coverage floor of zero or a type checker present in no hook and no workflow, counts as unenforced and must be either wired up or downgraded to a review-time WARNING. An invariant check must prove its own scope with a regression test shaped like the code it polices, and lands green by carrying an explicit burn-down allowlist of known violators; allowlist entries shrink and are never added to. CI must exercise the marker taxonomy so the tiers have a consumer and cannot drift.

```python
# ✅ DO: # TEST-016 enforced by tests/lint/test_marker_taxonomy.py plus a CI job per marker
# ❌ DO NOT: # Scanner walks only tree.body functions, so class-based tests are never inspected
```
