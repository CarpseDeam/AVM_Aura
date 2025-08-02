import logging
from typing import Dict, Any

from events import ActionReadyForExecution, BlueprintInvocation
from foundry.actions import read_file
from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)

"""
Defines the blueprint for the 'read_file' command.

This blueprint allows the AI to read the content of a specified file
in the project's workspace.
"""


def _execute_read_file(invocation: BlueprintInvocation) -> ActionReadyForExecution:
    """Prepares the 'read_file' action for execution.

    This function is called by the FoundryManager when the 'read_file' blueprint
    is invoked. It extracts the necessary arguments from the invocation event
    and creates an ActionReadyForExecution event, which is then handled by the
    ExecutorService.

    Args:
        invocation: The BlueprintInvocation event containing the arguments
                    validated against the blueprint's parameter schema.

    Returns:
        An ActionReadyForExecution event configured to call the read_file action.
    """
    filename = invocation.args["filename"]

    logger.info(f"Preparing 'read_file' action for file: {filename}")

    action_args = {"filename": filename}

    return ActionReadyForExecution(
        action_func=read_file,
        action_args=action_args,
        source_invocation=invocation,
    )


read_file_bp = Blueprint(
    name="read_file",
    description="Reads the entire content of a specified file.",
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The relative path of the file to read from the project workspace.",
            },
        },
        "required": ["filename"],
    },
    execute=_execute_read_file,
)