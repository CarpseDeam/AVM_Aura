# blueprints/submit_plan_bp.py
from foundry.blueprints import Blueprint

params = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "A clear, user-facing explanation of the architectural decisions behind the plan.",
        },
        "plan": {
            "type": "array",
            "description": "A list of tool call objects that, when executed in sequence, will accomplish the user's goal.",
            "items": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"}
                },
                "required": ["tool_name", "arguments"]
            }
        }
    },
    "required": ["reasoning", "plan"],
}

blueprint = Blueprint(
    id="submit_plan",
    description="Submits a complete, multi-step plan for execution. This is the primary tool for the Architect.",
    parameters=params,
    action_function_name="submit_plan"
)