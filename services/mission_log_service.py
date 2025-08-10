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
        log_path = self._get_log_path()
        if not log_path:
            logger.debug("Cannot save mission log, no active project path set yet.")
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2)
            # Emit the update *after* successfully saving.
            self.event_bus.emit("mission_log_updated", MissionLogUpdated(tasks=self.get_tasks()))
            logger.debug(f"Mission Log saved and UI notified. Task count: {len(self.tasks)}")
        except IOError as e:
            logger.error(f"Failed to save mission log to {log_path}: {e}")

    def load_log_for_active_project(self):
        """Loads the mission log from disk for the currently active project."""
        log_path = self._get_log_path()
        self.tasks = []
        self._next_task_id = 1

        if log_path and log_path.exists():
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f)
                if self.tasks:
                    # Ensure all tasks have a valid ID and find the max.
                    valid_ids = [task.get('id', 0) for task in self.tasks]
                    self._next_task_id = max(valid_ids) + 1 if valid_ids else 1
                logger.info(f"Successfully loaded Mission Log for '{self.project_manager.active_project_name}'")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse mission log at {log_path}: {e}. Starting fresh.")
                self.tasks = []  # Ensure tasks are cleared on error
        else:
            logger.info("No existing mission log found for this project. Starting fresh.")

        self._save_and_notify()

    def add_task(self, description: str, tool_call: Optional[Dict] = None) -> Dict[str, Any]:
        """Adds a new task to the mission log, optionally with its tool call."""
        if not description:
            raise ValueError("Task description cannot be empty.")

        new_task = {
            "id": self._next_task_id,
            "description": description,
            "done": False,
            "tool_call": tool_call
        }
        self.tasks.append(new_task)
        self._next_task_id += 1
        self._save_and_notify()
        logger.info(f"Added task {new_task['id']}: '{description}'")
        return new_task

    def mark_task_as_done(self, task_id: int) -> bool:
        """Marks a specific task as completed."""
        for task in self.tasks:
            if task.get('id') == task_id:
                if not task.get('done'):  # Only update if it's not already done
                    task['done'] = True
                    self._save_and_notify()
                    logger.info(f"Marked task {task_id} as done.")
                return True
        logger.warning(f"Attempted to mark non-existent task {task_id} as done.")
        return False

    def get_tasks(self, done: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Returns a copy of the current tasks, optionally filtered by done status."""
        tasks = self.tasks.copy()
        if done is not None:
            return [task for task in tasks if task.get('done') == done]
        return tasks

    def clear_all_tasks(self):
        """Removes all tasks from the log."""
        if not self.tasks:
            return
        self.tasks = []
        self._next_task_id = 1
        self._save_and_notify()
        logger.info("All tasks cleared from the Mission Log.")

    def replace_all_tasks_with_tool_plan(self, tool_plan: List[Dict[str, Any]]):
        """Atomically replaces all tasks with a new, executable tool-based plan."""
        self.tasks = []
        self._next_task_id = 1

        # Helper to create a human-readable summary
        def _summarize_tool_call(tool_call: dict) -> str:
            tool_name = tool_call.get('tool_name', 'unknown_tool')
            args = tool_call.get('arguments', {})
            summary = ' '.join(word.capitalize() for word in tool_name.split('_'))
            path = args.get('path') or args.get('source_path')
            if path:
                summary += f": '{Path(path).name}'"
            elif 'dependency' in args:
                summary += f": '{args['dependency']}'"
            return summary

        for tool_call in tool_plan:
            new_task = {
                "id": self._next_task_id,
                "description": _summarize_tool_call(tool_call),
                "done": False,
                "tool_call": tool_call
            }
            self.tasks.append(new_task)
            self._next_task_id += 1

        self._save_and_notify()
        logger.info(f"Mission Log replaced with executable plan of {len(self.tasks)} steps.")