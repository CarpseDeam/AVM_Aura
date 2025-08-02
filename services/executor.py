"""
This module defines the ExecutorService, which is responsible for executing actions.

The service listens for `ActionReadyForExecution` events on the event bus,
and upon receiving one, it logs and "announces" the execution of the
structured action contained within the event. It can also send status messages
to a GUI via a display callback.
"""

import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation
from foundry.blueprints import RawCodeInstruction

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Listens for structured actions and announces their execution.

    This service subscribes to the event bus for ActionReadyForExecution events,
    logs the details of the action, and simulates its execution by announcing it.
    It acts as the component that would ultimately perform file I/O, run commands,
    or call other tools based on the LLM's structured output. It can be
    configured with a display callback to send status updates to a UI.
    """

    def __init__(
        self,
        event_bus: EventBus,
        display_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initializes the ExecutorService.

        Args:
            event_bus: The application's central event bus to subscribe to events.
            display_callback: An optional function to send status messages to for
                              display in a UI. It should accept a single string.
        """
        self.event_bus = event_bus
        self.display_callback = display_callback
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Registers event handlers with the event bus."""
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)
        logger.info("ExecutorService initialized and handlers registered.")

    def _display(self, message: str) -> None:
        """
        Sends a message to the registered display callback, if available.

        Args:
            message: The string message to display.
        """
        if self.display_callback:
            self.display_callback(message)

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        """
        Logs and displays the details of a BlueprintInvocation.

        Args:
            invocation: The BlueprintInvocation object to be "executed".
        """
        action_name = invocation.blueprint.name
        action_params = invocation.parameters

        display_message_parts = [f"▶️ Executing Blueprint: {action_name}"]

        logger.info("--- EXECUTING BLUEPRINT ACTION ---")
        logger.info("Action: %s", action_name)

        if action_params:
            param_log_str = "\n".join(
                [f"  - {key}: {value}" for key, value in action_params.items()]
            )
            logger.info("Parameters:\n%s", param_log_str)

            display_message_parts.append("Parameters:")
            for key, value in action_params.items():
                display_message_parts.append(f"  - {key}: {value}")
        else:
            logger.info("Parameters: None")
            display_message_parts.append("Parameters: None")

        self._display("\n".join(display_message_parts))
        self._display("✅ Action Complete.")
        logger.info("--- ACTION COMPLETE ---")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        """
        Logs and displays the details of a RawCodeInstruction.

        Note: This is a placeholder for actual code execution. In a real
        scenario, this would involve sandboxing and careful security measures.

        Args:
            instruction: The RawCodeInstruction object to be "executed".
        """
        try:
            code_to_run = instruction.code
            language = getattr(instruction, "language", "unknown")

            display_message = (
                f"▶️ Executing Raw Code Instruction\n"
                f"Language: {language}\n"
                f"Code:\n---\n{code_to_run}\n---"
            )
            self._display(display_message)

            logger.info("--- EXECUTING RAW CODE INSTRUCTION ---")
            logger.info("Language: %s", language)
            logger.info("Code:\n---\n%s\n---", code_to_run)

            warning_msg = "Raw code execution is a placeholder. No code was actually run."
            self._display(f"⚠️ {warning_msg}")
            logger.warning(warning_msg)

            self._display("✅ Action Complete.")
            logger.info("--- ACTION COMPLETE ---")

        except AttributeError:
            error_msg = (
                "Action execution failed: RawCodeInstruction object is missing "
                f"the expected 'code' attribute. Instruction: {instruction}"
            )
            self._display(f"❌ {error_msg}")
            logger.error(error_msg)

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        """
        Handles an ActionReadyForExecution event by processing the instruction.

        This method inspects the type of the instruction (BlueprintInvocation or
        RawCodeInstruction) contained within the event and dispatches to the
        appropriate execution method.

        Args:
            event: The event containing the structured instruction to execute.
        """
        logger.debug("ExecutorService received event: %s", event)

        instruction = event.instruction

        if isinstance(instruction, BlueprintInvocation):
            self._execute_blueprint(instruction)
        elif isinstance(instruction, RawCodeInstruction):
            self._execute_raw_code(instruction)
        else:
            error_msg = (
                "Action execution failed: Unknown instruction type "
                f"'{type(instruction).__name__}'."
            )
            self._display(f"❌ {error_msg}")
            logger.error(error_msg)