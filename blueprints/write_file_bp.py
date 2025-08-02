# blueprints/write_file_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import write_file

params = {
    "type": "object", "properties": {
        "path": {"type": "string", "description": "The path of the file to write to."},
        "content": {"type": "string", "description": "The content to write into the file."}
    }, "required": ["path", "content"]
}

blueprint = Blueprint(
    name="write_file",
    description="Writes content to a file. Overwrites if the file exists.",
    template="",
    parameters=params,
    execution_logic=write_file
)