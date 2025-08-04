# gui/plan_approval_widget.py
import logging
from typing import List

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen

logger = logging.getLogger(__name__)


class PlanApprovalWidget(QFrame):
    """
    A custom widget for displaying a proposed plan and providing Approve/Deny buttons.
    It's designed to be embedded directly into the main chat log.
    """
    # Define signals that will be emitted when the user interacts with the widget.
    # We pass the original plan list back on approval.
    plan_approved = Signal(list)
    plan_denied = Signal()

    def __init__(self, plan: List, parent=None):
        super().__init__(parent)
        self.plan_data = plan
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("PlanApprovalWidget")

        # Main layout for the entire widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)  # Margins for the border

        # A container for the content, to allow for a drawn border
        content_frame = QFrame(self)
        content_frame.setObjectName("PlanContentFrame")
        main_layout.addWidget(content_frame)

        layout = QVBoxLayout(content_frame)
        layout.setContentsMargins(15, 10, 15, 10)  # Padding inside the border
        layout.setSpacing(10)

        # --- Header ---
        header_label = QLabel("[TRANSMISSION RECEIVED: PLANNING PROPOSAL]")
        header_label.setObjectName("PlanHeader")
        layout.addWidget(header_label)

        # --- Plan Steps ---
        plan_text = "Aura has formulated the following plan:\n\n"
        for i, step in enumerate(plan):
            tool_name = step.blueprint.id
            params = step.parameters
            # Simple, readable description of the step
            plan_text += f"  {i + 1}. {tool_name}({', '.join(f'{k}={v}' for k, v in params.items())})\n"
        plan_label = QLabel(plan_text)
        plan_label.setWordWrap(True)
        plan_label.setObjectName("PlanStepsLabel")
        layout.addWidget(plan_label)

        # --- Confirmation and Buttons ---
        confirmation_label = QLabel("Do you approve this course of action?")
        confirmation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(confirmation_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        self.approve_button = QPushButton("[ APPROVE ]")
        self.approve_button.setObjectName("PlanButton")
        self.approve_button.clicked.connect(self._on_approve)
        button_layout.addWidget(self.approve_button)

        self.deny_button = QPushButton("[ DENY ]")
        self.deny_button.setObjectName("PlanButton")
        self.deny_button.clicked.connect(self._on_deny)
        button_layout.addWidget(self.deny_button)

        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        self._apply_stylesheet()

    def _on_approve(self):
        """Handle the approve action."""
        logger.info("Plan approved by user.")
        self.plan_approved.emit(self.plan_data)
        self._disable_buttons()

    def _on_deny(self):
        """Handle the deny action."""
        logger.info("Plan denied by user.")
        self.plan_denied.emit()
        self._disable_buttons()

    def _disable_buttons(self):
        """Visually disable the buttons after a choice is made."""
        self.approve_button.setEnabled(False)
        self.deny_button.setEnabled(False)
        self.approve_button.setText("[ APPROVED ]")
        self.deny_button.setText("[ DENIED ]")
        # Update style to reflect disabled state
        self.approve_button.setStyleSheet("color: #006400; border: none;")  # Dark Green
        self.deny_button.setStyleSheet("color: #8B0000; border: none;")  # Dark Red

    def _apply_stylesheet(self):
        """Keep styles encapsulated within the widget."""
        self.setStyleSheet("""
            #PlanApprovalWidget {
                background-color: transparent;
            }
            #PlanContentFrame {
                border: 1px solid #FFB74D;
                background-color: #1a1a1a;
            }
            #PlanHeader {
                color: #FFB74D;
                font-weight: bold;
                border-bottom: 1px solid #444444;
                padding-bottom: 5px;
            }
            #PlanStepsLabel {
                font-family: "JetBrains Mono", "Consolas", monospace;
            }
            #PlanButton {
                background-color: transparent;
                border: none;
                color: #FFB74D;
                font-weight: bold;
                padding: 5px;
            }
            #PlanButton:hover {
                color: #ffffff;
            }
        """)