"""Background task manager for non-blocking long-running operations.

Uses threading to run tasks off Streamlit's main script thread.
Results are stored in a thread-safe dict and picked up by a
@st.fragment poller that writes them into st.session_state.

Each Streamlit session gets its own TaskManager instance (stored in
st.session_state) so that concurrent browser tabs never interfere.

A generation counter on every submit prevents stale threads from
overwriting newer results after clear()+re-submit.

Usage:
    from src.task_manager import task_manager

    # Submit a task (non-blocking)
    task_manager.submit("prediction", _run_prediction_sync, args=(query,))

    # Check status
    task_manager.status("prediction")  # "pending" | "running" | "complete" | "failed"

    # Get result (thread-safe)
    result = task_manager.get_result("prediction")
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class TaskInfo:
    task_id: str
    label: str  # Human-readable label for notifications
    generation: int = 0  # Monotonic counter — prevents stale thread overwrites
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    submitted_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    # Which session state keys to write the result into
    target_keys: dict[str, str] = field(default_factory=dict)


class TaskManager:
    """Thread-safe background task manager (one instance per session)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskInfo] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._generation: int = 0

    def submit(
        self,
        task_id: str,
        fn: Callable,
        args: tuple = (),
        kwargs: dict | None = None,
        label: str = "",
        target_keys: dict[str, str] | None = None,
    ) -> None:
        """Submit a task to run in a background thread.

        Args:
            task_id: Unique identifier for this task.
            fn: Callable to execute (must be sync, not async).
            args: Positional arguments for fn.
            kwargs: Keyword arguments for fn.
            label: Human-readable label for toast notifications.
            target_keys: Mapping of result dict keys to session state keys.
                         e.g. {"pdb": "prediction_result"} means
                         result["pdb"] -> st.session_state["prediction_result"]
                         Use "__direct__" as key to store the entire result.
        """
        kwargs = kwargs or {}
        target_keys = target_keys or {}

        with self._lock:
            self._generation += 1
            gen = self._generation

            info = TaskInfo(
                task_id=task_id,
                label=label or task_id,
                generation=gen,
                status=TaskStatus.RUNNING,
                target_keys=target_keys,
            )
            self._tasks[task_id] = info

        thread = threading.Thread(
            target=self._worker,
            args=(task_id, gen, fn, args, kwargs),
            daemon=True,
            name=f"lumi-task-{task_id}-g{gen}",
        )
        with self._lock:
            self._threads[task_id] = thread
        thread.start()

    def _worker(
        self,
        task_id: str,
        generation: int,
        fn: Callable,
        args: tuple,
        kwargs: dict,
    ):
        """Thread worker — only writes result if generation still matches."""
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                info = self._tasks.get(task_id)
                if info and info.generation == generation:
                    info.status = TaskStatus.COMPLETE
                    info.result = result
                    info.completed_at = time.time()
        except Exception as e:
            with self._lock:
                info = self._tasks.get(task_id)
                if info and info.generation == generation:
                    info.status = TaskStatus.FAILED
                    info.error = f"{type(e).__name__}: {e}"
                    info.completed_at = time.time()

    def status(self, task_id: str) -> TaskStatus | None:
        """Get the status of a task. Returns None if task doesn't exist."""
        with self._lock:
            info = self._tasks.get(task_id)
            return info.status if info else None

    def get_result(self, task_id: str) -> Any:
        """Get the result of a completed task."""
        with self._lock:
            info = self._tasks.get(task_id)
            if info and info.status == TaskStatus.COMPLETE:
                return info.result
            return None

    def get_error(self, task_id: str) -> str | None:
        """Get the error message of a failed task."""
        with self._lock:
            info = self._tasks.get(task_id)
            if info and info.status == TaskStatus.FAILED:
                return info.error
            return None

    def pop_completed(self) -> list[TaskInfo]:
        """Pop all completed/failed tasks (for the poller to process).

        Returns a list of TaskInfo objects and removes them from the manager.
        """
        with self._lock:
            finished = [
                info for info in self._tasks.values()
                if info.status in (TaskStatus.COMPLETE, TaskStatus.FAILED)
            ]
            for info in finished:
                self._tasks.pop(info.task_id, None)
                self._threads.pop(info.task_id, None)
            return finished

    def active_tasks(self) -> list[TaskInfo]:
        """Get all currently running tasks (for UI display)."""
        with self._lock:
            return [
                info for info in self._tasks.values()
                if info.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ]

    def has_active(self) -> bool:
        """Check if any tasks are currently running."""
        with self._lock:
            return any(
                info.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
                for info in self._tasks.values()
            )

    def clear(self):
        """Clear all tasks (e.g. on new query).

        Running threads will still finish but their results will be
        discarded because the generation check in _worker will fail.
        """
        with self._lock:
            self._generation += 1  # Invalidate all in-flight workers
            self._tasks.clear()
            self._threads.clear()


class _SessionProxy:
    """Proxy that routes every attribute access to a per-session TaskManager.

    On each access it looks up (or creates) a TaskManager in
    ``st.session_state["_task_manager"]``.  This keeps concurrent
    browser sessions fully isolated while remaining a drop-in
    replacement for the old module-level singleton.
    """

    def _real(self) -> TaskManager:
        import streamlit as st
        if "_task_manager" not in st.session_state:
            st.session_state["_task_manager"] = TaskManager()
        return st.session_state["_task_manager"]

    def __getattr__(self, name: str):
        return getattr(self._real(), name)


# Drop-in replacement — existing ``from src.task_manager import task_manager``
# keeps working but now routes to the per-session instance.
task_manager = _SessionProxy()
