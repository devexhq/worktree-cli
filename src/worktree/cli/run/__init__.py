"""The ``wt run`` CLI command package."""

from worktree.cli.run.app import register_run_command
from worktree.cli.run.commands.root import root_command

# Backward-compatible alias matching other command packages
run_command = root_command

__all__ = ["register_run_command", "root_command", "run_command"]
