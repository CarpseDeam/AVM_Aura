# services/task_agent.py
import logging
import threading
import time
from typing import Optional, Callable

from event_bus import EventBus
from events import UserPromptEntered, AgentTaskCompleted

logger = logging.getLogger(__name__)


class TaskAgent:
    """
    An agent responsible for executing a single task from the Mission Log
    using a Test-Driven, Lint-Validated Development loop.
    """

    def __init__(self, task_id: int, task_description: str, event_bus: EventBus, display_callback: Callable):
        self.task_id = task_id
        self.description = task_description
        self.event_bus = event_bus
        self.display = display_callback

        self._completion_event = threading.Event()
        self._last_result: Optional[AgentTaskCompleted] = None
        self._is_active = False

    def _subscribe_to_completion(self):
        self._is_active = True
        # This simplified event bus requires a handler that can filter events.
        self.event_bus.subscribe(AgentTaskCompleted, self._handle_task_completed)

    def _unsubscribe_from_completion(self):
        # A more robust bus would have event_bus.unsubscribe(self._handle_task_completed)
        self._is_active = False

    def _handle_task_completed(self, event: AgentTaskCompleted):
        if self._is_active and event.task_id == self.task_id:
            logger.info(f"TaskAgent for task {self.task_id} received completion signal.")
            self._last_result = event
            self._completion_event.set()

    def _execute_sub_phase(self, prompt: str, timeout: int = 600) -> Optional[AgentTaskCompleted]:
        """Publishes a prompt for a part of the TDD cycle and waits for its completion."""
        self._completion_event.clear()
        self._last_result = None
        self.event_bus.publish(
            UserPromptEntered(prompt_text=prompt, auto_approve_plan=True, task_id=self.task_id)
        )
        completed = self._completion_event.wait(timeout=timeout)
        if not completed:
            self.display(f"❌ Sub-phase for task {self.task_id} timed out after {timeout} seconds.", "avm_error")
            return None
        return self._last_result

    def execute(self) -> bool:
        """
        Executes the full TDD & Linting loop for the assigned task.
        Returns True if the task was completed successfully, False otherwise.
        """
        self._subscribe_to_completion()
        self.display(f"▶️ Agent assigned to task {self.task_id}: {self.description}", "avm_executing")

        max_attempts = 3
        last_error_report = ""

        for attempt in range(max_attempts):
            self.display(f"--- TDD Attempt {attempt + 1}/{max_attempts} for Task {self.task_id} ---", "avm_info")

            # Step 1: Generate Code (or Fix Code)
            if attempt == 0:
                # First attempt is to write the code and tests from the description.
                prompt = (
                    f"Your objective is to complete this task: '{self.description}'. "
                    "Create a plan that writes all necessary code and test files. "
                    "The plan MUST then lint the new application code. "
                    "Finally, the plan MUST end with a call to `run_with_debugger` to execute the tests."
                )
            else:
                # Subsequent attempts are to fix the previous error.
                prompt = (
                    "Your previous attempt failed. Fix the following error:\n\n"
                    f"--- ERROR REPORT ---\n{last_error_report}\n--- END REPORT ---"
                )

            result = self._execute_sub_phase(prompt)

            if not result or not result.result:
                self.display(f"❌ Agent for task {self.task_id} received no result from LLM. Aborting.", "avm_error")
                self._unsubscribe_from_completion()
                return False

            # The result from the LLM Operator is the test/lint output
            final_output = result.result
            if isinstance(final_output, str) and ("All tests passed" in final_output or "passed in" in final_output):
                self.display(f"✅ Task {self.task_id} completed successfully!", "avm_executing")
                self._unsubscribe_from_completion()
                return True
            else:
                # Capture the failure reason for the next attempt's prompt
                last_error_report = str(final_output)
                if "No issues found" in last_error_report: # Linting passed, but tests failed
                    self.display(f"❌ Linting passed, but tests failed on attempt {attempt + 1}. Analyzing debug report...", "avm_error")
                else: # Linting itself failed
                    self.display(f"❌ Code did not meet quality standards on attempt {attempt + 1}. Analyzing lint report...", "avm_error")
                time.sleep(2)

        self.display(f"💔 Task {self.task_id} failed after {max_attempts} attempts. Final error:\n{last_error_report}", "avm_error")
        self._unsubscribe_from_completion()
        return False