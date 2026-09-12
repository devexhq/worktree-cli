# Conventions checklist

Every mechanical rule in `docs/agents/code-conventions.md`, `docs/agents/testing.md`, and `docs/agents/architecture.md` that a reviewer must check by eye, because no linter in this repo enforces it.

Run this as a sweep over the changed hunks, not as a vibe check. A finding cites the rule it breaks.

## Naming (the most-missed category)

- **Readability first.** Check every new or renamed identifier (locals, parameters, attributes, fixtures, loop variables) against `docs/agents/code-conventions.md#variable-naming`. Code must read clearly and naturally.
- **Single-letter variables and standard iteration constructs:** Permitted in comprehensions and generator expressions (`p`, `x`, `i`, `v`, `c`), as well as standard iteration idioms (`k, v` in dict iteration, `i, v` in enumerate).
- **Commonly accepted abbreviations allowed:** Standard abbreviations that keep code concise without sacrificing readability are permitted: `req`, `res`, `fn` / `fn_node`, `idx`, `mod` / `mod_name`, `loc`, `tmp` / `temp`, `str`, `arr`, `num`, `len`, `val`, `msg`, `exc`, `rel_path`, `fs`, `cwd`, `db`, `ctx`.
- **Disallow cryptic or arbitrary truncations:** Reject abbreviations that obscure meaning or force guessing (e.g. `val_res` -> `validation_result`, `err_msg` -> `error_message`, arbitrary truncations like `acc` when ambiguous).
- Naming hazard to watch for: `core/runtime/engine.py` (`run_steps`) and `core/engine/engine.py` (`Engine`) are different modules. Check that a new import targets the intended one.

## Models and results

- Scoped exceptions allowing non-strict model configuration (`extra: "ignore"` on hand-authored YAML models) must carry a justifying comment.
- A failable operation returns a `BaseResult` subclass with a `status` `StrEnum`, and inherits `warnings` / `errors` / `fixes`; callers check `.ok` and render `.errors`, they do not catch exceptions.
- Every status enum value is reachable from production and covered by a test.
- Error, warning, and fix strings are built with inline f-strings or literals at the call site. No private single-message formatting wrapper.

## Placement and boundaries

- New domain types in `core/<domain>/models.py`; imperative operations in `core/<domain>/services/<verb>.py`; domain exceptions in `exceptions.py`; the single public entry point in `<domain>.py` (e.g., `prune.py`). No logic at a package root, no public model defined in `services/`, no extension of the flat `config/` / `db/` layout to a new domain.
- Import direction: `common/` -> `core/{db,git,sandbox,catalog,inputs,patch,history,diff,status}/` -> `core/agents/` -> `core/step/` -> `{core/runtime/, core/blueprint/}` -> `core/engine/` -> `cli/`. Never upward.
- Specific must-nots: `common/` imports no `core/` or `cli/`; `core/` and `common/` import no `cli/` and no `rich`; `inputs/` imports no step, runtime, agents, patch; `patch/` imports no agents, step, runtime; `agents/` imports no step or runtime; `step/` imports no runtime; `runtime/` imports no blueprint, engine, cli; `blueprint/` imports no runtime, engine, cli; `engine/` imports no cli.
- Shared table builders go in the domain's `common.py`.
- CLI commands take `CliContext`, return the core `*Result`, and emit through `ui_dispatcher.dispatch(result, output_format=...)`. No business logic, DB query, or filesystem scan in a CLI package.

## Functions and control flow

- Avoid God functions; distinct logical phases (setup, validate, persist, return) separated by a blank line, cohesive lines kept together.
- No test seam in a production signature: a parameter, kwarg, or callback production never reads is dead code.

## Writes and output

- No in-place config or state write. Use `Filesystem.atomic_write_json` / `atomic_write_text` (tmp sibling, flush, `os.fsync`, `Path.replace`).
- Output routing: `ui_dispatcher.dispatch(result)` handles terminal output. Check by hand for `console.print`, `input`, or `typer.confirm` which bypass dispatcher.

## Typing and suppressions

- `-> Any` on a public function is a defect unless the value is genuinely unconstrained. Prefer `object` for values only stored, compared, or passed through.
- `Any` is permitted only in: a Pydantic `mode="before"` validator signature, a `dict[str, Any]` at a serialization boundary, a value read from a user document and only compared, and `**kwargs: Any` on a non-inspecting pass-through.
- `Any` is banned when it dodges an import boundary, acts as a test seam, replaces a model that already exists, fills a third-party override (`ctx: Any` for `click.Context`), or fills a generic the code already knows (`Popen[Any]`).
- `# pyright: ignore[rule]` is permitted only for an intentional ill-typed test input whose subject is the raised error, a third-party stub conflict (the SQLModel `__tablename__` case), or a platform-gated import, and always with a one-line reason. Silencing `reportCallIssue`, `reportArgumentType`, or `reportIncompatibleVariableOverride` is a defect: the fixture, annotation, or override is wrong.

## Encapsulation and compatibility

- Expose public query properties (`is_enabled`, `has_*`) instead of referencing private state from external callers.
- Backwards compatibility is owed only to CLI surface (commands, subcommands, arguments, flags), user config and blueprint YAML keys, and stable machine-readable output. An internal alias, compatibility property, or shim in `common/`, `core/`, or `cli/` is a finding; callers should have been updated instead.
- Greenfield default: no dual code path or deprecation window unless the issue demanded one.

## Tests

Structure:

- Path mirrors `src/worktree/` under `tests/`, `__init__.py` in every test directory, and a moved module's test moves with it.
- One test file per source module. Class naming is `*Tests`; standalone `test_*` functions are preferred over either convention. `tests/core/**` never imports `worktree.cli.*`.
- Name format `test_<condition>_<outcome>`. Banned as having no outcome: `test_ok`, `test_success`, `test_present`, `test_missing`, `test_blank`, `test_basic`, `test_default`, `test_works`, `test_timeout`, `test_no_op`, `test_help`. A `should` prefix is filler, not an outcome.
- Per command, both `*RootTests` (direct handler call with `CliContext`) and `*CliIntegrationTests` (`runner.invoke`) exist.
- Tier 1 asserts the returned `BaseResult` and real side effects with no mocks beyond process and network boundaries. Tier 2 is **exactly two tests per formatter**: `to_json_serializable` as an exact dict, and a Rich render at a pinned width asserting only model-derived values (never a label, border, glyph, padding, or sentence). Tier 3 is four thin `CliRunner` tests per command (exit 0, a failure path with the right non-zero exit, `--output-format json` parses, any confirm/abort path). Tier 4 is `tests/lint/` invariants.

Assertions:

- One test asserts one behavior; multiple scenarios use `@pytest.mark.parametrize`, never a `for` loop and never four asserts in a row.
- Compare the object (`result == Expected(...)` or `result.model_dump() == {...}`), not eight fields.
- A test double must be a type production actually passes, or implement a Protocol production is typed against. A stub whose interface is the union of a `hasattr` chain guarantees test and production take different paths.
- A stored callback is not a tested seam: assert it fires from the production path.
- No test may be the sole consumer of a production symbol. No assertion on private state or import of an underscore-prefixed symbol.
- Machine-readable output byte-exact; human-readable output by data presence only. Never assert help text wording, except the `wt --help` versus `README.md` check.
- `is not None` alone means the test is unfinished. `isinstance` only when it distinguishes two real code paths.
- Every branch of a factory, dispatcher, or `elif` chain is covered; a covered line in a two-branch function proves nothing.
- No hardcoded sleeps: monkeypatch the clock.
- Test helpers and fixtures are annotated as tightly as production (`Iterator[GitFileSystem]`, not `None`); a `MagicMock` in a signature is the same finding as a hand-rolled stub.
- A name that overstates what the body checks is worse than no test. A copied test changes its **inputs**, not just its name.

Fixtures:

- Prefer the real `git_fs` / `fs` fixtures and real git over mocks. `render_rich(renderable, width=...)` is the only supported way to capture rendered output.
- Module-specific setup stays local; an exactly duplicated fixture is promoted to `tests/conftest.py` or `tests/helpers.py`. Fixtures yield plain tuples or dataclasses, not opaque harnesses, and perform no hidden assertions.
- Establish a valid baseline in the fixture and mutate it inline in the edge-case test, rather than adding near-identical fixtures or boolean switches.
- Coverage is a regression backstop: a test written to lift the percentage is a finding, and a coverage drop from deleting dead code is a success.
