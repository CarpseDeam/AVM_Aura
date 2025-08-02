# blueprints/function_call_bp.py

"""
Blueprint definition for the 'function_call' action.

This file creates a Blueprint instance that exposes the ability to create a
Python function call to the LLM. The blueprint specifies the parameters required
(the function's name and its arguments) and maps them to the corresponding
action in foundry.actions.
"""

import logging

from foundry.blueprints import Blueprint
from foundry.actions import function_call

logger = logging.getLogger(__name__)

function_call_blueprint = Blueprint(
    id="function_call",
    description=(
        "Creates a Python function call statement. This is useful for invoking "
        "existing functions within the code. Arguments are provided as a single "
        "comma-separated string. Each argument is parsed as a literal (e.g., "
        "\"'hello'\", \"123\") or treated as a variable name if literal parsing "
        "fails. This creates an AST node for the function call, which can then "
        "be inserted into a file's AST."
    ),
    parameters=[
        {
            "name": "function_name",
            "type": "string",
            "description": "The name of the function to call.",
            "required": True,
        },
        {
            "name": "args",
            "type": "string",
            "description": "A comma-separated string of arguments for the function "
                         "call (e.g., \"'a string', 42, some_variable\"). Use an "
                         "empty string for a function call with no arguments.",
            "required": True,
        },
    ],
    action=function_call,
)