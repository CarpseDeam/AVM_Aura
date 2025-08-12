# services/conductor_service.py
import logging
import asyncio
from pathlib import Path
from typing import Callable, Optional

from event_bus import EventBus
from services.mission_log_service import MissionLogService
from services.tool_runner_service import ToolRunnerService
from services.development_team_service import DevelopmentTeamService
from events import PostChatMessage, MissionAccomplished

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of a mission by looping through tasks and delegating
    the "how-to" for each step to the DevelopmentTeamService. It is now TDD-aware.
    """

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
        logger.info("ConductorService initialized.")

    def execute_mission_in_background(self, event=None):
        if self.is_mission_active:
            self.log("warning", "Mission is already in progress.")
            return
        self.is_mission_active = True
        asyncio.create_task(self.execute_mission())

    async def execute_mission(self):
        """
        The main agentic loop. It is TDD-aware and handles the Red-Green-Refactor cycle.
        """
        try:
            self.event_bus.emit("agent_status_changed", "Conductor", "Mission dispatched...", "fa5s.play-circle")
            self._post_chat_message("Conductor", "Mission received. Beginning autonomous TDD execution loop.")

            while self.is_mission_active:
                pending_tasks = self.mission_log_service.get_tasks(done=False)
                if not pending_tasks:
                    self.log("success", "All tasks completed.")
                    break

                current_task = pending_tasks[0]
                self.log("info", f"Executing task {current_task['id']}: {current_task['description']}")

                # --- *** THE FIX IS HERE: ROBUST TDD CHECK *** ---
                task_desc_lower = current_task['description'].lower()
                is_a_test_run_step = 'run the tests' in task_desc_lower or 'run the test suite' in task_desc_lower
                is_failure_expected = 'fail' in task_desc_lower or 'error' in task_desc_lower
                is_red_step = is_a_test_run_step and is_failure_expected
                # --- END OF FIX ---

                tool_call = await self.development_team_service.run_coding_task(current_task)
                if not tool_call:
                    raise RuntimeError(f"Could not determine a tool call for task: '{current_task['description']}'")

                result = await self.tool_runner_service.run_tool_by_dict(tool_call)

                is_actual_failure = False
                if isinstance(result, dict) and 'status' in result:
                    if is_red_step and result['status'] in ["failure", "error"]:
                        self.log("success", "TDD 'Red' step successful: Tests failed as expected.")
                        self._post_chat_message("Conductor", "Tests failed as expected. Proceeding to implementation.")
                    elif not is_red_step and result['status'] in ["failure", "error"]:
                        is_actual_failure = True
                        await self._execute_analysis_and_fix_phase(result)
                        break
                    elif is_red_step and result['status'] == 'success':
                        self.log("warning",
                                 "TDD 'Red' step warning: Tests passed unexpectedly. The implementation may already exist.")

                elif isinstance(result, str) and result.lower().strip().startswith("error"):
                    is_actual_failure = True
                    raise RuntimeError(f"Tool execution failed for task '{current_task['description']}': {result}")

                if not is_actual_failure:
                    self.mission_log_service.mark_task_as_done(current_task['id'])
                    self._post_chat_message("Conductor", f"Task completed: {current_task['description']}")
                    await asyncio.sleep(0.5)

            # This check is now outside the loop; it runs only when the loop breaks.
            if self.is_mission_active and not self.mission_log_service.get_tasks(done=False):
                self.log("success", "Mission Accomplished! All tasks completed and verified.")
                self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")
                self.event_bus.emit("mission_accomplished", MissionAccomplished())
                self._post_chat_message("Aura", "Mission Accomplished! All tasks have been completed successfully.")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")
            self._post_chat_message("Aura", f"A critical error stopped the mission: {e}", is_error=True)
        finally:
            self.is_mission_active = False
            self.log("info", "Conductor has finished its cycle and is now idle.")

    async def _execute_analysis_and_fix_phase(self, test_result: dict):
        """
        Triggers the reviewer to analyze the failure, propose a new plan, and then
        awaits the user's command to proceed.
        """
        self._post_chat_message("Conductor", "A failure was detected. Initiating self-correction protocol.",
                                is_error=True)
        error_details = test_result.get('full_output', 'No detailed output available from test run.')

        await self.development_team_service.run_review_and_fix_phase(
            error_report=error_details,
            git_diff=self.development_team_service.project_manager.get_git_diff(),
            full_code_context=self.development_team_service.project_manager.get_project_files()
        )

        self._post_chat_message("Aura",
                                "I have analyzed the failure and created a new plan to fix it. Please review the Agent TODO list and click 'Dispatch Aura' to try again.",
                                is_error=True)

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)