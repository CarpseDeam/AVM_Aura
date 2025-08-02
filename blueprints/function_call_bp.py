# blueprints/function_call_bp.py

"""
Blueprint definition for the 'function_call' action.

This file creates a Blueprint instance that exposes the ability to create a
Python function call to the LLM. The blueprint specifies the parameters required
(the function's name and its arguments) and maps them to the corresponding
action in foundry.actions.
"""

from foundry.blueprints import Blueprint
from foundry.actions import function_call

# <-- FIX: Changed parameter schema to the correct JSON schema format
params = {
    "type": "object",
    "properties": {
        "func_name": {
            "type": "string",
            "description": "The name of the function to call.",
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "A list of arguments for the function call (e.g., [\"'a string'\", \"42\", \"some_variable\"]).",
        },
    },
    "required": ["func_name"],
}


# <-- FIX: Renamed variable to 'blueprint' and changed 'action' to 'action_function'
blueprint = Blueprint(
    id="function_call",
    description=(
        "Creates a Python function call statement. This is useful for invoking "
        "existing functions within the code. Arguments are provided as a list of strings. "
        "Each argument is parsed as a literal (e.g., \"'hello'\", \"123\") or "
        "treated as a variable name if literal parsing fails."
    ),
    parameters=params,
    action_function=function_call,
)