"""CRUD helpers for workflow execution tracking in SQLite using WorkflowsDb repository."""

from getworktree.core.db.models import WorkflowRunRecord
from getworktree.core.db.run_tracking import RunTrackingDb


class WorkflowsDb(RunTrackingDb[WorkflowRunRecord]):
    """Repository managing workflow execution tracking CRUD operations in SQLite."""

    table = "workflows"
    record_cls = WorkflowRunRecord
    extra_columns = ("workflow_name", "branch_name")
