# services/executor.py
"""
This module defines the ExecutorService, which has been upgraded to an
AST weaver. It executes actions, and if an action returns a Python AST node,
it weaves that node into an in-memory code tree. It can also unparse
this tree back into a code string.
"""

import ast
import logging
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation
from foundry.blueprints import RawCodeInstruction, Blueprint
from services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Executes instructions, weaving returned AST nodes into a code structure.

    This service listens for `ActionReadyForExecution` events. When an action
    is executed, it checks the result. If the result is an `ast.AST` object,
    it is appended to an internal `ast.Module` body. This allows for the
    incremental construction of a Python script in memory.
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
            event_bus: The application's event bus for communication.
            context_manager: The service for managing shared context.
            display_callback: An optional function to display messages to the UI.
        """
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.display_callback = display_callback
        self.code_ast: ast.Module = ast.Module(body=[], type_ignores=[])
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Subscribes to relevant events on the event bus."""
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)

    def _display(self, message: str, tag: str) -> None:
        """
        Sends a message to the UI via the display callback, if available.

        Args:
            message: The message string to display.
            tag: The tag for styling the message in the UI.
        """
        if self.display_callback:
            self.display_callback(message, tag)

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        """
        Executes a blueprint's logic and handles the result.

        If the result is an `ast.AST` node, it's woven into the code tree.
        If it's a string or other data, it's displayed. Special handling
        is included for actions like 'read_file' (to update context) and
        'get_generated_code' (to provide the current AST).

        Args:
            invocation: The blueprint invocation details.
        """
        blueprint = invocation.blueprint
        action_name = blueprint.name
        action_params = invocation.parameters

        param_str = "\n".join([f"  - {key}: {value}" for key, value in action_params.items()])
        display_message = f"▶️ Executing Blueprint: {action_name}\nParameters:\n{param_str}"
        self._display(display_message, "avm_executing")

        if not blueprint.execution_logic:
            error_msg = f"Error: Blueprint '{action_name}' has no execution logic."
            self._display(error_msg, "avm_error")
            logger.error(error_msg)
            return

        try:
            # Inject the current AST for actions that need it
            if action_name == "get_generated_code":
                action_params['code_ast'] = self.code_ast

            result = blueprint.execution_logic(**action_params)

            # Handle AST nodes by weaving them into the code tree
            if isinstance(result, ast.AST):
                self.code_ast.body.append(result)
                logger.info("Weaving AST node from '%s' into code tree.", action_name)
                self._display(f"✅ Weaving AST node from '{action_name}' into code tree.", "avm_info")

            # Handle non-AST results (e.g., strings from file reads or code generation)
            elif result is not None:
                result_message = f"✅ Result from {action_name}:\n{result}"
                self._display(result_message, "avm_output")

                # Special context handling for 'read_file'
                if action_name == "read_file":
                    path = action_params.get("path")
                    if path and isinstance(result, str):
                        self.context_manager.add_to_context(key=path, content=result)
                        logger.info("Added content of file '%s' to context memory.", path)
                        self._display(f"📝 Content of '{path}' added to context.", "avm_info")
                    else:
                        logger.warning(
                            "Could not add 'read_file' result to context. Path or result missing/invalid."
                        )
            else:
                # For actions that return None (e.g., write_file)
                self._display(f"✅ Blueprint '{action_name}' executed successfully.", "avm_info")

        except Exception as e:
            error_msg = f"❌ Error executing Blueprint '{action_name}': {e}"
            self._display(error_msg, "avm_error")
            logger.exception("Error executing blueprint '%s'", action_name)

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        """
        Handles the execution of raw code instructions. Not yet implemented.

        Args:
            instruction: The raw code instruction to execute.
        """
        display_message = "▶️ Executing Raw Code..."
        self._display(display_message, "avm_executing")
        self._display("Raw code execution is not yet implemented.", "avm_info")
        logger.warning("Attempted to execute raw code, which is not implemented.")

    def _handle_action(self, event: ActionReadyForExecution) -> None:
        """
        Event handler for when an action is ready for execution.

        Routes the instruction to the appropriate execution method based on its type.

        Args:
            event: The event containing the instruction to execute.
        """
        instruction = event.instruction
        logger.info("Handling action for execution: %s", instruction.__class__.__name__)
        if isinstance(instruction, BlueprintInvocation):
            self._execute_blueprint(instruction)
        elif isinstance(instruction, RawCodeInstruction):
            self._execute_raw_code(instruction)
        else:
            error_msg = f"Error: Unknown instruction type: {type(instruction)}"
            self._display(error_msg, "avm_error")
            logger.error(error_msg)