import logging
from typing import Dict, Any

from events import ActionReadyForExecution, BlueprintInvocation
from foundry.actions import list_files
from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)

"""
Defines the blueprint for the 'list_files' command.

This blueprint allows the AI to list the files and directories within a specified
path in the project's workspace.
"""


def _execute_list_files(invocation: BlueprintInvocation) -> ActionReadyForExecution:
    """Prepares the 'list_files' action for execution.

    This function is called by the FoundryManager when the 'list_files' blueprint
    is invoked. It extracts the necessary arguments from the invocation event
    and creates an ActionReadyForExecution event, which is then handled by the
    ExecutorService.

    Args:
        invocation: The BlueprintInvocation event containing the arguments
                    validated against the blueprint's parameter schema.

    Returns:
        An ActionReadyForExecution event configured to call the list_files action.
    """
    path = invocation.args.get("path")  # 'path' is optional

    logger.info(f"Preparing 'list_files' action for path: {path or './'}")

    action_args: Dict[str, Any] = {}
    if path:
        action_args["path"] = path

    return ActionReadyForExecution(
        action_func=list_files,
        action_args=action_args,
        source_invocation=invocation,
    )


list_files_bp = Blueprint(
    name="list_files",
    description=(
        "Lists files and directories in a specified path within the project "
        "workspace. If no path is provided, it lists the contents of the root "
        "directory."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The optional relative path of the directory to list. "
                    "Defaults to the project root if not provided."
                ),
            },
        },
        "required": [],
    },
    execute=_execute_list_files,
)