# aura/core/prompt_templates/__init__.py
"""
Exposes the structured prompt classes for easy importing by services.
Each class in this module represents the "brain" or "thought process"
for a specific AI agent in the system.
"""
from .architect import ArchitectPrompt
from .coder import CoderPrompt
from .commit_author import CommitAuthorPrompt
from .creative import CreativeAssistantPrompt
from .dispatcher import ChiefOfStaffDispatcherPrompt
from .inquisitor import InquisitorPrompt
from .iterative_architect import IterativeArchitectPrompt
from .replan import RePlannerPrompt
from .sentry import SENTRY_PROMPT
from .summarizer import MissionSummarizerPrompt

__all__ = [
    "ArchitectPrompt",
    "CoderPrompt",
    "CommitAuthorPrompt",
    "CreativeAssistantPrompt",
    "ChiefOfStaffDispatcherPrompt",
    "InquisitorPrompt",
    "IterativeArchitectPrompt",
    "RePlannerPrompt",
    "SENTRY_PROMPT",
    "MissionSummarizerPrompt",
]
