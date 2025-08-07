# services/conductor_service.py
import logging
import threading
import json
from typing import Callable, Optional

from event_bus import EventBus
from events import (
    BlueprintInvocation, StatusUpdate, UserPromptEntered, DirectToolInvocationRequest, RefreshFileTreeRequest
)
from foundry import FoundryManager
from .mission_log_service import MissionLogService
from .tool_runner_service import ToolRunnerService
from .sandbox_manager import SandboxManager
from .project_manager import ProjectManager


logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log
    inside a secure, transactional sandbox environment.
    """

    def __init__(
            self,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            mission_log_service: MissionLogService,
            tool_runner_service: ToolRunnerService,
            project_manager: ProjectManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.mission_log_service = mission_log_service
        self.tool_runner_service = tool_runner_service
        self.project_manager = project_manager
        self.display_callback = display_callback
        self.is_mission_active = False
        logger.info("ConductorService initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _initiate_self_correction(self, failed_invocation: BlueprintInvocation, error_report: any) -> None:
        """Formats a prompt to fix a failure and starts the self-correction loop."""
        self.event_bus.publish(StatusUpdate("SELF-CORRECTION", "Error detected. Formulating a plan to fix it.", True))

        failed_tool_name = failed_invocation.blueprint.id
        failed_tool_args = failed_invocation.parameters

        error_context_str = json.dumps(error_report, indent=2) if isinstance(error_report, dict) else str(error_report)

        correction_prompt = f"""
Failure Report:
An attempt to execute the tool '{failed_tool_name}' with the arguments {json.dumps(failed_tool_args)} has failed.

--- ERROR CONTEXT ---
{error_context_str}
--- END ERROR CONTEXT ---

Your task is to analyze this failure and the relevant code context.
Create a new step-by-step plan to fix this bug.
The plan must end with a step to verify the fix (e.g., by re-running the test that failed).
"""
        logger.info(f"Initiating self-correction with prompt:\n{correction_prompt}")

        self.event_bus.publish(
            UserPromptEntered(prompt_text=correction_prompt, auto_approve_plan=True)
        )

    def execute_mission_in_background(self):
        """Starts the mission execution in a new thread to avoid blocking the GUI."""
        if self.is_mission_active:
            self._display("Mission is already in progress.", "avm_error")
            return

        self.is_mission_active = True
        mission_thread = threading.Thread(target=self.execute_mission, daemon=True)
        mission_thread.start()

    def execute_mission(self):
        """The main logic for running a mission from the Mission Log."""
        if not self.project_manager.is_project_active():
            self._display("❌ Cannot start mission: No active project.", "avm_error")
            self.is_mission_active = False
            return

        sandbox_manager = None
        try:
            tasks = self.mission_log_service.get_tasks()
            pending_tasks = [t for t in tasks if not t.get('done')]
            if not pending_tasks:
                self._display("✅ Mission Log is empty. Nothing to execute.", "system_message")
                return

            self._display(f"🚀 Mission dispatch acknowledged. Executing {len(pending_tasks)} tasks...", "system_message")
            self.event_bus.publish(StatusUpdate("EXECUTING", f"Mission started with {len(pending_tasks)} tasks", True, progress=0, total=len(pending_tasks)))

            for i, task in enumerate(pending_tasks):
                # --- NEW: Create a fresh sandbox for EACH step ---
                sandbox_manager = SandboxManager(project_path=self.project_manager.active_project_path)
                sandbox_path = sandbox_manager.create()
                self._display(f"--- Executing Task {i + 1}/{len(pending_tasks)}: {task['description']} ---", "avm_executing")
                self.event_bus.publish(StatusUpdate("EXECUTING", f"Task: {task['description']}", True, progress=i + 1, total=len(pending_tasks)))

                tool_call_dict = task.get("tool_call")
                if not tool_call_dict:
                    self._display(f"⚠️ Skipping task {task['id']} ('{task['description']}') as it has no executable tool call.", "avm_warning")
                    self.mission_log_service.mark_task_as_done(task['id'])
                    sandbox_manager.cleanup() # Clean up the unused sandbox
                    continue

                blueprint = self.foundry_manager.get_blueprint(tool_call_dict['tool_name'])
                if not blueprint:
                    raise RuntimeError(f"Aborting mission: Could not find blueprint for tool '{tool_call_dict['tool_name']}'.")

                invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))
                result = self.tool_runner_service.run_tool(invocation, sandbox_path=sandbox_path)

                # Check for failure
                is_failure = (isinstance(result, str) and ("Error" in result or "failed" in result)) or \
                             (isinstance(result, dict) and result.get("status") in ["failure", "error"])

                if is_failure:
                    self._initiate_self_correction(invocation, result)
                    raise RuntimeError(f"Task {task['id']} failed. Self-correction initiated.")
                else:
                    # --- NEW: Commit after EACH successful step ---
                    self._display(f"✅ Step successful. Committing changes...", "avm_info")
                    sandbox_manager.commit()
                    self.mission_log_service.mark_task_as_done(task['id'])
                    self.event_bus.publish(RefreshFileTreeRequest())
                    # Clean up the sandbox for this step
                    sandbox_manager.cleanup()
                    sandbox_manager = None


            # If we get here, all tasks succeeded.
            self._display("🎉 Mission Accomplished! All tasks completed successfully.", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self._display(f"❌ Mission aborted due to an error: {e}", "avm_error")
        finally:
            # Final cleanup just in case of an unexpected exit
            if sandbox_manager:
                sandbox_manager.cleanup()
            self.is_mission_active = False
            self.event_bus.publish(StatusUpdate("IDLE", "Ready for input.", False))
            logger.info("Mission finished or aborted. Conductor is now idle.")