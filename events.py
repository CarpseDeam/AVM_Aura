from dataclasses import dataclass
from typing import List

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