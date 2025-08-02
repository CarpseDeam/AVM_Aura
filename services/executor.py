# services/executor.py
"""
This module defines the ExecutorService, responsible for running actions.
"""

import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation
from foundry.blueprints import RawCodeInstruction, Blueprint
from services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Executes instructions received from the event bus.
    """
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.display_callback = display_callback
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        blueprint = invocation.blueprint
        action_name = blueprint.name
        action_params = invocation.parameters

        param_str = "\n".join([f"  - {key}: {value}" for key, value in action_params.items()])
        display_message = f"▶️ Executing Blueprint: {action_name}\nParameters:\n{param_str}"
        self._display(display_message, "avm_executing")

        if not blueprint.execution_logic:
            error_msg = f"Error: Blueprint '{action_name}' has no execution logic."
            self._display(error_msg, "avm_error")
            return

        try:
            result = blueprint.execution_logic(**action_params)
            result_message = f"✅ Result from {action_name}:\n{result}"
            self._display(result_message, "avm_output")

            # --- THIS IS THE FIX ---
            # If the action was reading a file, add its content to the context.
            if action_name == "read_file":
                # The parameter name in the blueprint is 'path', not 'filename'.
                path = action_params.get("path") 
                if path and isinstance(result, str):
                    self.context_manager.add_to_context(key=path, content=result)
                    logger.info("Added content of file '%s' to context memory.", path)
                    self._display(f"📝 Content of '{path}' added to context.", "avm_info")
                else:
                    logger.warning(
                        "Could not add 'read_file' result to context. Path or result missing/invalid."
                    )
            # --- END FIX ---

        except Exception as e:
            error_msg = f"❌ Error executing Blueprint '{action_name}': {e}"
            self._display(error_msg, "avm_error")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        display_message = f"▶️ Executing Raw Code..."
        self._display(display_message, "avm_executing")
        self._display("Raw code execution is not yet implemented.", "avm_info")

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        instruction = event.instruction
        if isinstance(instruction, BlueprintInvocation):
            self._execute_blueprint(instruction)
        elif isinstance(instruction, RawCodeInstruction):
            self._execute_raw_code(instruction)
        else:
            self._display(f"Error: Unknown instruction type.", "avm_error")