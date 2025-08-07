# services/mission_log_service.py
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from .project_manager import ProjectManager
from event_bus import EventBus
from events import MissionLogUpdated

logger = logging.getLogger(__name__)
MISSION_LOG_FILENAME = "mission_log.json"


class MissionLogService:
    """
    Manages the state of the Mission Log (to-do list) for the active project.
    """

    def __init__(self, project_manager: ProjectManager, event_bus: EventBus):
        self.project_manager = project_manager
        self.event_bus = event_bus
        self.tasks: List[Dict[str, Any]] = []
        self._next_task_id = 1
        logger.info("MissionLogService initialized.")

    def _get_log_path(self) -> Optional[Path]:
        """Gets the path to the mission log file for the active project."""
        if self.project_manager.active_project_path:
            return self.project_manager.active_project_path / MISSION_LOG_FILENAME
        return None

    def load_log_for_active_project(self):
        """Loads the mission log from disk for the currently active project."""
        log_path = self._get_log_path()
        if log_path and log_path.exists():
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f)
                if self.tasks:
                    self._next_task_id = max(task.get('id', 0) for task in self.tasks) + 1
                else:
                    self._next_task_id = 1
                logger.info(f"Successfully loaded Mission Log for '{self.project_manager.get_active_project_name()}'")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse mission log at {log_path}: {e}")
                self.tasks = []
                self._next_task_id = 1
        else:
            logger.info("No existing mission log found for this project. Starting fresh.")
            self.tasks = []
            self._next_task_id = 1

        self.event_bus.publish(MissionLogUpdated(tasks=self.tasks))

    def _save_log(self):
        """Saves the current list of tasks to disk."""
        log_path = self._get_log_path()
        if not log_path:
            logger.warning("Cannot save mission log, no active project.")
            return

        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2)
            logger.info(f"Mission Log saved to {log_path}")
        except IOError as e:
            logger.error(f"Failed to save mission log to {log_path}: {e}")

    def add_task(self, description: str, tool_call: Optional[Dict] = None) -> Dict[str, Any]:
        """Adds a new task to the mission log, optionally with its tool call."""
        if not description:
            raise ValueError("Task description cannot be empty.")

        new_task = {
            "id": self._next_task_id,
            "description": description,
            "done": False,
            "tool_call": tool_call  # Store the machine-readable instruction
        }
        self.tasks.append(new_task)
        self._next_task_id += 1
        self._save_log()
        self.event_bus.publish(MissionLogUpdated(tasks=self.tasks))
        logger.info(f"Added task {new_task['id']}: '{description}'")
        return new_task

    def mark_task_as_done(self, task_id: int) -> bool:
        """Marks a specific task as completed."""
        for task in self.tasks:
            if task.get('id') == task_id:
                task['done'] = True
                self._save_log()
                self.event_bus.publish(MissionLogUpdated(tasks=self.tasks))
                logger.info(f"Marked task {task_id} as done.")
                return True
        logger.warning(f"Attempted to mark non-existent task {task_id} as done.")
        return False

    def get_tasks(self) -> List[Dict[str, Any]]:
        """Returns a copy of the current tasks."""
        return self.tasks.copy()