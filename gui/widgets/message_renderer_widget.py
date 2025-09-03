# gui/widgets/message_renderer_widget.py
from datetime import datetime
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QTextEdit, QFrame, QLabel, 
    QHBoxLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QTextBlockFormat

from core.models.messages import AuraMessage, MessageType


class MessageBlock(QFrame):
    """
    A single message block that displays one AuraMessage with appropriate styling.
    """
    
    def __init__(self, message: AuraMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.setObjectName("MessageBlock")
        self._setup_ui()
        self._apply_styling()
    
    def _setup_ui(self):
        """Setup the UI components for this message block"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        # Header with message type and timestamp
        header_layout = QHBoxLayout()
        
        # Message type label
        self.type_label = QLabel(f"[{self.message.type_display_name}]")
        self.type_label.setObjectName(f"MessageType_{self.message.type.value}")
        header_layout.addWidget(self.type_label)
        
        # Timestamp (for non-user-facing messages)
        if not self.message.is_user_facing:
            timestamp_str = self.message.timestamp.strftime("%H:%M:%S") if self.message.timestamp else ""
            self.timestamp_label = QLabel(timestamp_str)
            self.timestamp_label.setObjectName("MessageTimestamp")
            header_layout.addWidget(self.timestamp_label)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Content area
        self.content_label = QLabel(self.message.content)
        self.content_label.setObjectName(f"MessageContent_{self.message.type.value}")
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.content_label)
        
        # Add metadata if present (for tool calls, errors, etc.)
        if self.message.metadata:
            self._add_metadata_display(layout)
    
    def _add_metadata_display(self, layout):
        """Add metadata information for messages that have it"""
        if self.message.type == MessageType.TOOL_CALL and self.message.metadata:
            tool_name = self.message.metadata.get('tool_name', 'Unknown')
            meta_label = QLabel(f"Tool: {tool_name}")
            meta_label.setObjectName("MessageMetadata")
            layout.addWidget(meta_label)
        
        elif self.message.type == MessageType.ERROR and self.message.metadata:
            error_code = self.message.metadata.get('error_code')
            if error_code:
                meta_label = QLabel(f"Error Code: {error_code}")
                meta_label.setObjectName("MessageMetadata")
                layout.addWidget(meta_label)
    
    def _apply_styling(self):
        """Apply message-type specific styling"""
        # The styling is handled via CSS in the parent widget
        pass


class MessageRendererWidget(QScrollArea):
    """
    Advanced message renderer that displays structured AuraMessage objects
    with distinct styling for different message types. Replaces simple text streaming.
    """
    
    # Signal emitted when a new message is added
    message_added = Signal(AuraMessage)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MessageRenderer")
        self.messages: List[AuraMessage] = []
        self._setup_ui()
        self._apply_stylesheet()
        
        # Auto-scroll timer for smooth scrolling
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._scroll_to_bottom)
    
    def _setup_ui(self):
        """Setup the scrollable message container"""
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container widget for messages
        self.container = QWidget()
        self.container.setObjectName("MessageContainer")
        self.setWidget(self.container)
        
        # Main layout for messages
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(2)
        self.layout.addStretch(1)  # Push messages to top
    
    def add_message(self, message: AuraMessage):
        """
        Add a new structured message to the display.
        
        Args:
            message: AuraMessage object to display
        """
        if not message or not message.content.strip():
            return
            
        self.messages.append(message)
        
        # Create message block
        message_block = MessageBlock(message)
        
        # Insert the widget
        self.add_widget(message_block)
        
        # Emit signal
        self.message_added.emit(message)

    def add_widget(self, widget: QWidget):
        """
        Add a generic QWidget to the message display.
        This is used for custom interactive widgets that aren't simple messages.
        """
        if not widget:
            return
        
        # Insert before the stretch
        self.layout.insertWidget(self.layout.count() - 1, widget)
        
        # Auto-scroll after a short delay for better UX
        self.scroll_timer.start(50)
    
    def add_system_message(self, content: str):
        """Convenience method to add a system message"""
        self.add_message(AuraMessage.system(content))
    
    def add_user_message(self, content: str):
        """Convenience method to add a user message"""
        self.add_message(AuraMessage.user_input(content))
    
    def add_error_message(self, content: str, error_code: str = None):
        """Convenience method to add an error message"""
        self.add_message(AuraMessage.error(content, error_code=error_code))
    
    def clear_messages(self):
        """Clear all messages from the display"""
        # Remove all message blocks (keep the stretch)
        for i in reversed(range(self.layout.count() - 1)):
            child = self.layout.itemAt(i)
            if child.widget():
                child.widget().deleteLater()
                self.layout.removeItem(child)
        
        self.messages.clear()
    
    def get_messages(self) -> List[AuraMessage]:
        """Get all AuraMessage objects currently displayed"""
        return self.messages.copy()
    
    def _scroll_to_bottom(self):
        """Smoothly scroll to the bottom to show the latest message"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _apply_stylesheet(self):
        """Apply comprehensive styling for all message types"""
        self.setStyleSheet("""
            QScrollArea#MessageRenderer {
                background-color: #000000;
                border: none;
            }
            
            QWidget#MessageContainer {
                background-color: #000000;
            }
            
            QFrame#MessageBlock {
                background-color: transparent;
                border: none;
                margin: 2px 0px;
            }
            
            /* Message Type Labels */
            QLabel[objectName^="MessageType_system"] {
                color: #FFB74D; /* Amber */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_user_input"] {
                color: #4FC3F7; /* Bright Cyan/Blue */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_agent_thought"] {
                color: #78909C; /* Blue Grey */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_agent_response"] {
                color: #AED581; /* Light Green */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_tool_call"] {
                color: #F06292; /* Magenta */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_tool_result"] {
                color: #80CBC4; /* Teal */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            QLabel[objectName^="MessageType_error"] {
                color: #F44336; /* Red */
                font-weight: bold;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }
            
            /* Message Content */
            QLabel[objectName^="MessageContent_system"] {
                color: #FFB74D; /* Amber */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px;
                padding: 4px 0px;
            }
            
            QLabel[objectName^="MessageContent_user_input"] {
                color: #E1F5FE; /* Lighter Cyan/Blue */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 14px;
                font-weight: 500;
                padding: 6px 0px;
            }
            
            QLabel[objectName^="MessageContent_agent_thought"] {
                color: #90A4AE; /* Lighter Blue Grey */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
                font-style: italic;
                padding: 3px 0px;
                background-color: rgba(144, 164, 174, 0.05);
                border-left: 2px solid #546E7A;
                padding-left: 8px;
            }
            
            QLabel[objectName^="MessageContent_agent_response"] {
                color: #DCE775; /* Lime */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 14px;
                font-weight: 500;
                padding: 8px 0px;
                line-height: 1.4;
            }
            
            QLabel[objectName^="MessageContent_tool_call"] {
                color: #F8BBD0; /* Lighter Magenta */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
                padding: 4px 0px;
                background-color: rgba(240, 98, 146, 0.1);
                border-radius: 4px;
                padding: 6px;
            }
            
            QLabel[objectName^="MessageContent_tool_result"] {
                color: #A7FFEB; /* Lighter Teal */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
                padding: 4px 0px;
            }
            
            QLabel[objectName^="MessageContent_error"] {
                color: #FFCDD2; /* Light Red */
                background-color: rgba(244, 67, 54, 0.1);
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px;
                padding: 8px;
                border-radius: 4px;
                border-left: 3px solid #E53935;
            }
            
            /* Timestamps and Metadata */
            QLabel#MessageTimestamp {
                color: #616161;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 10px;
            }
            
            QLabel#MessageMetadata {
                color: #B0BEC5; /* Blue Grey */
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px;
                font-style: italic;
                padding-top: 2px;
            }
            
            /* Scrollbar Styling */
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 8px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical {
                background: #444444;
                min-height: 20px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #555555;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
