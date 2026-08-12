"""CRUD helpers for task execution tracking in SQLite using TasksDb repository."""

from getworktree.core.db.models import RunStatus, TaskRunRecord
from getworktree.core.db.run_tracking import RunTrackingDb


class TasksDb(RunTrackingDb[TaskRunRecord]):
    """Repository managing task execution tracking CRUD operations in SQLite."""

    table = "tasks"
    record_cls = TaskRunRecord
    extra_columns = ("task_name",)

    def insert(
        self,
        session_id: str,
        task_name: str,
        status: RunStatus | str = RunStatus.RUNNING,
    ) -> TaskRunRecord:
        """Insert a task run record."""
        return super().insert(session_id, status=status, task_name=task_name)
