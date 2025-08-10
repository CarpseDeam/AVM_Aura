# services/conductor_service.py
import logging
import threading
import asyncio
from typing import Callable, Optional

from event_bus import EventBus
from services.mission_log_service import MissionLogService
from services.tool_runner_service import ToolRunnerService
from services.development_team_service import DevelopmentTeamService
from foundry import BlueprintInvocation
from events import PostChatMessage

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log.
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
        """Starts the mission execution in a new thread to avoid blocking the GUI."""
        if self.is_mission_active:
            print("[ConductorService] Mission is already in progress.")
            return

        self.is_mission_active = True

        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.log("error", "Could not get the running event loop. Cannot start mission.")
            self.is_mission_active = False
            return

        def mission_runner():
            self.log("info", "Mission thread started. Scheduling coroutine on main loop.")
            future = asyncio.run_coroutine_threadsafe(self.execute_mission(), main_loop)

            def on_done(f):
                try:
                    f.result()
                    self.log("info", "Mission coroutine completed successfully (from thread).")
                except Exception as e:
                    self.log("error", f"Mission coroutine failed with exception: {e}")

            future.add_done_callback(on_done)

        mission_thread = threading.Thread(target=mission_runner, daemon=True)
        mission_thread.start()

    async def execute_mission(self):
        """The main logic for running a mission from the Mission Log."""
        failed_result = None
        mission_succeeded = False
        try:
            high_level_tasks = self.mission_log_service.get_tasks()
            if not high_level_tasks:
                self.log("info", "Mission Log is empty. Nothing to execute.")
                return

            self.event_bus.emit("agent_status_changed", "Conductor", "Mission dispatched...", "fa5s.play-circle")
            self.event_bus.emit("post_chat_message", PostChatMessage(sender="Conductor",
                                                                     message="Mission dispatched! I'm now taking the high-level plan and handing it off to the technical team to create a detailed implementation plan."))

            # Combine high-level plan into a single prompt for the dev team
            high_level_prompt = "\n".join([f"- {task['description']}" for task in high_level_tasks])

            # Run the full technical planning phase
            detailed_tool_plan = await self.development_team_service.run_full_technical_build(high_level_prompt)

            if detailed_tool_plan is None:
                raise RuntimeError("The development team failed to produce a detailed execution plan.")

            # Replace the high-level plan with the detailed, tool-based plan
            self.mission_log_service.replace_all_tasks(detailed_tool_plan)
            self.event_bus.emit("post_chat_message", PostChatMessage(sender="Conductor",
                                                                     message="The detailed plan is complete. I am now executing the steps."))

            mission_task_queue = [t for t in self.mission_log_service.get_tasks() if not t.get('done')]

            while mission_task_queue:
                task = mission_task_queue.pop(0)
                tool_call = task.get("tool_call")

                self.log("info", f"Executing task: {task['description']}")
                await asyncio.sleep(0.5)

                result = self.tool_runner_service.run_tool_by_dict(tool_call)

                is_failure = (isinstance(result, str) and "Error" in result) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    failed_result = result
                    raise RuntimeError(f"Task '{task['description']}' failed.")
                else:
                    self.mission_log_service.mark_task_as_done(task['id'])

            mission_succeeded = True
            self.log("success", "Mission Accomplished! All tasks completed.")
            self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")
            if failed_result:
                self.event_bus.emit("execution_failed", str(failed_result))

        finally:
            self.is_mission_active = False
            if mission_succeeded:
                self.event_bus.emit("post_chat_message", PostChatMessage(sender="Aura",
                                                                         message="Mission Accomplished! All tasks have been completed successfully."))
            self.log("info", "Mission finished or aborted. Conductor is now idle.")

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)