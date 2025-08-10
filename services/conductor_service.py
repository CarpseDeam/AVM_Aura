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

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log.
    Handles the two-phase plan: approve high-level plan, then execute detailed plan.
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

        # Get the running event loop from the main thread where this method is called.
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.log("error", "Could not get the running event loop. Cannot start mission.")
            self.is_mission_active = False
            return

        # Define the target function for our new thread.
        def mission_runner():
            """
            This function runs in the new thread. It schedules the coroutine
            on the main event loop and can optionally wait for the result.
            """
            self.log("info", "Mission thread started. Scheduling coroutine on main loop.")
            # Schedule the coroutine to be run on the main loop.
            future = asyncio.run_coroutine_threadsafe(self.execute_mission(), main_loop)

            # You can add a callback to handle the result or exception from the thread
            def on_done(f):
                try:
                    f.result() # Raises exception if the coroutine failed
                    self.log("info", "Mission coroutine completed successfully (from thread).")
                except Exception as e:
                    self.log("error", f"Mission coroutine failed with exception: {e}")

            future.add_done_callback(on_done)

        # Start the thread with our new mission_runner function
        mission_thread = threading.Thread(target=mission_runner, daemon=True)
        mission_thread.start()

    async def execute_mission(self):
        """The main logic for running a mission from the Mission Log."""
        failed_result = None
        try:
            mission_task_queue = [t for t in self.mission_log_service.get_tasks() if not t.get('done')]
            if not mission_task_queue:
                self.log("info", "Mission Log is empty. Nothing to execute.")
                self.event_bus.emit("agent_status_changed", "Conductor", "Mission complete", "fa5s.check-circle")
                return

            self.event_bus.emit("agent_status_changed", "Conductor", "Executing mission...", "fa5s.play-circle")

            while mission_task_queue:
                task = mission_task_queue.pop(0)
                tool_call = task.get("tool_call")

                # If a task has no tool call, it's for review only. Mark done and skip.
                if not tool_call:
                    self.mission_log_service.mark_task_as_done(task['id'])
                    continue

                tool_name = tool_call.get("tool_name")

                # Handle the special trigger task to start the main execution phase
                if tool_name == "execute_full_generation_plan":
                    self.log("info", "User approved plan. Engaging Coder, Tester, and Finalizer.")
                    args = tool_call.get("arguments", {})
                    plan, existing_files = args.get("plan"), args.get("existing_files")

                    if not plan or self.development_team_service is None:
                        raise RuntimeError("Conductor missing plan or dev team service.")

                    # Mark the high-level trigger task as done
                    self.mission_log_service.mark_task_as_done(task['id'])

                    # Run Phase 2 to get the detailed, low-level tool plan
                    detailed_tool_plan = await self.development_team_service.run_execution_phase(plan, existing_files)

                    if detailed_tool_plan is None:
                        raise RuntimeError("Execution phase failed to produce a final tool plan.")

                    # Create human-readable tasks for the new detailed plan
                    new_tasks = []
                    for step in detailed_tool_plan:
                        summary = self.development_team_service._summarize_tool_call(step)
                        new_tasks.append({"description": summary, "tool_call": step})

                    # Prepend the new detailed tasks to the front of the queue
                    self.mission_log_service.replace_all_tasks(new_tasks)
                    mission_task_queue = [t for t in self.mission_log_service.get_tasks() if not t.get('done')]
                    self.log("success", "High-level plan expanded into detailed steps.")
                    continue

                # --- Regular Tool Execution ---
                self.log("info", f"Executing tool: {tool_name}")
                threading.Event().wait(0.5)
                result = self.tool_runner_service.run_tool_by_dict(tool_call)

                is_failure = (isinstance(result, str) and "Error" in result) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    failed_result = result
                    raise RuntimeError(f"Task '{task['description']}' failed. See logs for details.")
                else:
                    self.mission_log_service.mark_task_as_done(task['id'])

            self.log("success", "Mission Accomplished! All tasks completed.")
            self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", f"Mission Failed: {e}", "fa5s.exclamation-circle")
            if failed_result:
                self.event_bus.emit("execution_failed", str(failed_result))

        finally:
            self.is_mission_active = False
            self.log("info", "Mission finished or aborted. Conductor is now idle.")

    def log(self, level: str, message: str):
        self.event_bus.emit("log_message_received", "ConductorService", level, message)