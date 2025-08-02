# blueprints/return_statement_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import return_statement

params = {
    "type": "object", 
    "properties": {
        "value": {"type": "string", "description": "The literal or variable name to return (e.g., \"'Success'\", \"x\")."}
    }, 
    "required": ["value"]
}

blueprint = Blueprint(
    id="return_statement",
    description="Creates a Python `return` statement inside a function.",
    parameters=params,
    action_function=return_statement
)