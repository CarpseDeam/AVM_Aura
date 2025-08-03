# events.py

"""
Defines the event types used for communication on the event bus.

This module contains dataclasses representing various events that can be published
and subscribed to within the application, facilitating a decoupled architecture.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Union

# The architect has specified that these types are available for import.
from foundry.blueprints import Blueprint, RawCodeInstruction

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base class for all events."""

    pass


@dataclass
class UserPromptEntered(Event):
    """Event published when a user enters a standard prompt."""

    prompt_text: str


@dataclass
class UserCommandEntered(Event):
    """Event published when a user enters a command (e.g., /help)."""

    command: str
    args: List[str]


@dataclass
class BlueprintInvocation:
    """
    Represents a specific invocation of a tool based on a Blueprint.

    This is a strongly-typed container that bundles a tool's definition (the
    Blueprint) with the specific arguments for a single call.

    Attributes:
        blueprint: The Blueprint defining the tool to be executed.
        parameters: A dictionary of arguments for this specific tool invocation.
    """

    blueprint: Blueprint
    parameters: Dict[str, Any]


@dataclass
class ActionReadyForExecution(Event):
    """
    Event published when a structured action is parsed and ready for execution.

    This event is typically created by the LLMOperator after successfully parsing
    a response from the language model. It is consumed by the ExecutorService,
    which performs the specified action.

    Attributes:
        instruction: A strongly-typed object representing the action to be
                     executed. This can be either a BlueprintInvocation (for
                     a predefined tool) or a RawCodeInstruction (for ad-hoc
                     code execution).
    """

    instruction: Union[BlueprintInvocation, RawCodeInstruction]


@dataclass
class PauseExecutionForUserInput(Event):
    """
    Published by the Executor when an action requires user input.
    The GUI should handle this by displaying the question and enabling input.
    """
    question: str