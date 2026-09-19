"""Domain entrypoint coordinator for Worktree doctor diagnostics."""

from pathlib import Path

from worktree.core.config.facade import Config
from worktree.core.config.models import WorktreeConfig
from worktree.core.doctor.models import (
    CheckCategory,
    DoctorContext,
    DoctorReport,
)
from worktree.core.doctor.services.registry import CheckRegistry, get_default_registry
from worktree.core.doctor.services.runner import DiagnosticRunner


class Doctor:
    """Domain entrypoint coordinator for Worktree doctor diagnostics."""

    def __init__(self, path: Path = Path("."), registry: CheckRegistry | None = None) -> None:
        """Initialize the coordinator's workspace root, defaulting its check registry to the built-in check set."""
        self.path = path.resolve()
        self.registry = registry if registry is not None else get_default_registry()

    def run_diagnostics(
        self,
        categories: list[CheckCategory] | None = None,
        config: WorktreeConfig | None = None,
    ) -> DoctorReport:
        """Run registered diagnostic checks and return aggregated DoctorReport."""
        active_config: WorktreeConfig | None = config
        if active_config is None:
            try:
                load_result = Config(self.path).load()
                if load_result.ok:
                    active_config = load_result.config
            except Exception:
                active_config = None

        context = DoctorContext(cwd=self.path, config=active_config)
        runner = DiagnosticRunner(registry=self.registry)

        return runner.run_checks(context=context, categories=categories)
