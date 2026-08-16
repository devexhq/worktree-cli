"""CRUD helpers for task execution tracking in SQLite using TasksDb repository."""

from getworktree.core.db.models import TaskRunRecord
from getworktree.core.db.run_tracking import RunTrackingDb


class TasksDb(RunTrackingDb[TaskRunRecord]):
    """Repository managing task execution tracking CRUD operations in SQLite."""

    table = "tasks"
    record_cls = TaskRunRecord
    extra_columns = ("task_name",)
