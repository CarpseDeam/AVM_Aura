# services/executor.py
"""
This module defines the ExecutorService, responsible for running actions.

The service listens for `ActionReadyForExecution` events and executes the
instruction contained within, which can be either a structured Blueprint
invocation or a raw code instruction. It handles the invocation of the
correct logic and displays the results or errors. After certain actions,
like reading a file, it updates the context memory.
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

    This service acts as the bridge between an abstract instruction (like a
    BlueprintInvocation) and its concrete execution. It invokes the associated
    Python function, uses a callback to display the output, and updates the
    AVM's context memory when appropriate (e.g., after reading a file).
    """
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initializes the ExecutorService.

        Args:
            event_bus (EventBus): The central event bus for communication.
            context_manager (ContextManager): The service for managing AVM context.
            display_callback (Optional[Callable[[str, str], None]]): A function
                to call to display output to the user. It takes a message
                string and a tag string.
        """
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.display_callback = display_callback
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Subscribes to relevant events on the event bus."""
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)

    def _display(self, message: str, tag: str) -> None:
        """
        Sends a message to the display callback, if one is configured.

        Args:
            message (str): The message to display.
            tag (str): A tag for classifying the message (e.g., 'avm_output').
        """
        if self.display_callback:
            self.display_callback(message, tag)

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        """
        Executes a blueprint by invoking its linked Python function.

        This method retrieves the `execution_logic` callable from the blueprint,
        calls it with the provided parameters, and displays the result. It
        handles cases where no logic is defined or where execution fails.

        If the executed blueprint is 'read_file', its output is added to the
        ContextManager.

        Args:
            invocation (BlueprintInvocation): The event containing the blueprint
                and parameters for execution.
        """
        blueprint = invocation.blueprint
        action_name = blueprint.name
        action_params = invocation.parameters

        param_str = "\n".join([f"  - {key}: {value}" for key, value in action_params.items()])
        display_message = f"▶️ Executing Blueprint: {action_name}\nParameters:\n{param_str}"
        self._display(display_message, "avm_executing")

        if not blueprint.execution_logic:
            error_msg = f"Error: Blueprint '{action_name}' has no execution logic."
            logger.error(error_msg)
            self._display(error_msg, "avm_error")
            return

        try:
            # Unpack the parameters dictionary as keyword arguments to the function
            result = blueprint.execution_logic(**action_params)
            result_message = f"✅ Result from {action_name}:\n{result}"
            logger.info("Blueprint '%s' executed successfully.", action_name)
            self._display(result_message, "avm_output")

            # If the action was reading a file, add its content to the context.
            if action_name == "read_file":
                filename = action_params.get("filename")
                if filename and isinstance(result, str):
                    self.context_manager.add_to_context(key=filename, content=result)
                    logger.info(
                        "Added content of file '%s' to context memory.", filename
                    )
                    self._display(f"📝 Content of '{filename}' added to context.", "avm_info")
                else:
                    logger.warning(
                        "Could not add 'read_file' result to context. "
                        "Filename or result missing/invalid. Params: %s",
                        action_params,
                    )

        except Exception as e:
            error_msg = f"❌ Error executing Blueprint '{action_name}': {e}"
            logger.exception(
                "An exception occurred while executing blueprint '%s'.", action_name
            )
            self._display(error_msg, "avm_error")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        """
        Handles the execution of a raw code instruction.

        Note: This is currently a placeholder and does not execute the code.

        Args:
            instruction (RawCodeInstruction): The instruction containing the
                raw code to be executed.
        """
        display_message = f"▶️ Executing Raw Code..."
        self._display(display_message, "avm_executing")
        # A full implementation would require a secure sandbox environment.
        self._display("Raw code execution is not yet implemented.", "avm_info")

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        """
        Handles an ActionReadyForExecution event by dispatching to the correct handler.

        Args:
            event (ActionReadyForExecution): The event containing the instruction
                to be executed.
        """
        instruction = event.instruction
        if isinstance(instruction, BlueprintInvocation):
            self._execute_blueprint(instruction)
        elif isinstance(instruction, RawCodeInstruction):
            self._execute_raw_code(instruction)
        else:
            logger.error("Unknown instruction type received: %s", type(instruction))
            self._display(f"Error: Unknown instruction type.", "avm_error")