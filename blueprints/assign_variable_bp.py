import logging
from typing import Dict, Any

from events import ActionReadyForExecution, BlueprintInvocation
from foundry.actions import assign_variable
from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)

"""
Defines the blueprint for the 'assign_variable' command.

This blueprint allows the AI to store a value in a named variable within the
ContextManager. This variable can then be referenced in subsequent commands,
allowing for more complex, multi-step operations.
"""


def _execute_assign_variable(invocation: BlueprintInvocation) -> ActionReadyForExecution:
    """Prepares the 'assign_variable' action for execution.

    This function is called by the FoundryManager when the 'assign_variable' blueprint
    is invoked. It extracts the necessary arguments from the invocation event
    and creates an ActionReadyForExecution event, which is then handled by the
    ExecutorService.

    Args:
        invocation: The BlueprintInvocation event containing the arguments
                    validated against the blueprint's parameter schema.

    Returns:
        An ActionReadyForExecution event configured to call the assign_variable action.
    """
    variable_name = invocation.args["variable_name"]
    value = invocation.args["value"]

    logger.info(f"Preparing 'assign_variable' action for variable: '{variable_name}'")

    action_args: Dict[str, Any] = {"variable_name": variable_name, "value": value}

    return ActionReadyForExecution(
        action_func=assign_variable,
        action_args=action_args,
        source_invocation=invocation,
    )


assign_variable_bp = Blueprint(
    name="assign_variable",
    description=(
        "Assigns a value to a variable in the context manager. This variable can be "
        "referenced in subsequent commands. The value can be any valid JSON type "
        "(string, number, boolean, object, or array)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "variable_name": {
                "type": "string",
                "description": "The name of the variable to assign the value to.",
            },
            "value": {
                "description": (
                    "The value to assign to the variable. This can be a string, "
                    "number, boolean, object, or array."
                )
            },
        },
        "required": ["variable_name", "value"],
    },
    execute=_execute_assign_variable,
)