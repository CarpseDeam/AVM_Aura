"""
This module defines the ExecutorService, which is responsible for executing actions.

The service listens for `ActionReadyForExecution` events on the event bus,
and upon receiving one, it logs and "announces" the execution of the
structured action contained within the event.
"""

import logging

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
    or call other tools based on the LLM's structured output.
    """

    def __init__(self, event_bus: EventBus):
        """
        Initializes the ExecutorService.

        Args:
            event_bus: The application's central event bus to subscribe to events.
        """
        self.event_bus = event_bus
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Registers event handlers with the event bus."""
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)
        logger.info("ExecutorService initialized and handlers registered.")

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        """
        Logs the details of a BlueprintInvocation to simulate its execution.

        Args:
            invocation: The BlueprintInvocation object to be "executed".
        """
        action_name = invocation.blueprint.name
        action_params = invocation.parameters

        logger.info("--- EXECUTING BLUEPRINT ACTION ---")
        logger.info("Action: %s", action_name)

        if action_params:
            # Log each parameter on a new line for readability
            param_str = "\n".join(
                [f"  - {key}: {value}" for key, value in action_params.items()]
            )
            logger.info("Parameters:\n%s", param_str)
        else:
            logger.info("Parameters: None")

        logger.info("--- ACTION COMPLETE ---")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        """
        Logs the details of a RawCodeInstruction to simulate its execution.

        Note: This is a placeholder for actual code execution. In a real
        scenario, this would involve sandboxing and careful security measures.

        Args:
            instruction: The RawCodeInstruction object to be "executed".
        """
        try:
            code_to_run = instruction.code
            language = getattr(instruction, "language", "unknown")

            logger.info("--- EXECUTING RAW CODE INSTRUCTION ---")
            logger.info("Language: %s", language)
            logger.info("Code:\n---\n%s\n---", code_to_run)
            logger.warning(
                "Raw code execution is a placeholder. No code was actually run."
            )
            logger.info("--- ACTION COMPLETE ---")

        except AttributeError:
            logger.error(
                "Action execution failed: RawCodeInstruction object is missing "
                "the expected 'code' attribute. Instruction: %s",
                instruction,
            )

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        """
        Handles an ActionReadyForExecution event by processing the instruction.

        This method inspects the type of the instruction (BlueprintInvocation or
        RawCodeInstruction) contained within the event, extracts the relevant
        details, and logs them to simulate execution.

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
            logger.error(
                "Action execution failed: Unknown instruction type '%s'.",
                type(instruction).__name__,
            )