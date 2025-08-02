# services/executor.py
"""
This module defines the ExecutorService, responsible for running actions
and building the Abstract Syntax Tree (AST) for code generation.
"""

import logging
import ast # <-- Import the ast module
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation
from foundry.blueprints import RawCodeInstruction, Blueprint
from services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Executes instructions, building an AST for code generation.

    This service acts as the bridge between an abstract instruction and its
    concrete execution. It invokes functions, displays string results, and
    appends returned AST nodes to an internal code-building tree.
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
        
        # --- NEW: Initialize the AST canvas ---
        self.ast_root = ast.Module(body=[], type_ignores=[])
        logger.info("ExecutorService initialized with a blank AST root.")
        
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        """
        Executes a blueprint by invoking its logic and handling the result.
        The result can be a string to display or an AST node to be woven
        into the code being generated.
        """
        blueprint = invocation.blueprint
        action_name = blueprint.name
        action_params = invocation.parameters

        display_message = f"▶️ Executing Blueprint: {action_name}"
        self._display(display_message, "avm_executing")

        if not blueprint.execution_logic:
            self._display(f"Error: Blueprint '{action_name}' has no execution logic.", "avm_error")
            return

        try:
            # --- NEW: Handle special meta-blueprints ---
            if action_name == "get_generated_code":
                # This blueprint needs the AST itself as an argument.
                result = blueprint.execution_logic(code_ast=self.ast_root)
            else:
                # Standard execution for all other blueprints.
                result = blueprint.execution_logic(**action_params)

            # --- NEW: Handle the result based on its type ---
            if isinstance(result, str):
                # If it's a string, display it (e.g., from file operations).
                result_message = f"✅ Result from {action_name}:\n{result}"
                self._display(result_message, "avm_output")
                
                # Update context if it was a read_file action
                if action_name == "read_file":
                    path = action_params.get("path")
                    if path:
                        self.context_manager.add_to_context(key=path, content=result)
                        self._display(f"📝 Content of '{path}' added to context.", "avm_info")
            
            elif isinstance(result, ast.AST):
                # If it's an AST node, append it to our code tree.
                self.ast_root.body.append(result)
                node_type = type(result).__name__
                success_msg = f"✅ Success: Added '{node_type}' node to the code tree."
                self._display(success_msg, "avm_info")
                logger.info(success_msg)

            else:
                # Handle unexpected return types.
                self._display(f"Blueprint '{action_name}' returned an unexpected type: {type(result)}", "avm_error")

        except Exception as e:
            error_msg = f"❌ Error executing Blueprint '{action_name}': {e}"
            logger.exception("An exception occurred while executing blueprint '%s'.", action_name)
            self._display(error_msg, "avm_error")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        # This remains a placeholder for now.
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