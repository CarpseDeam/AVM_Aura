# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PySide6.QtCore import Qt, QPoint


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
        # We give the layout some margin so the text content doesn't touch the painted border
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5)

        # Make author label a member to get its geometry in the paintEvent
        self.author_label = QLabel("[ Aura ]")
        self.author_label.setObjectName("AuraAuthorLabel")
        self.author_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        # This is needed to ensure the label has a size for the first paint event
        self.author_label.adjustSize()

        # --- Message Label ---
        self.message_label = QLabel(text)
        self.message_label.setObjectName("AIMessageLabel")
        self.message_label.setWordWrap(True)
        # This tells the label to grow vertically as needed
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(self.author_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.message_label)

    def paintEvent(self, event):
        # We paint the border first, then call super() to draw the child widgets on top.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # If the label hasn't been placed by the layout manager, we can't draw the border yet.
        label_geom = self.author_label.geometry()
        if label_geom.width() == 0 or not self.author_label.isVisible():
            painter.fillRect(self.rect(), QColor("#0d0d0d")) # Just draw background
            super().paintEvent(event)
            return

        # Define our "stylish" colors
        border_color = QColor("#FFB74D")
        bg_color = QColor("#0d0d0d")

        # Fill the background first
        painter.fillRect(self.rect(), bg_color)

        # --- Prepare for drawing the border ---
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)

        # We need a monospaced font to draw the ASCII corners correctly
        font = self.font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        char_h_offset = fm.ascent() / 2 - 2 # Fine-tune vertical alignment of corners

        # --- Calculations ---
        rect = self.rect().adjusted(2, 2, -2, -2) # Inset for crispness
        top_line_y = label_geom.center().y()
        gap_start_x = label_geom.x() - 5
        gap_end_x = label_geom.right() + 5

        # --- Draw the border components ---
        # Top-left line
        painter.drawLine(rect.left(), top_line_y, gap_start_x, top_line_y)
        # Top-right line
        painter.drawLine(gap_end_x, top_line_y, rect.right(), top_line_y)
        # Left vertical line
        painter.drawLine(rect.left(), top_line_y, rect.left(), rect.bottom())
        # Right vertical line
        painter.drawLine(rect.right(), top_line_y, rect.right(), rect.bottom())
        # Bottom line
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        # Draw the ASCII corners on top of the line ends
        painter.drawText(QPoint(rect.left() - 1, top_line_y + char_h_offset), "┌")
        painter.drawText(QPoint(rect.right() - 2, top_line_y + char_h_offset), "┐")
        painter.drawText(QPoint(rect.left() - 1, rect.bottom() + char_h_offset), "└")
        painter.drawText(QPoint(rect.right() - 2, rect.bottom() + char_h_offset), "┘")

        # Let the default implementation draw the child widgets (our labels)
        super().paintEvent(event)