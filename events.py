# events.py

"""
Defines the event types used for communication on the event bus.

This module contains dataclasses representing various events that can be published
and subscribed to within the application, facilitating a decoupled architecture.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Union, Optional

# The architect has specified that these types are available for import.
from foundry.blueprints import Blueprint, RawCodeInstruction

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base class for all events."""

    pass


@dataclass
class StatusUpdate(Event):
    """
    Published by backend services to update the GUI's persistent status bar.
    """
    status: str  # e.g., "PLANNING", "EXECUTING"
    activity: str  # e.g., "Architect is formulating a plan..."
    animate: bool = True
    progress: Optional[int] = None # e.g., 3
    total: Optional[int] = None # e.g., 12


@dataclass
class UserPromptEntered(Event):
    """Event published when a user enters a standard prompt."""

    prompt_text: str
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
    """
    instruction: Union[BlueprintInvocation, RawCodeInstruction, List[BlueprintInvocation]]


@dataclass
class DirectToolInvocationRequest(Event):
    """
    Published by a GUI component to execute a specific tool directly,
    bypassing the LLM.
    """
    tool_id: str
    params: Dict[str, Any]


@dataclass
class RefreshFileTreeRequest(Event):
    """
    Published by a service (like the Executor) to request that the
    GUI's file tree re-scans the disk.
    """
    pass


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
    This event carries the plan data to the ExecutorService.
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


@dataclass
class ProjectCreated(Event):
    """
    Published by the ExecutorService after a project is successfully created.
    """
    project_name: str
    project_path: str


@dataclass
class MissionLogUpdated(Event):
    """
    Published by the MissionLogService whenever the list of tasks changes.
    The GUI should listen for this to stay in sync.
    """
    tasks: List[Dict[str, Any]]


@dataclass
class MissionDispatchRequest(Event):
    """
    Published by the Mission Log window when the user clicks the 'Dispatch' button.
    This signals the system to begin autonomously executing the tasks in the log.
    """
    pass


@dataclass
class ToolsModified(Event):
    """
    Published by an action (like create_new_tool) to signal that the
    FoundryManager needs to rescan its available tools.
    """
    pass