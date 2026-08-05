GITIGNORE_ENTRY = "\n# Worktree CLI cache and local databases\n/.worktree/\n"

BOOTSTRAP_SCHEMA_VERSION = 1

BOOTSTRAP_META_REL = ".meta/bootstrap.json"

# Wall-clock cap for internal git plumbing (sandbox lifecycle, patch apply,
# mutation baseline/capture, status/diff helpers). Distinct from trigger/agent
# timeouts; prevents a hung git child from wedging ``wt workflow run`` indefinitely.
GIT_SUBPROCESS_TIMEOUT_SECONDS = 120

REQUIRED_SUBDIRS = (
    ".meta",
    "loops",
    "sessions",
    "artifacts",
    "tmp",
    "logs",
)
