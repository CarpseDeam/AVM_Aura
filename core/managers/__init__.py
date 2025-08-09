# core/managers/__init__.py
# Manager exports for clean application architecture

from .service_manager import ServiceManager
from .window_manager import WindowManager
from .event_coordinator import EventCoordinator
from .workflow_manager import WorkflowManager
from .task_manager import TaskManager
from .project_manager import ProjectManager
from .git_manager import GitManager
from .venv_manager import VenvManager

__all__ = [
    'ServiceManager',
    'WindowManager',
    'EventCoordinator',
    'WorkflowManager',
    'TaskManager',
    'ProjectManager',
    'GitManager',
    'VenvManager'
]