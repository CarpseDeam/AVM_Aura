# services/mission_log_service.py
import logging
import json
import re
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
        self.event_bus.emit("mission_log_updated", MissionLogUpdated(tasks=self.get_tasks()))
        logger.debug(f"UI notified of mission log update. Task count: {len(self.tasks)}")

        log_path = self._get_log_path()
        if not log_path:
            logger.debug("Cannot save mission log to disk, no active project path set yet.")
            return

        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2)
            logger.debug(f"Mission Log saved to disk at {log_path}.")
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
                    valid_ids = [task.get('id', 0) for task in self.tasks]
                    self._next_task_id = max(valid_ids) + 1 if valid_ids else 1
                logger.info(f"Successfully loaded Mission Log for '{self.project_manager.active_project_name}'")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load or parse mission log at {log_path}: {e}. Starting fresh.")
                self.tasks = []
        else:
            logger.info("No existing mission log found for this project. Starting fresh.")

        self._save_and_notify()

    def set_initial_plan(self, plan_steps: List[str]):
        """Clears all tasks and sets a new plan, including the initial indexing task."""
        self.tasks = []
        self._next_task_id = 1

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
        """
        Adds a new task. If the task is for creating a Python file, it
        automatically adds a follow-up task to generate tests.
        """
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
        logger.info(f"Added task {new_task['id']}: '{description}'")

        # --- AUTOMATIC TEST GENERATION RULE (HARDENED) ---
        # If the task is for creating a .py file AND is NOT a test-generation task itself.
        match = re.search(r"['`\"](.+?\.py)['`\"]", description, re.IGNORECASE)
        is_test_generation_task = 'test' in description.lower()

        if match and not is_test_generation_task:
            py_filename = match.group(1)
            test_task_desc = f"Generate tests for {py_filename}"
            test_task = {
                "id": self._next_task_id,
                "description": test_task_desc,
                "done": False,
                "tool_call": {
                    "tool_name": "generate_tests_for_file",
                    "arguments": {"path": py_filename}
                }
            }
            self.tasks.append(test_task)
            self._next_task_id += 1
            logger.info(f"AUTO-TASK: Added task {test_task['id']}: '{test_task_desc}'")
        # --- END OF RULE ---

        if notify:
            self._save_and_notify()

        return new_task

    def mark_task_as_done(self, task_id: int) -> bool:
        """Marks a specific task as completed."""
        for task in self.tasks:
            if task.get('id') == task_id:
                if not task.get('done'):
                    task['done'] = True
                    self._save_and_notify()
                    logger.info(f"Marked task {task_id} as done.")
                return True
        logger.warning(f"Attempted to mark non-existent task {task_id} as done.")
        return False

    def get_tasks(self, done: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Returns a copy of the current tasks, optionally filtered by done status."""
        return [task for task in self.tasks if done is None or task.get('done') == done]

    def clear_all_tasks(self):
        """Removes all tasks from the log."""
        if self.tasks:
            self.tasks = []
            self._next_task_id = 1
            self._save_and_notify()
            logger.info("All tasks cleared from the Mission Log.")

    def replace_all_tasks_with_tool_plan(self, tool_plan: List[Dict[str, Any]]):
        """Atomically replaces all tasks with a new, executable tool-based plan."""
        self.tasks = []
        self._next_task_id = 1

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

        # Use the main add_task method so the auto-test rule still applies to fixes
        for tool_call in tool_plan:
            self.add_task(
                description=_summarize_tool_call(tool_call),
                tool_call=tool_call,
                notify=False # Delay notification until all tasks are added
            )

        self._save_and_notify()
        logger.info(f"Mission Log replaced with executable plan of {len(self.tasks)} steps.")