# aura/gui/chat_widgets/transmission_review_widget.py
from PySide6.QtWidgets import QFrame
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics


class TransmissionReviewWidget(QFrame):
    """A custom-painted, retro-themed widget for reviewing and approving code changes."""

    changes_approved = Signal()
    changes_discarded = Signal()

    def __init__(self, summary: str, diff_text: str, branch_name: str, parent=None):
        super().__init__(parent)
        self.summary = summary
        self.diff_lines = diff_text.split('\n')
        self.branch_name = branch_name

        # --- Theme & Fonts ---
        self.font = QFont("Courier New", 14)
        self.fm = QFontMetrics(self.font)
        self.line_height = self.fm.height()
        self.char_width = self.fm.horizontalAdvance(' ')

        self.bg_color = QColor("#0d0d0d")
        self.border_color = QColor("#FFB74D")  # Amber
        self.text_color = QColor("#d4d4d4")
        self.added_color = QColor("#38761d")  # Dark Green
        self.removed_color = QColor("#990000")  # Dark Red

        # --- Interactivity ---
        self.approve_button_rect = None
        self.discard_button_rect = None
        self.setMouseTracking(True)  # Needed for hover effects

        self.setMinimumHeight(self._calculate_height())

    def _calculate_height(self) -> int:
        """Calculate the total required height for the widget."""
        # This is a simplified calculation. A real implementation would be more robust.
        num_lines = 10 + len(self.summary.split('\n')) + len(self.diff_lines)
        return num_lines * self.line_height

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font)
        painter.fillRect(self.rect(), self.bg_color)

        painter.setPen(self.border_color)

        # This is where we would draw all the ASCII borders, headers, and text
        # It's a complex but super fun process! We'd have helper methods like:
        # self._draw_border(painter)
        # self._draw_header(painter, "AGENT'S SUMMARY", y_pos)
        # self._draw_wrapped_text(painter, self.summary, text_rect)
        # self._draw_diff_text(painter, diff_rect)
        # self._draw_buttons(painter)

        # For this example, let's just show the concept
        painter.drawText(20, 40, f"Branch: {self.branch_name}")
        painter.drawText(20, 80, "--- SUMMARY ---")
        painter.drawText(20, 120, self.summary)
        painter.drawText(20, 200, "--- DIFF ---")

        y = 240
        for line in self.diff_lines:
            color = self.text_color
            if line.startswith('+'):
                color = self.added_color
            elif line.startswith('-'):
                color = self.removed_color

            painter.setPen(color)
            painter.drawText(20, y, line)
            y += self.line_height

        # Draw placeholder buttons
        painter.setPen(self.border_color)
        self.approve_button_rect = self.rect().adjusted(50, y, -50, y + 40)
        self.discard_button_rect = self.rect().adjusted(50, y + 60, -50, y + 100)

        painter.drawRect(self.approve_button_rect)
        painter.drawText(self.approve_button_rect, Qt.AlignmentFlag.AlignCenter, "[ APPROVE ]")

        painter.drawRect(self.discard_button_rect)
        painter.drawText(self.discard_button_rect, Qt.AlignmentFlag.AlignCenter, "[ DISCARD ]")

    def mousePressEvent(self, event):
        if self.approve_button_rect and self.approve_button_rect.contains(event.pos()):
            self.changes_approved.emit()
            # Here you would disable the buttons visually
            self.update()
        elif self.discard_button_rect and self.discard_button_rect.contains(event.pos()):
            self.changes_discarded.emit()
            self.update()