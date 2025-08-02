# blueprints/assign_variable_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import assign_variable

params = {
    "type": "object", "properties": {
        "variable_name": {"type": "string", "description": "The name of the variable."},
        "value": {"type": "string", "description": "The value to assign (e.g., \"123\", \"'hello'\", \"other_var\")."}
    }, "required": ["variable_name", "value"]
}

blueprint = Blueprint(
    name="assign_variable",
    description="Creates a Python variable assignment AST node.",
    template="",
    parameters=params,
    execution_logic=assign_variable
)