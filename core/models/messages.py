# core/models/messages.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class MessageType(Enum):
    """
    Defines the different types of messages that can be displayed in the command deck.
    Each type will have its own distinct styling and presentation.
    """
    SYSTEM = "system"
    USER_INPUT = "user_input"
    AGENT_THOUGHT = "agent_thought"
    AGENT_RESPONSE = "agent_response"
    AGENT_PLAN_JSON = "agent_plan_json"  # A raw JSON plan from an agent
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"


@dataclass
class AuraMessage:
    """
    Standardized message structure for all command deck communications.
    Replaces raw text streaming with structured, type-aware messaging.
    """
    type: MessageType
    content: str
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Set timestamp if not provided"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @property
    def type_display_name(self) -> str:
        """Get the display name for the message type"""
        type_names = {
            MessageType.SYSTEM: "SYSTEM",
            MessageType.USER_INPUT: "USER",
            MessageType.AGENT_THOUGHT: "THOUGHT",
            MessageType.AGENT_RESPONSE: "AURA",
            MessageType.TOOL_CALL: "TOOL",
            MessageType.TOOL_RESULT: "RESULT",
            MessageType.ERROR: "ERROR",
            MessageType.AGENT_PLAN_JSON: "PLAN"
        }
        return type_names.get(self.type, self.type.value.upper())
    
    @property
    def is_user_facing(self) -> bool:
        """Check if this message should be prominently displayed to the user"""
        return self.type in {MessageType.USER_INPUT, MessageType.AGENT_RESPONSE, MessageType.ERROR}
    
    @property
    def is_internal(self) -> bool:
        """Check if this message is internal workflow information"""
        return self.type in {MessageType.AGENT_THOUGHT, MessageType.TOOL_CALL, MessageType.TOOL_RESULT, MessageType.AGENT_PLAN_JSON}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "type": self.type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuraMessage":
        """Create from dictionary"""
        return cls(
            type=MessageType(data["type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None,
            metadata=data.get("metadata")
        )

    @classmethod
    def system(cls, content: str, **metadata) -> "AuraMessage":
        """Create a system message"""
        return cls(MessageType.SYSTEM, content, metadata=metadata or None)

    @classmethod
    def user_input(cls, content: str, **metadata) -> "AuraMessage":
        """Create a user input message"""
        return cls(MessageType.USER_INPUT, content, metadata=metadata or None)

    @classmethod
    def agent_thought(cls, content: str, **metadata) -> "AuraMessage":
        """Create an agent thought message"""
        return cls(MessageType.AGENT_THOUGHT, content, metadata=metadata or None)

    @classmethod
    def agent_response(cls, content: str, **metadata) -> "AuraMessage":
        """Create an agent response message"""
        return cls(MessageType.AGENT_RESPONSE, content, metadata=metadata or None)

    @classmethod
    def tool_call(cls, content: str, tool_name: str = None, **metadata) -> "AuraMessage":
        """Create a tool call message"""
        meta = metadata or {}
        if tool_name:
            meta["tool_name"] = tool_name
        return cls(MessageType.TOOL_CALL, content, metadata=meta or None)

    @classmethod
    def tool_result(cls, content: str, tool_name: str = None, success: bool = True, **metadata) -> "AuraMessage":
        """Create a tool result message"""
        meta = metadata or {}
        if tool_name:
            meta["tool_name"] = tool_name
        meta["success"] = success
        return cls(MessageType.TOOL_RESULT, content, metadata=meta or None)

    @classmethod
    def error(cls, content: str, error_code: str = None, **metadata) -> "AuraMessage":
        """Create an error message"""
        meta = metadata or {}
        if error_code:
            meta["error_code"] = error_code
        return cls(MessageType.ERROR, content, metadata=meta or None)
