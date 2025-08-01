"""
Define the simple data structures for Blueprints and raw code instructions,
used for code generation.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict

logger = logging.getLogger(__name__)


@dataclass
class Blueprint:
    """
    Represents a template for generating code or other artifacts.

    Blueprints are the 'tools' the AVM can use. They define a structured
    template with named parameters that can be filled in to produce a
    final piece of code or configuration.
    """
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    template: str


@dataclass
class RawCodeInstruction:
    """
    Represents a direct, raw code instruction to be executed or displayed.

    This is used for LLM outputs that are not meant to fit into a structured
    Blueprint but are instead a direct command or piece of code.
    """
    code: str