# foundry/blueprints.py

"""
Defines the simple data structures for Blueprints and raw code instructions,
used for code generation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Blueprint:
    """
    Represents a template for generating code or other artifacts.

    Blueprints are the 'tools' the AVM can use. They define a structured
    template with named parameters that can be filled in to produce a
    final piece of code or configuration. They can also be linked to a
    concrete Python function for direct execution.
    """
    # --- All required fields come FIRST ---
    name: str
    description: str
    template: str

    # --- Optional fields with default values come LAST ---
    parameters: Dict[str, Any] = field(default_factory=dict)
    execution_logic: Optional[Callable[..., Any]] = None


@dataclass
class RawCodeInstruction:
    """
    Represents a direct, raw code instruction to be executed or displayed.

    This is used for LLM outputs that are not meant to fit into a structured
    Blueprint but are instead a direct command or piece of code.
    """
    code: str
    language: str = "python"