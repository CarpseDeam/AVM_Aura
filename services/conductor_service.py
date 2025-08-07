# services/conductor_service.py
import logging
import threading
import json
from typing import Callable, Optional

from event_bus import EventBus
from events import (
    BlueprintInvocation, StatusUpdate, UserPromptEntered, DirectToolInvocationRequest
)
from foundry import FoundryManager
from .mission_log_service import MissionLogService
from .tool_runner_service import ToolRunnerService

logger = logging.getLogger(__name__)


class ConductorService:
    """
    Orchestrates the execution of multi-step missions from the Mission Log.
    This is the "Foreman" of the execution system.
    """

    def __init__(
            self,
            event_bus: EventBus,
            foundry_manager: FoundryManager,
            mission_log_service: MissionLogService,
            tool_runner_service: ToolRunnerService,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.foundry_manager = foundry_manager
        self.mission_log_service = mission_log_service
        self.tool_runner_service = tool_runner_service
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
        try:
            tasks = self.mission_log_service.get_tasks()
            pending_tasks = [t for t in tasks if not t.get('done')]
            self._display(f"🚀 Mission dispatch acknowledged. Executing {len(pending_tasks)} tasks...", "system_message")

            # Foresight: Pre-scan for and execute project creation first
            project_creation_task = next((t for t in pending_tasks if t.get("tool_call", {}).get("tool_name") == "create_project"), None)

            if project_creation_task:
                self._display("Project creation task found. Setting up environment first...", "avm_executing")
                tool_call = project_creation_task["tool_call"]
                blueprint = self.foundry_manager.get_blueprint(tool_call['tool_name'])
                invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call.get('arguments', {}))

                # We inject mission_log_service here for mission-specific actions
                if 'mission_log_service' in self.tool_runner_service.run_tool.__code__.co_varnames:
                     invocation.parameters['mission_log_service'] = self.mission_log_service

                result = self.tool_runner_service.run_tool(invocation)

                if isinstance(result, str) and ("Error" in result or "failed" in result):
                    self._display(f"❌ Project creation failed. Aborting mission.", "avm_error")
                    return
                else:
                    self.event_bus.publish(DirectToolInvocationRequest(tool_id='mark_task_as_done', params={'task_id': project_creation_task['id']}))

                pending_tasks = [t for t in self.mission_log_service.get_tasks() if not t.get('done')]

            # Execute remaining tasks
            for task in pending_tasks:
                tool_call_dict = task.get("tool_call")
                if not tool_call_dict:
                    self._display(f"⚠️ Skipping task {task['id']} ('{task['description']}') as it has no executable tool call.", "avm_warning")
                    continue

                self._display(f"--- Executing Task {task['id']}: {task['description']} ---", "avm_executing")
                blueprint = self.foundry_manager.get_blueprint(tool_call_dict['tool_name'])
                if not blueprint:
                    self._display(f"❌ Aborting mission: Could not find blueprint for tool '{tool_call_dict['tool_name']}'.", "avm_error")
                    return

                invocation = BlueprintInvocation(blueprint=blueprint, parameters=tool_call_dict.get('arguments', {}))

                # Inject the mission log service for the mark_as_done tool
                if tool_call_dict['tool_name'].startswith(("mark_task", "get_mission", "add_task")):
                    invocation.parameters['mission_log_service'] = self.mission_log_service

                result = self.tool_runner_service.run_tool(invocation)

                if isinstance(result, str) and ("Error" in result or "failed" in result):
                    self._display(f"❌ Task {task['id']} failed. Initiating self-correction.", "avm_error")
                    self._initiate_self_correction(invocation, result)
                    return
                else:
                    self.event_bus.publish(DirectToolInvocationRequest(tool_id='mark_task_as_done', params={'task_id': task['id']}))

            self._display("🎉 All mission tasks completed successfully!", "system_message")

        except Exception as e:
            logger.error(f"A critical error occurred during mission execution: {e}", exc_info=True)
            self._display(f"A critical error occurred during the mission: {e}", "avm_error")
        finally:
            self.is_mission_active = False
            logger.info("Mission finished or aborted. Conductor is now idle.")