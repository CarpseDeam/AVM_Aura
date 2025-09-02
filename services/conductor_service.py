# services/conductor_service.py
import logging
import asyncio
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from event_bus import EventBus
from services.mission_log_service import MissionLogService
from services.tool_runner_service import ToolRunnerService
from services.development_team_service import DevelopmentTeamService
from events import PostChatMessage, MissionAccomplished

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of a mission by looping through tasks, handling
    failures with a two-tiered correction system (retry and re-plan), and
    delegating the "how-to" for each step to the DevelopmentTeamService.

    Includes a "Quality Tier" system to switch between fast drafting and
    robust, test-driven production code generation.
    """
    MAX_RETRIES_PER_TASK = 1

    def __init__(
            self,
            event_bus: EventBus,
            mission_log_service: MissionLogService,
            tool_runner_service: ToolRunnerService,
            development_team_service: DevelopmentTeamService
    ):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.tool_runner_service = tool_runner_service
        self.development_team_service = development_team_service

        self.is_mission_active = False
        self.original_user_goal = ""

        # New! The configurable quality setting for the factory.
        self.quality_tier = "DRAFT"  # Can be "DRAFT" or "PRODUCTION"

        logger.info("ConductorService initialized.")

    def execute_mission_in_background(self, event=None):
        """Entry point to start the mission execution in a non-blocking way."""
        if self.is_mission_active:
            self.log("warning", "Mission is already in progress.")
            return
        self.is_mission_active = True
        if not self.original_user_goal:
            self.original_user_goal = self.mission_log_service.get_initial_goal()

        asyncio.create_task(self.execute_mission())

    async def execute_mission(self):
        """
        The main agentic loop. It processes tasks based on the selected quality tier,
        retries on failure, and triggers a strategic re-plan if a task cannot be completed.
        """
        try:
            self.event_bus.emit("agent_status_changed", "Conductor",
                                f"Mission dispatched ({self.quality_tier} Mode)...", "fa5s.play-circle")
            self._post_chat_message("Conductor",
                                    f"Mission received. Beginning autonomous execution in '{self.quality_tier}' mode.")

            while True:
                if not self.is_mission_active:
                    self.log("info", "Mission execution was externally stopped.")
                    break

                pending_tasks = self.mission_log_service.get_tasks(done=False)
                if not pending_tasks:
                    await self._handle_mission_completion()
                    break

                current_task = pending_tasks[0]
                task_succeeded = False

                if self.quality_tier == "PRODUCTION" and self._is_code_generation_task(current_task):
                    # Use the robust, test-driven workflow
                    task_succeeded = await self._run_production_task(current_task)
                else:
                    # Use the fast, draft-oriented workflow
                    task_succeeded = await self._run_draft_task(current_task)

                if not task_succeeded:
                    self.log("error", f"Task {current_task['id']} failed its workflow. Triggering strategic re-plan.")
                    self._post_chat_message("Aura", "I seem to be stuck. I'm going to rethink my approach.",
                                            is_error=True)
                    await self._execute_strategic_replan(current_task)
                else:
                    await asyncio.sleep(0.5)  # Small delay between successful tasks

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")
            self._post_chat_message("Aura", f"A critical error stopped the mission: {e}", is_error=True)
        finally:
            self.is_mission_active = False
            self.log("info", "Conductor has finished its cycle and is now idle.")

    async def _run_draft_task(self, current_task: dict) -> bool:
        """Handles a task with the fast, retry-based DRAFT workflow."""
        retry_count = 0
        while retry_count <= self.MAX_RETRIES_PER_TASK:
            tool_call = await self.development_team_service.run_coding_task(
                task=current_task,
                last_error=current_task.get('last_error')
            )

            if not tool_call:
                error_msg = f"Could not determine a tool call for task: '{current_task['description']}'"
                current_task['last_error'] = error_msg
                retry_count += 1
                self.log("warning", f"{error_msg}. Retry {retry_count}/{self.MAX_RETRIES_PER_TASK}.")
                continue

            result = await self.tool_runner_service.run_tool_by_dict(tool_call)
            result_is_error, error_message = self._is_result_an_error(result)

            if not result_is_error:
                self.mission_log_service.mark_task_as_done(current_task['id'])
                self._post_chat_message("Conductor", f"Task completed: {current_task['description']}")
                return True
            else:
                current_task['last_error'] = error_message
                retry_count += 1
                self.log("warning",
                         f"Task {current_task['id']} failed. Error: {error_message}. Retry {retry_count}/{self.MAX_RETRIES_PER_TASK}.")
                self._post_chat_message("Conductor", f"Task failed. I will try again. Error: {error_message}",
                                        is_error=True)

        return False  # Task failed all retries

    async def _run_production_task(self, current_task: dict) -> bool:
        """Handles a code generation task with the robust, TDD-based PRODUCTION workflow."""
        self.log("info", f"Running PRODUCTION workflow for task: {current_task['description']}")

        # 1. Determine paths for implementation and test files
        try:
            impl_path, test_path = self._get_paths_for_task(current_task)
        except ValueError as e:
            current_task['last_error'] = str(e)
            return False

        # 2. Sentry Agent: Write failing tests
        self.event_bus.emit("agent_status_changed", "Sentry", f"Writing tests for {Path(impl_path).name}...",
                            "fa5s.shield-alt")
        sentry_result = await self.development_team_service.run_sentry_task(current_task, impl_path, test_path)
        if self._is_result_an_error(sentry_result)[0]:
            current_task['last_error'] = f"Sentry failed to write tests: {sentry_result}"
            return False
        self._post_chat_message("Sentry", f"Wrote initial failing tests to `{test_path}`.")

        # 3. Coder Agent: Write implementation code to pass the tests
        current_task_with_test_context = current_task.copy()
        current_task_with_test_context[
            'description'] += f"\n\n**Goal:** Implement the code in `{impl_path}` to make the tests in `{test_path}` pass."
        tool_call = await self.development_team_service.run_coding_task(task=current_task_with_test_context)
        if not tool_call:
            current_task['last_error'] = "Coder failed to generate a tool call for the implementation."
            return False

        write_result = await self.tool_runner_service.run_tool_by_dict(tool_call)
        if self._is_result_an_error(write_result)[0]:
            current_task['last_error'] = f"Coder failed to write implementation file: {write_result}"
            return False
        self._post_chat_message("Coder", f"Wrote implementation code to `{impl_path}`.")

        # 4. Conductor: Run the tests
        self._post_chat_message("Conductor", "Implementation complete. Running verification tests...")
        test_command = f"pytest {test_path}"  # Assuming pytest is installed in the venv
        test_result_str = await self.tool_runner_service.run_tool_by_dict({
            "tool_name": "run_shell_command",
            "arguments": {"command": test_command}
        })

        if "failed" in test_result_str.lower() or "error" in test_result_str.lower():
            current_task['last_error'] = f"Tests failed. Pytest output:\n{test_result_str}"
            self._post_chat_message("Conductor", "Tests failed. The code is not yet correct.", is_error=True)
            return False  # Failed, will trigger re-plan with test output

        # 5. Success!
        self.mission_log_service.mark_task_as_done(current_task['id'])
        self._post_chat_message("Conductor", "All tests passed! Code is verified and correct.")
        return True

    def _is_code_generation_task(self, task: dict) -> bool:
        """Heuristically determines if a task is about writing code."""
        desc = task['description'].lower()
        keywords = ["create file", "write code", "implement", "define function", "add class"]
        if any(keyword in desc for keyword in keywords):
            return True
        if task.get("tool_call", {}).get("tool_name") == "stream_and_write_file":
            return True
        return False

    def _get_paths_for_task(self, task: dict) -> Tuple[str, str]:
        """Extracts the implementation path from the task and derives the test path."""
        desc = task['description']
        # Regex to find file paths like 'src/main.py' or `path/to/file.ext`
        match = re.search(r"[`']([^`']+\.py)[`']", desc)
        if not match:
            raise ValueError("Could not determine the target file path from the task description.")

        relative_impl_path = match.group(1)
        impl_path = Path(relative_impl_path)

        # Derive test path, e.g., 'src/utils.py' -> 'tests/test_utils.py'
        test_filename = f"test_{impl_path.name}"
        relative_test_path = Path("tests") / test_filename

        return str(relative_impl_path), str(relative_test_path)

    def _is_result_an_error(self, result: any) -> Tuple[bool, Optional[str]]:
        """Determines if a tool result constitutes an error."""
        if isinstance(result, str) and result.strip().lower().startswith("error"):
            return True, result
        if isinstance(result, dict) and result.get('status', 'success').lower() in ["failure", "error"]:
            return True, result.get('summary') or result.get('full_output') or "Unknown error from tool."
        return False, None

    async def _execute_strategic_replan(self, failed_task: Dict):
        """Triggers the Development Team to create a new plan to overcome a persistent failure."""
        await self.development_team_service.run_strategic_replan(
            original_goal=self.original_user_goal,
            failed_task=failed_task,
            mission_log=self.mission_log_service.get_tasks()
        )
        self._post_chat_message("Aura", "I have formulated a new plan. Resuming execution.", is_error=False)

    async def _handle_mission_completion(self):
        """Generates and posts the final summary when all tasks are done."""
        self.log("success", "Mission Accomplished! All tasks completed.")
        self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")
        self.event_bus.emit("mission_accomplished", MissionAccomplished())

        summary = await self.development_team_service.generate_mission_summary(self.mission_log_service.get_tasks())
        self._post_chat_message("Aura", summary)

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)

