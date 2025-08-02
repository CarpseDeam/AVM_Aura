# blueprints/define_function_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import define_function

params = {
    "type": "object", 
    "properties": {
        "name": {"type": "string", "description": "The name of the function."},
        "args": {
            "type": "array", 
            "items": {"type": "string"}, 
            "description": "A list of argument names for the function."
        }
    }, 
    "required": ["name"]
}

blueprint = Blueprint(
    id="define_function",
    description="Defines a new Python function with specified arguments. The body will be empty (pass).",
    parameters=params,
    action_function=define_function
)