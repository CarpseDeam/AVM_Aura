# aura/core/prompt_templates/__init__.py
"""
Exposes the structured prompt classes for easy importing by services.
Each class in this module represents the "brain" or "thought process"
for a specific AI agent in the system.
"""
from .architect import ArchitectPrompt
from .coder import CoderPrompt
from .replan import RePlannerPrompt
from .summarizer import MissionSummarizerPrompt

__all__ = [
    "ArchitectPrompt",
    "CoderPrompt",
    "RePlannerPrompt",
    "MissionSummarizerPrompt",
]