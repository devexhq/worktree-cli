"""CRUD helpers for task execution tracking in SQLite using TasksDb repository."""

from worktree.core.db.models import TaskRunRecord
from worktree.core.db.run_tracking import RunTrackingDb


class TasksDb(RunTrackingDb[TaskRunRecord]):
    """Repository managing task execution tracking CRUD operations in SQLite."""

    table = "tasks"
    record_cls = TaskRunRecord
    extra_columns = ("task_name",)
