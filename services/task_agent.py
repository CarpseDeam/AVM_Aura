# services/task_agent.py
import logging
import threading
import time
import json
from typing import Optional, Callable, Dict, Any

from event_bus import EventBus
from events import UserPromptEntered, AgentTaskCompleted
from .prompt_engine import PromptEngine
from foundry.actions.code_quality_actions import lint_file

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

    def _run_linting_check(self, file_paths: Dict[str, str]) -> Optional[str]:
        linting_errors = []
        for file_path in file_paths.values():
            if file_path.endswith('.py'):
                self.display(f"Checking code quality for {file_path}...", "avm_info")
                lint_result = lint_file(file_path)
                if "No issues found" not in lint_result:
                    linting_errors.append(f"--- LINTING ERRORS for {file_path} ---\n{lint_result}")
        return "\n".join(linting_errors) if linting_errors else None

    def execute(self, mission_goal: str) -> Optional[Dict[str, str]]:
        self._subscribe_to_completion()
        self.display(f"▶️ Agent assigned to task {self.task_id}: {self.description}", "avm_executing")

        max_attempts = 5
        current_prompt_text = self.description
        mission_context = {}

        for attempt in range(max_attempts):
            self.display(f"--- Agent Attempt {attempt + 1}/{max_attempts} for Task {self.task_id} ---", "avm_info")

            prompt = self.prompt_engine.create_prompt(
                user_prompt=current_prompt_text,
                mission_goal=mission_goal,
                mission_context=mission_context
            )
            result_event = self._execute_sub_phase(prompt)

            if not result_event or not isinstance(result_event.result, dict):
                self.display(f"❌ Agent for task {self.task_id} received invalid result. Aborting.", "avm_error")
                break

            run_result = result_event.result
            status = run_result.get("status")

            if status == "success":
                self.display("✅ Tests passed! Checking code quality...", "avm_executing")
                linting_report = self._run_linting_check(result_event.file_paths)
                if linting_report:
                    self.display("⚠️ Code quality issues found. Requesting fixes...", "avm_warning")
                    current_prompt_text = (
                        "Your code is functionally correct, but has style issues. "
                        "Fix these linting errors without changing functionality:\n\n"
                        f"{linting_report}"
                    )
                    continue
                else:
                    self.display("✨ Code quality check passed! Task complete.", "avm_executing")
                    self._unsubscribe_from_completion()
                    return result_event.file_paths

            elif status == "failure":
                self.display(f"❌ Tests failed. Analyzing report...", "avm_error")
                # Create a very specific prompt for fixing the error
                error_report = json.dumps(run_result, indent=2)
                current_prompt_text = (
                    "Your previous attempt failed the tests. Analyze this structured report and fix the bug. "
                    "Focus only on the failing code.\n\n"
                    f"--- STRUCTURED ERROR REPORT ---\n{error_report}\n--- END REPORT ---"
                )
                time.sleep(2)
                continue

            else:  # Handle 'error' or 'no_tests_found' or other unexpected statuses
                self.display(
                    f"⚠️ Task {self.task_id} resulted in an inconclusive state: {status}. Summary: {run_result.get('summary')}",
                    "avm_warning")
                current_prompt_text = (
                    "Your previous attempt was inconclusive. Please try to accomplish the original task again, "
                    "ensuring you create both implementation and test files. "
                    f"Original task: '{self.description}'"
                )
                continue

        self.display(f"💔 Task {self.task_id} failed after {max_attempts} attempts.", "avm_error")
        self._unsubscribe_from_completion()
        return None