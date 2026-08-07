# Installation

Worktree (`wt`) can be installed using Python package managers or system installers.

## Recommended Installation

### Python / Pip

Install the package directly via `pip`:

```bash
pip install getworktree
```

Using `pipx` (isolated application environments):

```bash
pipx install getworktree
```

Using `uv`:

```bash
uv tool install getworktree
```

### Local Development / Source Installation

To install in editable mode with development dependencies:

```bash
uv sync --all-extras
# Or using uv pip:
# uv pip install -e ".[dev]"
```

To install with documentation dependencies:

```bash
uv sync --extra docs
# Or: uv pip install -e ".[docs]"
```

## Alternative Install Methods

### Homebrew (macOS / Linux)

```bash
brew tap getworktree/tap
brew install wt
```

### Script / Curl

```bash
curl -fsSL https://getworktree.io/install.sh | sh
```

## Verification

Verify that `wt` is installed and check your version:

```bash
wt --version
```

Output:

```text
wt version 0.1.1
```
