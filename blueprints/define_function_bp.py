# blueprints/define_function_bp.py

"""
Blueprint definition for the 'define_function' action.

This file creates a Blueprint instance that exposes the ability to define a new
Python function to the LLM. The blueprint specifies the parameters required
(function name and arguments) and maps them to the corresponding action in
foundry.actions.
"""

import logging

from foundry.blueprints import Blueprint
from foundry.actions import define_function

logger = logging.getLogger(__name__)

define_function_blueprint = Blueprint(
    id="define_function",
    description=(
        "Defines a new Python function with a specified name and arguments. "
        "The function body will be empty, containing only a 'pass' statement. "
        "This creates an AST node for the function definition, which can then be "
        "inserted into a file's AST."
    ),
    parameters=[
        {
            "name": "name",
            "type": "string",
            "description": "The name of the function to define.",
            "required": True,
        },
        {
            "name": "args",
            "type": "string",
            "description": "A comma-separated string of argument names for the function "
                         "(e.g., 'x, y, z'). Use an empty string for a function "
                         "with no arguments.",
            "required": True,
        },
    ],
    action=define_function,
)