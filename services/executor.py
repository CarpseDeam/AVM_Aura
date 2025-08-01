"""
This module defines the ExecutorService, which is responsible for executing actions.

The service listens for `ActionReadyForExecution` events on the event bus,
and upon receiving one, it logs and "announces" the execution of the
structured action contained within the event.
"""

import logging
from typing import Any, Dict

from event_bus import EventBus
from events import ActionReadyForExecution

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

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        """
        Handles an ActionReadyForExecution event.

        This method extracts the action details from the event, logs them,
        and announces the execution. It includes basic validation to ensure
        the action data is in the expected format.

        Args:
            event: The event containing the structured action to execute.
        """
        logger.debug("ExecutorService received event: %s", event)

        action_data = event.action
        if not isinstance(action_data, dict):
            logger.error(
                "Action execution failed: Event data is not a dictionary. Found type %s.",
                type(action_data).__name__,
            )
            return

        action_name = action_data.get("action")
        action_params = action_data.get("parameters", {})

        if not action_name or not isinstance(action_name, str):
            logger.error(
                "Action execution failed: 'action' key is missing or not a string in event data: %s",
                action_data,
            )
            return

        if not isinstance(action_params, dict):
            logger.error(
                "Action execution failed: 'parameters' key is not a dictionary in event data: %s",
                action_data,
            )
            return

        logger.info("--- EXECUTING ACTION ---")
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