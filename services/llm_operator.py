# services/llm_operator.py
import logging
import threading
from typing import Callable, Optional

from event_bus import EventBus
from events import (
    UserPromptEntered, DirectToolInvocationRequest, StatusUpdate
)
from .architect_service import ArchitectService
from .technician_service import TechnicianService
from .mission_log_service import MissionLogService

logger = logging.getLogger(__name__)


class LLMOperator:
    """
    Acts as the "Foreman", orchestrating the workflow between the Architect,
    Technician, and MissionLog services to populate the Mission Log.
    """

    def __init__(
            self,
            event_bus: EventBus,
            architect_service: ArchitectService,
            technician_service: TechnicianService,
            mission_log_service: MissionLogService,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.architect_service = architect_service
        self.technician_service = technician_service
        self.mission_log_service = mission_log_service
        self.display_callback = display_callback
        logger.info("LLMOperator (Foreman) initialized.")

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _summarize_tool_call(self, tool_call: dict) -> str:
        """Creates a human-readable summary of a tool call for the Mission Log."""
        tool_name = tool_call.get('tool_name', 'unknown_tool')
        args = tool_call.get('arguments', {})
        if not isinstance(args, dict): args = {}

        summary = ' '.join(word.capitalize() for word in tool_name.split('_'))
        path = args.get('path') or args.get('source_path')
        if path:
            summary += f": '{path}'"
        elif 'project_name' in args:
            summary += f": '{args['project_name']}'"

        content_keys = ['content', 'function_code', 'class_code', 'command']
        for key in content_keys:
            if key in args:
                summary += f" with `{str(args[key])[:40].strip()}...`"
                break
        return summary

    def handle(self, event: UserPromptEntered) -> None:
        """Handles the user prompt by running the full planning workflow in a background thread."""
        thread = threading.Thread(target=self._handle_prompt_thread, args=(event,))
        thread.start()

    def _handle_prompt_thread(self, event: UserPromptEntered):
        """
        The core orchestration logic for the Architect -> Technician workflow.
        """
        try:
            if event.auto_approve_plan:
                self._display("Clearing failed plan from Mission Log to make way for the fix...", "avm_info")
                self.mission_log_service.clear_pending_tasks()

            # 1. Delegate to the ArchitectService to get the high-level plan
            reasoning, plan_steps = self.architect_service.get_plan(event.prompt_text)

            if not plan_steps:
                logger.warning("Architect service did not return any plan steps. Aborting.")
                return # Error messages are handled by the service itself

            # 2. Loop through the plan, delegating each step to the TechnicianService
            total_steps = len(plan_steps)
            for i, task in enumerate(plan_steps):
                self.event_bus.publish(StatusUpdate(
                    "PLANNING", f"Technician converting task: '{task[:50]}...'", True, progress=i + 1, total=total_steps
                ))
                self._display(f"    - Task {i + 1}/{total_steps}: `{task}`", "system_message")

                invocations = self.technician_service.get_tool_invocations(task)

                if not invocations:
                    error_message = f"❌ Technician failed to convert task {i + 1}. Aborting plan."
                    self._display(error_message, "avm_error")
                    self.event_bus.publish(StatusUpdate("FAIL", f"Technician failed on task {i + 1}.", False))
                    return

                # 3. Add the successfully translated invocations to the Mission Log
                for invocation in invocations:
                    tool_call_dict = {"tool_name": invocation.blueprint.id, "arguments": invocation.parameters}
                    summary = self._summarize_tool_call(tool_call_dict)
                    params = {"description": summary, "tool_call": tool_call_dict}
                    self.event_bus.publish(DirectToolInvocationRequest(
                        tool_id='add_task_to_mission_log', params=params
                    ))

            self.event_bus.publish(StatusUpdate("IDLE", "Mission Log is ready for dispatch.", False))

        except Exception as e:
            logger.error(f"An unexpected error occurred in the LLMOperator workflow: {e}", exc_info=True)
            self._display(f"An unexpected error occurred during planning: {e}", "avm_error")
            self.event_bus.publish(StatusUpdate("FAIL", "An unexpected error occurred.", False))