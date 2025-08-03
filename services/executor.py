# services/executor.py
import logging
import ast
from typing import Callable, Optional, List

from event_bus import EventBus
from events import ActionReadyForExecution, BlueprintInvocation, PauseExecutionForUserInput, PlanApproved
from foundry import FoundryManager
from foundry.blueprints import RawCodeInstruction, UserInputRequest
from .context_manager import ContextManager
from .vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


class ExecutorService:
    def __init__(
            self,
            event_bus: EventBus,
            context_manager: ContextManager,
            foundry_manager: FoundryManager,
            vector_context_service: VectorContextService,
            display_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.event_bus = event_bus
        self.context_manager = context_manager
        self.foundry_manager = foundry_manager
        self.vector_context_service = vector_context_service
        self.display_callback = display_callback
        self.ast_root = ast.Module(body=[], type_ignores=[])
        logger.info("ExecutorService initialized with a blank AST root.")
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(ActionReadyForExecution, self._handle_action_ready)
        # --- NEW: Subscribe to the PlanApproved event from the GUI ---
        self.event_bus.subscribe(PlanApproved, self._handle_plan_approved)

    def _display(self, message: str, tag: str) -> None:
        if self.display_callback:
            self.display_callback(message, tag)

    def _execute_plan(self, plan: List[BlueprintInvocation]) -> None:
        """A dedicated, reusable method to execute a list of blueprint invocations."""
        self._display(f"▶️ Executing {len(plan)}-step plan...", "avm_executing")
        for i, step in enumerate(plan):
            self._display(f"--- Step {i + 1}/{len(plan)} ---", "avm_executing")
            if isinstance(step, BlueprintInvocation):
                self._execute_blueprint(step)
            else:
                self._display(f"Error: Plan step {i + 1} is not a valid BlueprintInvocation.", "avm_error")
                # Optional: Decide if the plan should halt on error
                break
        self._display("✅ Plan execution complete.", "avm_executing")

    def _execute_blueprint(self, invocation: BlueprintInvocation) -> None:
        blueprint = invocation.blueprint
        action_id = blueprint.id
        action_params = invocation.parameters
        self._display(f"▶️ Executing Blueprint: {action_id}", "avm_executing")
        action_function = self.foundry_manager.get_action(blueprint.action_function_name)
        if not action_function:
            self._display(f"Error: Action function '{blueprint.action_function_name}' not found.", "avm_error")
            return
        try:
            if action_id == "get_generated_code":
                result = action_function(code_ast=self.ast_root)
            elif action_id == "index_project_context":
                result = action_function(vector_context_service=self.vector_context_service, **action_params)
            else:
                result = action_function(**action_params)

            if isinstance(result, str):
                self._display(f"✅ Result from {action_id}:\n{result}", "avm_output")
                if action_id == "read_file" and action_params.get("path"):
                    self.context_manager.add_to_context(key=action_params["path"], content=result)
                    self._display(f"📝 Content of '{action_params['path']}' added to context.", "avm_info")
            elif isinstance(result, ast.AST):
                self.ast_root.body.append(result)
                self._display(f"✅ Success: Added '{type(result).__name__}' node to the code tree.", "avm_info")
            elif isinstance(result, UserInputRequest):
                self.event_bus.publish(PauseExecutionForUserInput(question=result.question))
            else:
                self._display(f"Blueprint '{action_id}' returned an unexpected type: {type(result)}", "avm_error")
        except Exception as e:
            logger.exception("An exception occurred while executing blueprint '%s'.", action_id)
            self._display(f"❌ Error executing Blueprint '{action_id}': {e}", "avm_error")

    def _execute_raw_code(self, instruction: RawCodeInstruction) -> None:
        self._display("▶️ Executing Raw Code...\nRaw code execution is not yet implemented.", "avm_executing")

    def _handle_action_ready(self, event: ActionReadyForExecution) -> None:
        instruction = event.instruction
        if isinstance(instruction, list):
            self._execute_plan(instruction)
        elif isinstance(instruction, BlueprintInvocation):
            self._execute_blueprint(instruction)
        elif isinstance(instruction, RawCodeInstruction):
            self._execute_raw_code(instruction)
        else:
            self._display(f"Error: Unknown instruction type received for execution.", "avm_error")

    def _handle_plan_approved(self, event: PlanApproved) -> None:
        """Handles the execution of a plan that was manually approved by the user."""
        logger.info(f"Received approved plan with {len(event.plan)} steps. Starting execution.")
        self._display("✅ Plan approved by user. Executing now...", "system_message")
        self._execute_plan(event.plan)