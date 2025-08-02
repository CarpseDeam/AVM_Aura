# blueprints/assign_variable_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import assign_variable

params = {
    "type": "object",
    "properties": {
        "variable_name": {
            "type": "string",
            "description": "The name of the variable to create or assign to.",
        },
        "value": {
            "type": "string",
            "description": "The value to assign. This can be a literal (e.g., \"123\", \"'hello'\", \"True\") or an identifier for another variable (e.g., \"other_var\").",
        },
    },
    "required": ["variable_name", "value"],
}

blueprint = Blueprint(
    id="assign_variable",
    description="Creates a Python variable assignment AST node.",
    parameters=params,
    action_function=assign_variable
)