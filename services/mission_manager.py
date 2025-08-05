# services/mission_manager.py
import logging
import threading
import time
from typing import Callable, Optional, Dict, Any

from event_bus import EventBus
from events import MissionDispatchRequest, UserPromptEntered, AgentTaskCompleted, DirectToolInvocationRequest
from .mission_log_service import MissionLogService
from .project_manager import ProjectManager

logger = logging.getLogger(__name__)


class MissionManager:
    """
    Manages the autonomous execution of tasks from the Mission Log using a TDD loop.
    """

    def __init__(self, event_bus: EventBus, mission_log_service: MissionLogService,
                 project_manager: ProjectManager, display_callback: Callable):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.project_manager = project_manager
        self.display_callback = display_callback

        self._is_mission_active = False
        self._mission_thread = None
        self._current_task_id: Optional[int] = None
        self._sub_task_completion_event = threading.Event()
        self._last_sub_task_result: Optional[AgentTaskCompleted] = None

        self.event_bus.subscribe(MissionDispatchRequest, self.handle_dispatch_request)
        self.event_bus.subscribe(AgentTaskCompleted, self.handle_task_completed)
        logger.info("MissionManager initialized.")

    def handle_dispatch_request(self, event: MissionDispatchRequest):
        if self._is_mission_active:
            self.display_callback("Mission is already in progress.", "avm_error")
            return

        if not self.project_manager.is_project_active():
            self.display_callback("❌ Cannot dispatch mission. No active project. Please create one first.", "avm_error")
            return

        self._is_mission_active = True
        self.display_callback("🚀 Mission dispatch acknowledged. Beginning autonomous execution...", "system_message")
        self._mission_thread = threading.Thread(target=self._run_mission, daemon=True)
        self._mission_thread.start()

    def handle_task_completed(self, event: AgentTaskCompleted):
        if self._is_mission_active and event.task_id == self._current_task_id:
            logger.info(f"Received completion signal for sub-task of mission {event.task_id}.")
            self._last_sub_task_result = event
            self._sub_task_completion_event.set()

    def _execute_sub_task(self, prompt: str, timeout: int = 600) -> Optional[AgentTaskCompleted]:
        """Publishes a prompt for a sub-task and waits for its completion."""
        self._sub_task_completion_event.clear()
        self._last_sub_task_result = None
        self.event_bus.publish(
            UserPromptEntered(prompt_text=prompt, auto_approve_plan=True, task_id=self._current_task_id)
        )
        completed = self._sub_task_completion_event.wait(timeout=timeout)
        if not completed:
            self.display_callback(f"❌ Sub-task timed out after {timeout} seconds.", "avm_error")
            return None
        return self._last_sub_task_result

    def _run_mission(self):
        try:
            undone_tasks = [task for task in self.mission_log_service.get_tasks() if not task.get('done', False)]
            if not undone_tasks:
                self.display_callback("Mission log contains no pending tasks.", "system_message")
                return
            self.display_callback(f"Found {len(undone_tasks)} pending tasks.", "avm_info")
            time.sleep(1)

            for task in undone_tasks:
                self._current_task_id = task['id']
                self.display_callback(f"▶️ Starting task {self._current_task_id}: {task['description']}",
                                      "avm_executing")

                max_attempts = 3
                task_successful = False
                last_error = ""
                file_paths = {}

                # --- THIS IS THE TDD LOOP ---
                for attempt in range(max_attempts):
                    self.display_callback(f"--- TDD Attempt {attempt + 1}/{max_attempts} ---", "avm_info")

                    # --- PROMPT GENERATION ---
                    if attempt == 0:
                        # First attempt: Write the tests and the code
                        prompt = (
                            f"Your objective is to complete the following task: '{task['description']}'. "
                            "You are working inside an existing project. Your plan must NOT include a 'create_project' step. "
                            "The plan MUST include these specific actions in order:\n"
                            "1. `write_file` for `requirements.txt` (including `pytest`, `requests`, `beautifulsoup4`).\n"
                            "2. `write_file` for the main python script (e.g., `scraper.py`).\n"
                            "3. `write_file` for a `pytest` test script (e.g., `test_scraper.py`) that uses `unittest.mock`.\n"
                            "4. `run_shell_command` to create a virtual environment: `python -m venv venv`.\n"
                            "5. `pip_install` to install dependencies from `requirements.txt`.\n"
                            "6. `run_tests` to execute the tests."
                        )
                    else:
                        # Subsequent attempts: Fix the code based on the error
                        prompt = (f"Objective: {task['description']}. The previous attempt failed. "
                                  f"Error: '{last_error}'. The relevant files are: {file_paths}. "
                                  f"Please analyze the error and the code in the files, then create a plan to "
                                  f"fix the code using the 'write_file' tool. Your response must be only a single JSON object."
                                  )

                    # --- EXECUTE THE PLAN ---
                    plan_execution_result = self._execute_sub_task(prompt)

                    if not plan_execution_result:
                        self.display_callback(
                            "❌ Mission Manager did not receive a response from the LLM Operator. Aborting task.",
                            "avm_error")
                        break # Exit the attempt loop for this task

                    # Keep track of file paths for the next attempt's context
                    if plan_execution_result.file_paths:
                        file_paths.update(plan_execution_result.file_paths)

                    final_output = plan_execution_result.result

                    # --- CHECK FOR SUCCESS ---
                    if isinstance(final_output, str) and (
                            "All tests passed" in final_output or "passed in" in final_output):
                        self.display_callback(f"✅ Tests passed on attempt {attempt + 1}!", "avm_executing")
                        task_successful = True
                        break # Success! Exit the attempt loop.
                    else:
                        # Failure: record the error and loop again
                        self.display_callback(f"❌ Tests failed on attempt {attempt + 1}. Analyzing error...",
                                              "avm_error")
                        last_error = str(final_output)
                        time.sleep(2) # Give a moment to see the error

                # --- MARK TASK AS DONE (OR NOT) ---
                if task_successful:
                    self.event_bus.publish(
                        DirectToolInvocationRequest('mark_task_as_done', {'task_id': self._current_task_id}))
                    self.display_callback(f"✅ Task {self._current_task_id} completed successfully.", "avm_executing")
                else:
                    self.display_callback(
                        f"💔 Task {self._current_task_id} failed after {max_attempts} attempts. Final error: {last_error}",
                        "avm_error")

                time.sleep(2) # Pause between tasks

            self.display_callback("🎉 All mission tasks completed or attempted!", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.display_callback(f"A critical error occurred in the mission loop: {e}", "avm_error")
        finally:
            self._is_mission_active = False
            self._current_task_id = None
            logger.info("Mission finished or aborted. MissionManager is now idle.")