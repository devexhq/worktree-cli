# Installation

Worktree (`wt`) can be installed using Python package managers or system installers.

## Recommended Installation

### Python / Pip

Install the package directly via `pip`:

```bash
pip install getworktree
```

To install with development dependencies:

```bash
pip install "getworktree[dev]"
```

To install with documentation build dependencies:

```bash
pip install "getworktree[docs]"
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
