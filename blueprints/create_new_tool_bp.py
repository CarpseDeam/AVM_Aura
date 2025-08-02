# blueprints/create_new_tool_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import create_new_tool

# This is the schema that the LLM will see. It's a contract that tells the LLM
# exactly how to call our new 'create_new_tool' action.
params = {
    "type": "object",
    "properties": {
        "tool_name": {
            "type": "string",
            "description": "The unique ID for the new tool (e.g., 'rename_file'). Must be a valid Python identifier in snake_case.",
        },
        "description": {
            "type": "string",
            "description": "A clear, user-facing description of what the new tool does.",
        },
        "parameters_json": {
            "type": "string",
            "description": "A string containing the entire JSON schema object for the new tool's parameters. Must be valid JSON. Example: '{\\\"type\\\": \\\"object\\\", \\\"properties\\\": {\\\"old_path\\\": {\\\"type\\\": \\\"string\\\"}}, \\\"required\\\": [\\\"old_path\\\"]}'",
        },
        "action_function_name": {
            "type": "string",
            "description": "The name of the Python function in foundry/actions.py that will execute the tool's logic. This should match the tool_name.",
        },
    },
    "required": ["tool_name", "description", "parameters_json", "action_function_name"],
}

# Finally, we create the Blueprint object itself, wiring together the ID,
# the description, the parameters, and the actual Python function to call.
blueprint = Blueprint(
    id="create_new_tool",
    description="Meta-Tool: Creates a new blueprint .py file, defining a new tool for the AVM. The corresponding Python action function must be added to foundry/actions.py manually by the user, and the application must be restarted.",
    parameters=params,
    action_function=create_new_tool
)