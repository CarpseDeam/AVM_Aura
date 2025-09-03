# services/mission_log_service.py
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from event_bus import EventBus
from events import MissionLogUpdated, ProjectCreated

if TYPE_CHECKING:
    from core.managers import ProjectManager

logger = logging.getLogger(__name__)
MISSION_LOG_FILENAME = "mission_log.json"


class MissionLogService:
    """
    Manages the state of the Mission Log (to-do list) for the active project.
    """

    def __init__(self, project_manager: "ProjectManager", event_bus: EventBus):
        self.project_manager = project_manager
        self.event_bus = event_bus
        self.tasks: List[Dict[str, Any]] = []
        self._next_task_id = 1
        self._initial_user_goal = ""
        self.event_bus.subscribe("project_created", self.handle_project_created)
        logger.info("MissionLogService initialized.")

    def handle_project_created(self, event: ProjectCreated):
        """Resets and loads the log when a new project becomes active."""
        logger.info(f"ProjectCreated event received. Resetting and loading mission log for '{event.project_name}'.")
        self.load_log_for_active_project()

    def _get_log_path(self) -> Optional[Path]:
        """Gets the path to the mission log file for the active project."""
        if self.project_manager.active_project_path:
            return self.project_manager.active_project_path / MISSION_LOG_FILENAME
        return None

    def _save_and_notify(self):
        """Saves the current list of tasks to disk and notifies the UI."""
        data_to_save = {
            "initial_goal": self._initial_user_goal,
            "tasks": self.tasks
        }

        # Always emit the event first to update UI immediately
        self.event_bus.emit("mission_log_updated", MissionLogUpdated(tasks=self.get_tasks()))
        logger.debug(f"UI notified of mission log update. Task count: {len(self.tasks)}")

        log_path = self._get_log_path()
        if not log_path:
            logger.warning("No active project path - mission log not saved to disk.")
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2)
            logger.debug(f"Mission Log saved to disk at {log_path}.")
        except IOError as e:
            logger.error(f"Failed to save mission log to {log_path}: {e}")

    def load_log_for_active_project(self):
        """Loads the mission log from disk for the currently active project."""
        log_path = self._get_log_path()
        self.tasks = []
        self._next_task_id = 1
        self._initial_user_goal = ""

        if log_path and log_path.exists():
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    self.tasks = saved_data.get("tasks", [])
                    self._initial_user_goal = saved_data.get("initial_goal", "")
                if self.tasks:
                    valid_ids = [task.get('id', 0) for task in self.tasks if task.get('id')]
                    self._next_task_id = max(valid_ids) + 1 if valid_ids else 1
                logger.info(
                    f"Successfully loaded Mission Log for '{self.project_manager.active_project_name}' with {len(self.tasks)} tasks.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse mission log at {log_path}: {e}. Starting fresh.")
                self.tasks = []
        else:
            logger.info("No existing mission log found for this project. Starting fresh.")
        self._save_and_notify()

    def set_initial_plan(self, plan_steps: List[str], user_goal: str):
        """Clears all tasks and sets a new plan, storing the original user goal."""
        self.tasks = []
        self._next_task_id = 1
        self._initial_user_goal = user_goal

        self.add_task(
            description="Index the project to build a contextual map.",
            tool_call={"tool_name": "index_project_context", "arguments": {"path": "."}},
            notify=False
        )

        for step in plan_steps:
            self.add_task(description=step, notify=False)

        self._save_and_notify()
        logger.info(f"Initial plan with {len(self.tasks)} steps has been set.")

    def add_task(self, description: str, tool_call: Optional[Dict] = None, notify: bool = True) -> Dict[str, Any]:
        """Adds a new task to the mission log."""
        if not description or not description.strip():
            raise ValueError("Task description cannot be empty.")

        new_task = {
            "id": self._next_task_id,
            "description": description.strip(),
            "done": False,
            "tool_call": tool_call,
            "last_error": None
        }

        self.tasks.append(new_task)
        self._next_task_id += 1
        logger.info(f"Added task {new_task['id']}: '{description.strip()}'")

        if notify:
            self._save_and_notify()

        return new_task

    def mark_task_as_done(self, task_id: int) -> bool:
        """Marks a specific task as completed."""
        if not isinstance(task_id, int) or task_id <= 0:
            logger.error(f"Invalid task_id: {task_id}. Must be a positive integer.")
            return False

        for task in self.tasks:
            if task.get('id') == task_id:
                if task.get('done'):
                    logger.info(f"Task {task_id} was already marked as done.")
                    return True

                task['done'] = True
                task['last_error'] = None
                logger.info(f"Successfully marked task {task_id} as done: '{task.get('description', 'Unknown')}'")
                self._save_and_notify()
                return True

        logger.error(
            f"Attempted to mark non-existent task {task_id} as done. Available task IDs: {[t.get('id') for t in self.tasks]}")
        return False

    def get_tasks(self, done: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Returns a copy of the current tasks, optionally filtered by done status."""
        if done is None:
            return [task.copy() for task in self.tasks]
        return [task.copy() for task in self.tasks if task.get('done') == done]

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Returns a specific task by its ID."""
        for task in self.tasks:
            if task.get('id') == task_id:
                return task.copy()
        return None

    def update_task_error(self, task_id: int, error_message: str) -> bool:
        """Updates the last_error field for a specific task."""
        for task in self.tasks:
            if task.get('id') == task_id:
                task['last_error'] = error_message
                self._save_and_notify()
                logger.info(f"Updated error for task {task_id}: {error_message}")
                return True
        logger.warning(f"Could not find task {task_id} to update error.")
        return False

    def clear_all_tasks(self):
        """Removes all tasks from the log."""
        if self.tasks:
            task_count = len(self.tasks)
            self.tasks = []
            self._next_task_id = 1
            self._initial_user_goal = ""
            self._save_and_notify()
            logger.info(f"Cleared {task_count} tasks from the Mission Log.")

    def replace_tasks_from_id(self, start_task_id: int, new_plan_steps: List[str]):
        """
        Replaces a block of tasks starting from a given ID with a new plan.
        The failed task and all subsequent tasks are removed.
        """
        start_index = -1
        for i, task in enumerate(self.tasks):
            if task.get('id') == start_task_id:
                start_index = i
                break

        if start_index == -1:
            logger.error(f"Could not find task with ID {start_task_id} to start replacement.")
            return

        # Remove the failed task and all subsequent tasks
        removed_count = len(self.tasks) - start_index
        self.tasks = self.tasks[:start_index]

        # Add the new plan steps
        for step in new_plan_steps:
            self.add_task(description=step, notify=False)

        self._save_and_notify()
        logger.info(
            f"Replaced {removed_count} tasks from ID {start_task_id} with new plan of {len(new_plan_steps)} steps.")

    def get_initial_goal(self) -> str:
        """Returns the initial user goal that started the mission."""
        return self._initial_user_goal

    def get_log_as_string_summary(self) -> str:
        """Returns a concise string summary of the mission log state."""
        tasks = self.get_tasks()
        if not tasks:
            return "State: EMPTY. No tasks in the mission log."

        pending = [t for t in tasks if not t['done']]
        done = [t for t in tasks if t['done']]

        if pending:
            next_task_desc = pending[0]['description'][:50] + ("..." if len(pending[0]['description']) > 50 else "")
            return f"State: IN_PROGRESS. {len(done)} tasks done, {len(pending)} tasks pending. Next up: '{next_task_desc}'"
        else:
            return f"State: COMPLETE. All {len(done)} tasks are done."

    def get_task_statistics(self) -> Dict[str, int]:
        """Returns statistics about the current tasks."""
        tasks = self.get_tasks()
        return {
            "total": len(tasks),
            "completed": len([t for t in tasks if t.get('done')]),
            "pending": len([t for t in tasks if not t.get('done')]),
            "with_errors": len([t for t in tasks if t.get('last_error')])
        }