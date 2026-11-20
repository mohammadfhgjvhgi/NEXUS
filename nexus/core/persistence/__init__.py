"""NEXUS Task Persistence package (Final Build Plan §2.5)."""

from .repository import TaskRepository, TaskSummary
from .serializer import (
    TASK_RECORD_SCHEMA,
    TASK_RECORD_VERSION,
    PersistenceError,
    task_from_record,
    task_to_record,
)

__all__ = [
    "TASK_RECORD_SCHEMA",
    "TASK_RECORD_VERSION",
    "PersistenceError",
    "TaskRepository",
    "TaskSummary",
    "task_from_record",
    "task_to_record",
]
