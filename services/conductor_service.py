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
    tasks and invoking the development team to generate code for each step
    within a rich, just-in-time context.
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
        """
        Schedules the mission execution as a background task on the main
        asyncio event loop, avoiding blocking the GUI.
        """
        if self.is_mission_active:
            self.log("warning", "Mission is already in progress.")
            return

        self.is_mission_active = True
        asyncio.create_task(self.execute_mission())

    async def execute_mission(self):
        """
        The main logic for running a mission based on the new context-aware loop architecture.
        """
        mission_succeeded = False
        try:
            self.event_bus.emit("agent_status_changed", "Conductor", "Mission dispatched...", "fa5s.play-circle")

            high_level_tasks_dicts = self.mission_log_service.get_tasks(done=False)
            if not high_level_tasks_dicts:
                self.log("info", "Mission Log is empty. Nothing to execute.")
                self.is_mission_active = False # Reset status
                return

            self._post_chat_message("Conductor", "Mission received. Beginning autonomous execution loop.")

            # Loop through human-readable tasks, creating context for each one.
            for task_dict in high_level_tasks_dicts:
                current_task_desc = task_dict['description']
                task_id = task_dict['id']

                # Stop if mission was aborted externally
                if not self.is_mission_active:
                    self.log("info", "Mission was aborted. Halting execution.")
                    return

                # If the task is a pre-defined tool call (like indexing), execute it directly.
                if task_dict.get('tool_call'):
                    self._post_chat_message("Conductor", f"Executing utility task: {current_task_desc}")
                    await self.tool_runner_service.run_tool_by_dict(task_dict['tool_call'])
                    self.mission_log_service.mark_task_as_done(task_id)
                    continue

                self.event_bus.emit("agent_status_changed", "Conductor", f"Executing: {current_task_desc}", "fa5s.cogs")

                # 1. Delegate to Dev Team to get the correct tool call for the task
                tool_call_to_execute = await self.development_team_service.run_coding_task(
                    current_task=current_task_desc
                )

                if not tool_call_to_execute:
                    raise RuntimeError(f"The Coder failed to generate a tool call for task: '{current_task_desc}'")

                # 2. Execute the returned tool call
                result = await self.tool_runner_service.run_tool_by_dict(tool_call_to_execute)

                is_failure = (isinstance(result, str) and result.lower().strip().startswith("error"))
                if is_failure:
                    self.event_bus.emit("execution_failed", str(result))
                    raise RuntimeError(f"Task '{current_task_desc}' failed during tool execution.")
                else:
                    self.mission_log_service.mark_task_as_done(task_id)
                    self._post_chat_message("Conductor", f"Task completed: {current_task_desc}")

                await asyncio.sleep(0.5)

            # 3. Post-mission verification
            self._post_chat_message("Conductor", "All tasks completed. Running final verification steps.")
            self.event_bus.emit("agent_status_changed", "Conductor", "Verifying installation...", "fa5s.cogs")
            pip_result = await self.tool_runner_service.run_tool_by_dict({"tool_name": "pip_install", "arguments": {}})
            self._post_chat_message("Conductor", f"Installation result:\n{pip_result}")

            self.event_bus.emit("agent_status_changed", "Conductor", "Running tests...", "fa5s.cogs")
            test_result = await self.tool_runner_service.run_tool_by_dict({"tool_name": "run_tests", "arguments": {}})

            test_summary = test_result.get('summary', 'No summary available.')
            self._post_chat_message("Conductor", f"Test result: {test_summary}")

            if test_result.get("status") in ["failure", "error"]:
                 error_details = test_result.get('full_output', 'No detailed output available from test run.')
                 self.event_bus.emit("execution_failed", error_details)
                 raise RuntimeError("Tests failed after mission completion.")

            mission_succeeded = True
            self.log("success", "Mission Accomplished! All tasks completed and tests passed.")
            self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")
            self.event_bus.emit("mission_accomplished", MissionAccomplished())

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")

        finally:
            self.is_mission_active = False
            if mission_succeeded:
                self._post_chat_message("Aura", "Mission Accomplished! All tasks have been completed successfully.")
            else:
                self._post_chat_message("Aura", "Mission failed. Please review the logs and my proposed fix.", is_error=True)
            self.log("info", "Mission finished or aborted. Conductor is now idle.")

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)