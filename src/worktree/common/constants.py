GITIGNORE_ENTRY = "\n# Worktree CLI cache and local databases\n/.worktree/\n"

BOOTSTRAP_SCHEMA_VERSION = 1

BOOTSTRAP_META_REL = ".meta/bootstrap.json"

# Wall-clock cap for internal git plumbing (sandbox lifecycle, patch apply,
# mutation baseline/capture, status/diff helpers). Distinct from trigger/agent
# timeouts; prevents a hung git child from wedging ``wt run`` indefinitely.
GIT_SUBPROCESS_TIMEOUT_SECONDS = 120

# @TODO: Is this still used?
REQUIRED_SUBDIRS = (
    ".meta",
    "sessions",
    "artifacts",
    "tmp",
    "logs",
)

# Maximum diff lines rendered before truncation in interactive terminals
DEFAULT_MAX_DIFF_LINES = 500

# @TODO: Do we need a maximum?
ON_FAILURE_MAX_RETRIES_MINIMUM = 1
ON_FAILURE_MAX_RETRIES_DEFAULT = 3
ON_FAILURE_BACKOFF_MS_MINIMUM = 0
ON_FAILURE_BACKOFF_MS_DEFAULT = 0
