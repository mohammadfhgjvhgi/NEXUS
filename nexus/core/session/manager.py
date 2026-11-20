"""Session/conversation/task hierarchy manager (Final Build Plan §2.3).

Owns the strict hierarchy User → Conversation → Task → Session:

* task creation is **not** a state transition — tasks are born CREATED
  and the TaskEngine (§2.4) drives them afterwards;
* one active session per task at a time (opening a second raises
  :class:`SessionError`) — sessions never overlap, tasks never mix;
* restored tasks (loaded from persistence) register back here so the
  runtime can continue them (§2.6 exit criteria).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ...events import EventBus, EventName
from .models import (
    Conversation,
    Session,
    SessionError,
    Task,
    TaskPlan,
    User,
)


class SessionManager:
    """Manages the §2.3 hierarchy and emits ``task.created``."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._users: dict[str, User] = {}
        self._conversations: dict[str, Conversation] = {}
        self._tasks: dict[str, Task] = {}

    # ------------------------------------------------------------------ user

    def create_user(self, *, display_name: str = "User") -> User:
        user = User.create(display_name=display_name)
        self._users[user.id] = user
        return user

    def register_user(self, user: User) -> User:
        self._users[user.id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    # ---------------------------------------------------------- conversation

    def create_conversation(
        self, user: User | str, *, title: str = "Conversation"
    ) -> Conversation:
        user_id = user.id if isinstance(user, User) else user
        if isinstance(user, User):
            self.register_user(user)
        conversation = Conversation.create(user_id=user_id, title=title)
        self._conversations[conversation.id] = conversation
        return conversation

    def register_conversation(self, conversation: Conversation) -> Conversation:
        self._conversations[conversation.id] = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    # ------------------------------------------------------------------ task

    def create_task(
        self,
        conversation: Conversation,
        *,
        goal: str,
        prompt: str,
        scope: Mapping[str, Any] | None = None,
        workspace: str = "main",
        plan: TaskPlan | None = None,
        agents: Iterable[str] | None = None,
    ) -> Task:
        """Create a task under a conversation (state CREATED, publishes
        ``task.created``). Goal and prompt are required."""
        if not goal.strip() or not prompt.strip():
            raise ValueError("goal and prompt are required")
        task = Task.create(
            conversation_id=conversation.id,
            goal=goal,
            prompt=prompt,
            scope=scope,
            workspace=workspace,
            plan=plan,
            agents=agents,
        )
        conversation.add_task(task.id)
        self._tasks[task.id] = task
        self._bus.publish(
            EventName.TASK_CREATED,
            payload={"goal": task.goal, "workspace": task.workspace},
            task_id=task.id,
            conversation_id=conversation.id,
            source="nexus.session",
        )
        return task

    def register_task(self, task: Task) -> Task:
        """Register a task restored from persistence (§2.6 continuity)."""
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    # --------------------------------------------------------------- session

    def open_session(
        self, task: Task, *, context: Mapping[str, Any] | None = None
    ) -> Session:
        """Open the next session for a task (fails while one is active)."""
        active = task.active_session
        if active is not None:
            raise SessionError(
                f"task {task.id} already has an active session {active.id} — "
                "close it before opening a new one"
            )
        session = Session.begin(
            task_id=task.id,
            index=len(task.sessions) + 1,
            context=context,
        )
        task.sessions.append(session)
        task.touch()
        return session

    def close_session(
        self, task: Task, *, notes: str | None = None
    ) -> Session | None:
        """Close the active session of a task, if any."""
        active = task.active_session
        if active is None:
            return None
        active.end(notes=notes)
        task.touch()
        return active

    # ---------------------------------------------------------------- agents

    def attach_agent(self, task: Task, agent_id: str) -> bool:
        """Add an agent to the task's agent list; True when newly added."""
        if agent_id in task.agents:
            return False
        task.agents.append(agent_id)
        task.touch()
        return True

    def detach_agent(self, task: Task, agent_id: str) -> bool:
        if agent_id not in task.agents:
            return False
        task.agents.remove(agent_id)
        task.touch()
        return True
