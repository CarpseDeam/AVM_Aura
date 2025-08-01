"""
Defines the event types used for communication on the event bus.

This module contains dataclasses representing various events that can be published
and subscribed to within the application, facilitating a decoupled architecture.
"""

from dataclasses import dataclass
from typing import Any, Dict, List


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
class ActionReadyForExecution(Event):
    """
    Event published when a structured action is parsed and ready for execution.

    This event is typically created by the LLMOperator after successfully parsing
    a JSON response from the language model. It is consumed by the ExecutorService,
    which performs the specified action.

    Attributes:
        action: A dictionary representing the structured action. It is expected
                to have an 'action' key with a string value (the action name)
                and a 'parameters' key with a dictionary of arguments.
    """

    action: Dict[str, Any]