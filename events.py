from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from foundry import Blueprint


@dataclass
class BlueprintInvocation:
    """Represents a specific invocation of a tool based on a Blueprint."""
    blueprint: Blueprint
    parameters: Dict[str, Any]


# --- Core Application & User Input Events ---

@dataclass
class UserPromptEntered:
    """Published when the user submits a request via the main chat input."""
    prompt_text: str
    conversation_history: List[Dict[str, Any]]
    image_bytes: Optional[bytes] = None
    image_media_type: Optional[str] = None
    code_context: Optional[Dict[str, str]] = None

@dataclass
class InteractionModeChangeRequested:
    """Published when the user clicks the Plan/Build mode toggle."""
    new_mode: Any # Should be InteractionMode enum

@dataclass
class AppStateChanged:
    """Published by AppStateService when the state (BOOTSTRAP/MODIFY) changes."""
    new_state: Any # Should be AppState enum
    project_name: Optional[str] = None

@dataclass
class InteractionModeChanged:
    """Published by AppStateService when the mode (PLAN/BUILD) changes."""
    new_mode: Any # Should be InteractionMode enum

@dataclass
class NewSessionRequested:
    """Published when the user requests to start a new, clean session."""
    pass

# --- AI Agent & Workflow Events ---

@dataclass
class AgentStatusChanged:
    """Published by AI agents to update the main status bar."""
    agent_name: str
    status_text: str
    icon_name: str

@dataclass
class AIWorkflowFinished:
    """Published when any main AI workflow (build or chat) completes or fails."""
    pass

# --- Code Generation & Streaming Events ---

@dataclass
class StreamCodeChunk:
    """Published by the Coder agent with a piece of generated code for a file."""
    filename: str
    chunk: str

@dataclass
class CodeGenerationComplete:
    """Published by the DevelopmentTeamService when all files have been generated."""
    generated_files: Dict[str, str]

# --- Mission Log & Execution Events ---

@dataclass
class MissionPlanReady:
    """Published by the Finalizer with a complete, tool-based execution plan."""
    plan: List[Dict[str, Any]]

@dataclass
class MissionDispatchRequest:
    """Published by the Mission Log UI when the user clicks 'Dispatch'."""
    pass

# --- Tool & Foundry Events ---

@dataclass
class DirectToolInvocationRequest:
    """For directly calling a tool, bypassing the AI workflow (e.g., from a context menu)."""
    tool_id: str
    params: Dict[str, Any]

# --- GUI & Window Management Events ---

@dataclass
class DisplayFileInEditor:
    """Requests that the Code Viewer open or focus a tab for a specific file."""
    file_path: str
    file_content: str

@dataclass
class RefreshFileTree:
    """Requests that the Code Viewer's file tree re-scans the disk."""
    pass

@dataclass
class LogMessageReceived:
    """A standardized event for logging to the Log Viewer window."""
    source: str
    level: str  # e.g., "info", "error", "success"
    message: str

@dataclass
class BranchUpdated:
    """Published by the ProjectManager when the Git branch changes."""
    branch_name: str

# --- LSP & Editor Events ---

@dataclass
class LSPDiagnosticsReceived:
    """Published by the LSPClientService when it receives diagnostics from the server."""
    uri: str
    diagnostics: List[Dict[str, Any]]

# --- Plugin Events ---

@dataclass
class PluginStateChanged:
    """Published by the PluginManager when a plugin's state changes."""
    plugin_name: str
    old_state: Any
    new_state: Any