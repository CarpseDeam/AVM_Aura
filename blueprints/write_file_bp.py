import logging
from typing import Dict, Any

from events import ActionReadyForExecution, BlueprintInvocation
from foundry.actions import write_file
from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)

"""
Defines the blueprint for the 'write_file' command.

This blueprint allows the AI to write or overwrite content to a specified file
in the project's workspace.
"""


def _execute_write_file(invocation: BlueprintInvocation) -> ActionReadyForExecution:
    """Prepares the 'write_file' action for execution.

    This function is called by the FoundryManager when the 'write_file' blueprint
    is invoked. It extracts the necessary arguments from the invocation event
    and creates an ActionReadyForExecution event, which is then handled by the
    ExecutorService.

    Args:
        invocation: The BlueprintInvocation event containing the arguments
                    validated against the blueprint's parameter schema.

    Returns:
        An ActionReadyForExecution event configured to call the write_file action.
    """
    filename = invocation.args["filename"]
    content = invocation.args["content"]

    logger.info(f"Preparing 'write_file' action for file: {filename}")

    action_args = {"filename": filename, "content": content}

    return ActionReadyForExecution(
        action_func=write_file,
        action_args=action_args,
        source_invocation=invocation,
    )


write_file_bp = Blueprint(
    name="write_file",
    description=(
        "Writes content to a specified file. Creates the file if it doesn't "
        "exist, and overwrites it if it does."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "The relative path of the file to write to. "
                    "Directories will be created if they don't exist."
                ),
            },
            "content": {
                "type": "string",
                "description": "The content to write into the file.",
            },
        },
        "required": ["filename", "content"],
    },
    execute=_execute_write_file,
)