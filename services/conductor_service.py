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
    Orchestrates the execution of a mission by looping through human-readable
    tasks, delegating to the Coder to get a precise tool call for each step,
    and then executing that tool call. Implements the self-healing loop on failure.
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
        The main agentic loop: Build -> Test -> (on fail) -> Analyze -> Propose Fix.
        """
        try:
            self.event_bus.emit("agent_status_changed", "Conductor", "Mission dispatched...", "fa5s.play-circle")
            self._post_chat_message("Conductor", "Mission received. Beginning autonomous execution loop.")

            # PHASE 1: BUILD - Execute all pending tasks
            await self._execute_build_phase()

            # PHASE 2: TEST - Verify the build
            test_result = await self._execute_test_phase()

            # PHASE 3: ANALYZE & LOOP
            if test_result.get("status") in ["failure", "error"]:
                self._post_chat_message("Conductor", "Tests failed. Initiating self-correction protocol.",
                                        is_error=True)
                await self._execute_analysis_and_fix_phase(test_result)
                self._post_chat_message("Aura",
                                        "I have analyzed the failure and created a new plan to fix it. Please review the Agent TODO list and click 'Dispatch Aura' to try again.",
                                        is_error=True)
            else:
                self.log("success", "Mission Accomplished! All tasks completed and tests passed.")
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

    async def _execute_build_phase(self):
        """Executes all pending tasks from the mission log."""
        high_level_tasks = self.mission_log_service.get_tasks(done=False)
        if not high_level_tasks:
            self._post_chat_message("Conductor", "No pending tasks to execute in the build phase.")
            return

        for task in high_level_tasks:
            if not self.is_mission_active:
                self.log("info", "Mission aborted during build phase.")
                raise InterruptedError("Mission was aborted by an external signal.")

            tool_call = await self.development_team_service.run_coding_task(current_task=task['description'])
            if not tool_call:
                raise RuntimeError(f"The Coder failed to generate a tool call for task: '{task['description']}'")

            result = await self.tool_runner_service.run_tool_by_dict(tool_call)
            is_failure = (isinstance(result, str) and result.lower().strip().startswith("error"))
            if is_failure:
                self.event_bus.emit("execution_failed", str(result))
                raise RuntimeError(f"Task '{task['description']}' failed during tool execution.")

            self.mission_log_service.mark_task_as_done(task['id'])
            self._post_chat_message("Conductor", f"Task completed: {task['description']}")
            await asyncio.sleep(0.5)

    async def _execute_test_phase(self) -> dict:
        """Installs dependencies and runs tests."""
        self._post_chat_message("Conductor", "All build tasks completed. Running final verification steps.")
        self.event_bus.emit("agent_status_changed", "Conductor", "Verifying installation...", "fa5s.cogs")

        pip_result = await self.tool_runner_service.run_tool_by_dict({"tool_name": "pip_install", "arguments": {}})
        self._post_chat_message("Conductor", f"Installation result:\n{pip_result}")
        if "error" in str(pip_result).lower():
            return {"status": "error", "summary": "PIP install failed.", "full_output": str(pip_result)}

        self.event_bus.emit("agent_status_changed", "Conductor", "Running tests...", "fa5s.cogs")
        test_result = await self.tool_runner_service.run_tool_by_dict({"tool_name": "run_tests", "arguments": {}})
        test_summary = test_result.get('summary', 'No summary available.')
        self._post_chat_message("Conductor", f"Test result: {test_summary}")
        return test_result

    async def _execute_analysis_and_fix_phase(self, test_result: dict):
        """Triggers the reviewer to analyze the failure and propose a new plan."""
        error_details = test_result.get('full_output', 'No detailed output available from test run.')
        await self.development_team_service.run_review_and_fix_phase(
            error_report=error_details,
            git_diff=self.development_team_service.project_manager.get_git_diff(),
            full_code_context=self.development_team_service.project_manager.get_project_files()
        )

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)