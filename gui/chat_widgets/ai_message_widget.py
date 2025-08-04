# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import Qt


class AIMessageWidget(QFrame):
    """
    A custom widget for displaying messages from Aura, styled to look like
    a retro terminal transmission box. It handles its own painting to resize correctly.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("AIMessageWidget")

        # Crucial for allowing the widget to grow and shrink vertically
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Main layout holds the content; the box is painted around it
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)  # Padding inside the box

        # --- Author Label ---
        author_label = QLabel("[ Aura ]")
        author_label.setObjectName("AuraAuthorLabel")
        author_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # --- Message Label ---
        self.message_label = QLabel(text)
        self.message_label.setObjectName("AIMessageLabel")
        self.message_label.setWordWrap(True)
        # This tells the label to grow vertically as needed
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(author_label)
        layout.addWidget(self.message_label)

    def paintEvent(self, event):
        """Override the paint event to draw a custom, resizable ASCII-style box."""
        # This paint event is called *before* the child widgets are painted.
        # We first draw the background, then the border.
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get the current geometry
        rect = self.rect()
        width = rect.width()
        height = rect.height()

        # Define colors and pen
        bg_color = QColor("#111111")
        border_color = QColor("#444")
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)

        # Draw the main background rectangle
        painter.fillRect(rect, bg_color)

        # --- Draw the box-drawing characters programmatically ---
        # Top line
        painter.drawText(0, 10, "┌")
        painter.drawText(10, 10, "─" * (width - 20))  # Stretch the line
        painter.drawText(width - 10, 10, "┐")

        # Side lines
        painter.drawLine(0, 10, 0, height - 10)  # Left
        painter.drawLine(width - 1, 10, width - 1, height - 10)  # Right

        # Bottom line
        painter.drawText(0, height - 1, "└")
        painter.drawText(10, height - 1, "─" * (width - 20))
        painter.drawText(width - 10, height - 1, "┘")