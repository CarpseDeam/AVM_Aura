# blueprints/get_generated_code_bp.py
from foundry.blueprints import Blueprint
from foundry.actions import get_generated_code

blueprint = Blueprint(
    name="get_generated_code",
    description="Returns the Python code generated so far in the session.",
    template="",
    parameters={"type": "object", "properties": {}, "required": []},
    execution_logic=get_generated_code
)