# blueprints/list_files_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import list_files

params = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The directory path to list. Defaults to the current directory if not provided.",
        }
    },
    "required": [],
}

blueprint = Blueprint(
    id="list_files",
    description="Lists all files and directories in a specified path.",
    parameters=params,
    action_function=list_files
)