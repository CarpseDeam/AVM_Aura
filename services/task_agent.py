# services/task_agent.py
import logging
import threading
import time
from typing import Optional, Callable, Dict

from event_bus import EventBus
from events import UserPromptEntered, AgentTaskCompleted
from .prompt_engine import PromptEngine

logger = logging.getLogger(__name__)


class TaskAgent:
    """
    An agent responsible for executing a single task from the Mission Log
    using a Test-Driven, Lint-Validated Development loop.
    """

    def __init__(self, task_id: int, task_description: str, event_bus: EventBus, display_callback: Callable,
                 prompt_engine: PromptEngine):
        self.task_id = task_id
        self.description = task_description
        self.event_bus = event_bus
        self.display = display_callback
        self.prompt_engine = prompt_engine

        self._completion_event = threading.Event()
        self._last_result: Optional[AgentTaskCompleted] = None
        self._is_active = False

    def _subscribe_to_completion(self):
        self._is_active = True
        self.event_bus.subscribe(AgentTaskCompleted, self._handle_task_completed)

    def _unsubscribe_from_completion(self):
        self._is_active = False
        # This is tricky due to multithreading. A simple flag is safer than
        # trying to unsubscribe during an event callback cycle.

    def _handle_task_completed(self, event: AgentTaskCompleted):
        if self._is_active and event.task_id == self.task_id:
            logger.info(f"TaskAgent for task {self.task_id} received completion signal.")
            self._last_result = event
            self._completion_event.set()

    def _execute_sub_phase(self, prompt: str, timeout: int = 600) -> Optional[AgentTaskCompleted]:
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

    def _is_successful_outcome(self, result_text: str) -> bool:
        """
        Checks if the result of a plan execution indicates success.
        Success can be passing tests or a successful shell command execution.
        """
        if not isinstance(result_text, str):
            return False

        # keywords for successful test runs
        test_success_keywords = ["all tests passed", "passed in"]
        # keywords for successful shell commands (like running main.py)
        shell_success_keywords = ["command executed successfully"]

        lower_text = result_text.lower()

        if any(keyword in lower_text for keyword in test_success_keywords):
            return True
        if any(keyword in lower_text for keyword in shell_success_keywords):
            return True

        return False

    def execute(self, mission_goal: str) -> Optional[Dict[str, str]]:
        """
        Executes the full TDD & Linting loop for the assigned task.
        Returns a dictionary of new file paths and their content if successful,
        otherwise returns None.
        """
        self._subscribe_to_completion()
        self.display(f"▶️ Agent assigned to task {self.task_id}: {self.description}", "avm_executing")

        max_attempts = 3
        current_prompt_text = self.description
        mission_context = {}

        for attempt in range(max_attempts):
            self.display(f"--- TDD Attempt {attempt + 1}/{max_attempts} for Task {self.task_id} ---", "avm_info")

            prompt = self.prompt_engine.create_prompt(
                user_prompt=current_prompt_text,
                mission_goal=mission_goal,
                mission_context=mission_context
            )

            result_event = self._execute_sub_phase(prompt)

            if not result_event or not result_event.result:
                self.display(f"❌ Agent for task {self.task_id} received no result from LLM. Aborting.", "avm_error")
                break

            final_output_text = str(result_event.result)
            if self._is_successful_outcome(final_output_text):
                self.display(f"✅ Task {self.task_id} completed successfully!", "avm_executing")
                self._unsubscribe_from_completion()
                return result_event.file_paths
            else:
                current_prompt_text = (
                    "Your previous attempt failed. Fix the following error:\n\n"
                    f"--- ERROR REPORT ---\n{final_output_text}\n--- END REPORT ---"
                )
                self.display(f"❌ Attempt {attempt + 1} failed for task {self.task_id}. Analyzing...", "avm_error")
                time.sleep(2)

        self.display(f"💔 Task {self.task_id} failed after {max_attempts} attempts.", "avm_error")
        self._unsubscribe_from_completion()
        return None