# blueprints/list_files_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import list_files

params = {
    "type": "object", "properties": {
        "path": {"type": "string", "description": "The directory path to list. Defaults to the current directory."}
    }, "required": []
}

blueprint = Blueprint(
    name="list_files",
    description="Lists all files and directories in a specified path.",
    template="",
    parameters=params,
    execution_logic=list_files
)