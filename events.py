# events.py

"""
Defines the event types used for communication on the event bus.

This module contains dataclasses representing various events that can be published
and subscribed to within the application, facilitating a decoupled architecture.
"""

import logging
from dataclasses import dataclass, field
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
    auto_approve_plan: bool = False # Retained from previous feature


@dataclass
class UserCommandEntered(Event):
    """Event published when a user enters a command (e.g., /help)."""

    command: str
    args: List[str]


@dataclass
class BlueprintInvocation:
    """
    Represents a specific invocation of a tool based on a Blueprint.
    """
    blueprint: Blueprint
    parameters: Dict[str, Any]


@dataclass
class ActionReadyForExecution(Event):
    """
    Event published when a structured action is parsed and ready for execution.
    """
    instruction: Union[BlueprintInvocation, RawCodeInstruction, List[BlueprintInvocation]]


@dataclass
class PauseExecutionForUserInput(Event):
    """

    Published by the Executor when an action requires user input.
    """
    question: str


@dataclass
class PlanReadyForApproval(Event):
    """
    Published by the LLMOperator when a plan is generated in interactive mode.
    """
    plan: List[BlueprintInvocation] = field(default_factory=list)


@dataclass
class PlanApproved(Event):
    """
    Published by the GUI when the user clicks 'Approve' on a plan.
    """
    plan: List[BlueprintInvocation] = field(default_factory=list)


@dataclass
class PlanDenied(Event):
    """
    Published by the GUI when the user clicks 'Deny' on a plan.
    """
    pass


@dataclass
class DisplayFileInEditor(Event):
    """
    Published when a tool's action results in file content that should be
    displayed to the user in a proper code editor, not the chat log.
    """
    file_path: str
    file_content: str