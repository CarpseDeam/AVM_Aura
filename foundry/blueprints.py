# foundry/blueprints.py

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Blueprint:
    """
    Represents a self-contained, executable tool that the AVM can use.

    This dataclass is the 'contract' for all blueprints. It defines the tool's
    name, its purpose, the parameters it accepts (in a JSON Schema format),
    and the actual Python function that gets executed when the tool is called.
    """
    # Use 'id' as the unique name for the tool, which is more intuitive.
    id: str
    description: str

    # The JSON-schema compliant parameter definition that the LLM will see.
    parameters: Dict[str, Any]

    # A direct reference to the Python function that performs the action.
    action_function: Callable[..., Any]

    # Template is kept for potential future use in more complex blueprints.
    template: str = ""


@dataclass
class RawCodeInstruction:
    """
    Represents a direct, raw code instruction to be executed or displayed.

    This is used for LLM outputs that are not meant to fit into a structured
    Blueprint but are instead a direct command or piece of code.
    """
    code: str
    language: str = "python"