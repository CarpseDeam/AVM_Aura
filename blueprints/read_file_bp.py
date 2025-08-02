# blueprints/read_file_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import read_file

params = {
    "type": "object", "properties": {
        "path": {"type": "string", "description": "The relative path of the file to read."}
    }, "required": ["path"]
}

blueprint = Blueprint(
    name="read_file",
    description="Reads the entire content of a specified file.",
    template="",
    parameters=params,
    execution_logic=read_file
)