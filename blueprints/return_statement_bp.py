# blueprints/return_statement_bp.py

"""
Blueprint definition for the 'return_statement' action.

This file creates a Blueprint instance that exposes the ability to create a
Python return statement to the LLM. The blueprint specifies the parameter required
(the value to be returned) and maps it to the corresponding action in
foundry.actions.
"""

import logging

from foundry.blueprints import Blueprint
from foundry.actions import return_statement

logger = logging.getLogger(__name__)

return_statement_blueprint = Blueprint(
    id="return_statement",
    description=(
        "Creates a Python return statement. This is used to exit a function and "
        "optionally pass back a value. If the 'value' parameter is an empty "
        "string, a bare `return` is created. Otherwise, the value is parsed as "
        "a literal (e.g., \"'hello'\", \"123\") or treated as a variable name if "
        "literal parsing fails. This creates an AST node for the return "
        "statement, which can then be inserted into a function's body in the AST."
    ),
    parameters=[
        {
            "name": "value",
            "type": "string",
            "description": "The value to return. This can be a literal (e.g., "
                         "\"'a string'\", \"42\"), a variable name (e.g., "
                         "\"some_variable\"), or an empty string for a bare "
                         "`return` statement.",
            "required": True,
        },
    ],
    action=return_statement,
)