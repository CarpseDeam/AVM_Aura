# services/conductor_service.py
import logging
import threading
import asyncio
from typing import Callable, Optional

from event_bus import EventBus
from services.mission_log_service import MissionLogService
from services.tool_runner_service import ToolRunnerService
from services.development_team_service import DevelopmentTeamService
from services.agents.finalizer_agent import FinalizerAgent
from events import PostChatMessage

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of a mission by first using the Finalizer agent to
    convert a high-level plan into an executable tool plan, then running the tools.
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
        # The Finalizer is the key to translating the human plan to a tool plan
        self.finalizer = FinalizerAgent(development_team_service.service_manager)
        self.is_mission_active = False
        logger.info("ConductorService initialized.")

    def execute_mission_in_background(self, event=None):
        """Starts the mission execution in a new thread to avoid blocking the GUI."""
        if self.is_mission_active:
            self.log("warning", "Mission is already in progress.")
            return

        self.is_mission_active = True

        def mission_runner():
            asyncio.run(self.execute_mission())

        mission_thread = threading.Thread(target=mission_runner, daemon=True)
        mission_thread.start()

    async def execute_mission(self):
        """
        The main logic for running a mission.
        1. Takes the human-readable plan from the Mission Log.
        2. Uses the Finalizer to create a detailed, tool-based plan.
        3. Replaces the old plan with the new executable plan.
        4. Executes the tool calls one by one.
        """
        mission_succeeded = False
        try:
            self.event_bus.emit("agent_status_changed", "Conductor", "Mission dispatched...", "fa5s.play-circle")

            # Get the high-level plan from the user's log.
            high_level_tasks = self.mission_log_service.get_tasks(done=False)
            if not high_level_tasks:
                self.log("info", "Mission Log is empty. Nothing to execute.")
                return

            self._post_chat_message("Conductor",
                                    "High-level plan received. Engaging Finalizer to create detailed execution plan.")
            self.event_bus.emit("agent_status_changed", "Finalizer", "Creating technical plan...",
                                "fa5s.clipboard-list")

            # Create a fake diff and dependency list to satisfy the Finalizer's prompt format.
            # The real intelligence is in how it handles the prompt.
            finalizer_prompt_context = "\n".join([f"- {task['description']}" for task in high_level_tasks])

            # The Finalizer is now our Architect. It converts the human plan to a tool plan.
            tool_plan = await self.finalizer.create_tool_plan_from_prompt(finalizer_prompt_context)

            if not tool_plan:
                raise RuntimeError("The Finalizer failed to create an executable tool plan from the high-level steps.")

            self.mission_log_service.replace_all_tasks_with_tool_plan(tool_plan)
            self._post_chat_message("Conductor", "Executable plan created. Beginning execution loop.")

            # Execute the newly created tool-based plan
            mission_task_queue = self.mission_log_service.get_tasks(done=False)
            for task in mission_task_queue:
                tool_call = task.get("tool_call")
                self.event_bus.emit("agent_status_changed", "Conductor", f"Executing: {task['description']}",
                                    "fa5s.cogs")

                result = self.tool_runner_service.run_tool_by_dict(tool_call)

                is_failure = (isinstance(result, str) and "Error" in result) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    self.event_bus.emit("execution_failed", str(result))
                    raise RuntimeError(f"Task '{task['description']}' failed.")
                else:
                    self.mission_log_service.mark_task_as_done(task['id'])
                await asyncio.sleep(0.5)

            mission_succeeded = True
            self.log("success", "Mission Accomplished! All tasks completed.")
            self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")

        finally:
            self.is_mission_active = False
            if mission_succeeded:
                self._post_chat_message("Aura", "Mission Accomplished! All tasks have been completed successfully.")
            self.log("info", "Mission finished or aborted. Conductor is now idle.")

    def _post_chat_message(self, sender: str, message: str, is_error: bool = False):
        self.event_bus.emit("post_chat_message", PostChatMessage(sender, message, is_error))

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)