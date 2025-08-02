# blueprints/write_file_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import write_file

params = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path of the file to write to."
        },
        "content": {
            "type": "string",
            "description": "The content to write into the file."
        }
    },
    "required": ["path", "content"],
}

blueprint = Blueprint(
    id="write_file",
    description="Writes content to a file. Creates directories if needed and overwrites the file if it exists.",
    parameters=params,
    action_function=write_file
)