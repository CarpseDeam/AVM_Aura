# services/mission_manager.py
import logging
import threading
import time
from typing import Callable, Optional, Dict, Any

from event_bus import EventBus
from events import MissionDispatchRequest, UserPromptEntered, AgentTaskCompleted, DirectToolInvocationRequest
from .mission_log_service import MissionLogService

logger = logging.getLogger(__name__)


class MissionManager:
    """
    Manages the autonomous execution of tasks from the Mission Log using a TDD loop.
    """

    def __init__(self, event_bus: EventBus, mission_log_service: MissionLogService, display_callback: Callable):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
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

                for attempt in range(max_attempts):
                    self.display_callback(f"--- TDD Attempt {attempt + 1}/{max_attempts} ---", "avm_info")

                    # Step 1: Generate Code (and Test on first attempt)
                    if attempt == 0:
                        prompt = (f"Objective: {task['description']}. Create a plan to write both the feature code "
                                  f"and a new pytest test file to verify it. Use the 'write_file' tool for both.")
                    else:
                        prompt = (f"Objective: {task['description']}. The previous attempt failed. "
                                  f"Error: '{last_error}'. The relevant files are: {file_paths}. "
                                  f"Please analyze the error and the code in the files, then create a plan to "
                                  f"fix the code using the 'write_file' tool.")

                    code_writing_result = self._execute_sub_task(prompt)
                    if not code_writing_result: break  # Timeout or other critical error
                    if code_writing_result.file_paths:
                        file_paths.update(code_writing_result.file_paths)

                    if 'test' not in file_paths:
                        self.display_callback("❌ Agent did not provide a test file path. Aborting task.", "avm_error")
                        break

                    # Step 2: Run the tests
                    self.display_callback(f"Code written. Running test: {file_paths['test']}", "avm_info")
                    test_run_prompt = (f"Run the pytest test located at '{file_paths['test']}' and report the result.")
                    test_result_event = self._execute_sub_task(test_run_prompt)

                    if not test_result_event or not isinstance(test_result_event.result, str):
                        self.display_callback("❌ Failed to get a valid test result. Aborting task.", "avm_error")
                        break

                    test_output = test_result_event.result
                    if "All tests passed" in test_output or "== 1 passed in" in test_output:
                        self.display_callback(f"✅ Tests passed on attempt {attempt + 1}!", "avm_executing")
                        task_successful = True
                        break
                    else:
                        self.display_callback(f"❌ Tests failed. Analyzing error...", "avm_error")
                        last_error = test_output
                        time.sleep(2)

                if task_successful:
                    self.event_bus.publish(
                        DirectToolInvocationRequest('mark_task_as_done', {'task_id': self._current_task_id}))
                    self.display_callback(f"✅ Task {self._current_task_id} completed successfully.", "avm_executing")
                else:
                    self.display_callback(
                        f"💔 Task {self._current_task_id} failed after {max_attempts} attempts. Moving to next task.",
                        "avm_error")

                time.sleep(2)

            self.display_callback("🎉 All mission tasks completed or attempted!", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.display_callback(f"A critical error occurred in the mission loop: {e}", "avm_error")
        finally:
            self._is_mission_active = False
            self._current_task_id = None
            logger.info("Mission finished or aborted. MissionManager is now idle.")