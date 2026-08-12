"""CRUD helpers for workflow execution tracking in SQLite using WorkflowsDb repository."""

from getworktree.core.db.models import RunStatus, WorkflowRunRecord
from getworktree.core.db.run_tracking import RunTrackingDb


class WorkflowsDb(RunTrackingDb[WorkflowRunRecord]):
    """Repository managing workflow execution tracking CRUD operations in SQLite."""

    table = "workflows"
    record_cls = WorkflowRunRecord
    extra_columns = ("workflow_name", "branch_name")

    def insert(
        self,
        session_id: str,
        workflow_name: str,
        branch_name: str,
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> WorkflowRunRecord:
        """Insert a workflow run record."""
        return super().insert(
            session_id,
            status=status,
            workflow_name=workflow_name,
            branch_name=branch_name,
        )
