"""Bootstrap domain package."""

from worktree.common.constants import (
    BOOTSTRAP_META_REL,
    BOOTSTRAP_SCHEMA_VERSION,
    REQUIRED_SUBDIRS,
)
from worktree.core.bootstrap.facade import Bootstrap
from worktree.core.bootstrap.models import (
    BootstrapResult,
    DirEnsureOutcome,
    WorkspaceInitResult,
)
from worktree.core.bootstrap.services.bootstrap import (
    assert_writable,
    bootstrap_worktree,
    ensure_dir,
    load_existing_bootstrap_metadata,
    write_bootstrap_metadata,
)
from worktree.core.bootstrap.services.initialize import initialize_workspace

__all__ = [
    "BOOTSTRAP_META_REL",
    "BOOTSTRAP_SCHEMA_VERSION",
    "REQUIRED_SUBDIRS",
    "Bootstrap",
    "BootstrapResult",
    "DirEnsureOutcome",
    "WorkspaceInitResult",
    "assert_writable",
    "bootstrap_worktree",
    "ensure_dir",
    "initialize_workspace",
    "load_existing_bootstrap_metadata",
    "write_bootstrap_metadata",
]
