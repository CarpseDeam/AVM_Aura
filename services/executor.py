# services/executor.py
import logging
import ast
from typing import Callable, Optional

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation
from foundry.foundry_manager import FoundryManager  # <-- Import FoundryManager
from foundry.blueprints import RawCodeInstruction
from services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class ExecutorService:
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            foundry_manager: FoundryManager,  # <-- MODIFIED: Inject the FoundryManager
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.foundry_manager = foundry_manager  # <-- MODIFIED: Store the FoundryManager
        self.display_callback = display_callback
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
        Looks up an action by name via the FoundryManager and executes it.
        """
        blueprint = invocation.blueprint
        action_id = blueprint.id
        action_params = invocation.parameters

        display_message = f"▶️ Executing Blueprint: {action_id}"
        self._display(display_message, "avm_executing")

        # --- MODIFIED: The core logic change ---
        # 1. Get the action function NAME from the blueprint
        action_function_name = blueprint.action_function_name
        # 2. Get the actual function OBJECT from the FoundryManager's registry
        action_function = self.foundry_manager.get_action(action_function_name)

        if not action_function:
            self._display(
                f"Error: Action function '{action_function_name}' not found in Foundry for blueprint '{action_id}'.",
                "avm_error")
            return

        try:
            if action_id == "get_generated_code":
                result = action_function(code_ast=self.ast_root)
            else:
                result = action_function(**action_params)

            if isinstance(result, str):
                result_message = f"✅ Result from {action_id}:\n{result}"
                self._display(result_message, "avm_output")

                if action_id == "read_file":
                    path = action_params.get("path")
                    if path:
                        self.context_manager.add_to_context(key=path, content=result)
                        self._display(f"📝 Content of '{path}' added to context.", "avm_info")

            elif isinstance(result, ast.AST):
                self.ast_root.body.append(result)
                node_type = type(result).__name__
                success_msg = f"✅ Success: Added '{node_type}' node to the code tree for blueprint '{action_id}'."
                self._display(success_msg, "avm_info")
                logger.info(success_msg)

            else:
                self._display(f"Blueprint '{action_id}' returned an unexpected type: {type(result)}", "avm_error")

        except Exception as e:
            error_msg = f"❌ Error executing Blueprint '{action_id}': {e}"
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
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