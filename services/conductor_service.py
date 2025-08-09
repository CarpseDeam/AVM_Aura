import logging
import threading
from typing import Callable, Optional

from event_bus import EventBus
from events import StatusUpdate, RefreshFileTreeRequest
from services.mission_log_service import MissionLogService
from services.tool_runner_service import ToolRunnerService
from foundry import BlueprintInvocation

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log.
    """

    def __init__(
            self,
            event_bus: EventBus,
            mission_log_service: MissionLogService,
            tool_runner_service: ToolRunnerService
    ):
        self.event_bus = event_bus
        self.mission_log_service = mission_log_service
        self.tool_runner_service = tool_runner_service
        self.is_mission_active = False
        logger.info("ConductorService initialized.")

    def execute_mission_in_background(self):
        """Starts the mission execution in a new thread to avoid blocking the GUI."""
        if self.is_mission_active:
            print("[ConductorService] Mission is already in progress.")
            return

        self.is_mission_active = True
        mission_thread = threading.Thread(target=self.execute_mission, daemon=True)
        mission_thread.start()

    def execute_mission(self):
        """The main logic for running a mission from the Mission Log."""
        try:
            all_tasks = self.mission_log_service.get_tasks()
            mission_task_queue = [t for t in all_tasks if not t.get('done')]
            mission_total_tasks = len(mission_task_queue)

            if mission_total_tasks == 0:
                print("[ConductorService] Mission Log is empty. Nothing to execute.")
                self.event_bus.emit("agent_status_changed", "Conductor", "Mission complete", "fa5s.check-circle")
                return

            self.event_bus.emit("agent_status_changed", "Conductor", f"Executing {mission_total_tasks} tasks...",
                                "fa5s.play-circle")

            completed_in_run = 0
            while mission_task_queue:
                task = mission_task_queue.pop(0)
                completed_in_run += 1

                tool_call_dict = task.get("tool_call")
                if not tool_call_dict:
                    self.mission_log_service.mark_task_as_done(task['id'])
                    continue

                # The ToolRunner will resolve paths using the ProjectManager, no sandbox needed here
                result = self.tool_runner_service.run_tool_by_dict(tool_call_dict)

                is_failure = (isinstance(result, str) and ("Error" in result or "failed" in result)) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    # Self-correction could be triggered here in the future
                    raise RuntimeError(f"Task {task['id']} failed. Aborting mission.")
                else:
                    self.mission_log_service.mark_task_as_done(task['id'])
                    self.event_bus.emit(RefreshFileTreeRequest())

            print("[ConductorService] Mission Accomplished! All tasks completed successfully.")
            self.event_bus.emit("agent_status_changed", "Aura", "Mission Accomplished!", "fa5s.rocket")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self.event_bus.emit("agent_status_changed", "Conductor", "Mission Failed!", "fa5s.exclamation-circle")
        finally:
            self.is_mission_active = False
            logger.info("Mission finished or aborted. Conductor is now idle.")