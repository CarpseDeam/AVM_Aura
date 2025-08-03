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
    # --- NEW: Flag to indicate if the user wants to auto-approve plans ---
    auto_approve_plan: bool = False


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
    This is used for single actions or for plans that have been auto-approved.
    """
    instruction: Union[BlueprintInvocation, RawCodeInstruction, List[BlueprintInvocation]]


@dataclass
class PauseExecutionForUserInput(Event):
    """
    Published by the Executor when an action requires user input.
    """
    question: str


# --- NEW: Events for the interactive plan approval workflow ---

@dataclass
class PlanReadyForApproval(Event):
    """
    Published by the LLMOperator when a plan is generated in interactive mode.
    The GUI should listen for this, display the plan, and await user action.
    """
    plan: List[BlueprintInvocation] = field(default_factory=list)


@dataclass
class PlanApproved(Event):
    """
    Published by the GUI when the user clicks 'Approve' on a plan.
    The ExecutorService listens for this to proceed with execution.
    """
    plan: List[BlueprintInvocation] = field(default_factory=list)


@dataclass
class PlanDenied(Event):
    """
    Published by the GUI when the user clicks 'Deny' on a plan.
    This can be used to inform the user the action was cancelled.
    """
    pass