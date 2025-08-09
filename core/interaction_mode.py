from enum import Enum, auto


class InteractionMode(Enum):
    """
    Represents the user's intended interaction with the AI.
    """
    PLAN = auto()   # For general conversation, brainstorming, and questions.
    BUILD = auto()  # For requests that should result in code generation or modification.