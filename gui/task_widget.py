# gui/task_widget.py
import logging
import random
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen

logger = logging.getLogger(__name__)

# A set of characters to use for the "glitching" effect
SCRAMBLE_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_-+={}[]"


class TaskCheckbox(QWidget):
    """A custom-painted, retro-styled checkbox."""
    stateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False
        self.color = QColor("#FFB74D")  # Main brand orange

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.stateChanged.emit(self._checked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = QPen(self.color)
        pen.setWidth(2)
        painter.setPen(pen)

        if self._checked:
            painter.setBrush(self.color)
            painter.drawRect(rect)
            pen.setColor(QColor("#0d0d0d"))
            painter.setPen(pen)
            painter.drawLine(rect.left() + 3, rect.center().y(), rect.center().x(), rect.bottom() - 3)
            painter.drawLine(rect.center().x(), rect.bottom() - 3, rect.right() - 3, rect.top() + 3)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.setChecked(not self.isChecked())
        super().mousePressEvent(event)


class TaskWidget(QWidget):
    """A widget representing a single task with a Matrix-style decoding animation."""
    task_state_changed = Signal(int, bool)

    def __init__(self, task_id: int, description: str, is_done: bool, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.real_description = description

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.checkbox = TaskCheckbox()
        self.description_label = QLabel("")  # Start with empty text
        self.description_label.setWordWrap(True)
        # Use a monospaced font for that classic terminal look
        self.description_label.setStyleSheet("font-family: 'Courier New', monospace;")

        layout.addWidget(self.checkbox)
        layout.addWidget(self.description_label)

        self.checkbox.stateChanged.connect(self._on_state_changed)
        self.set_done_state(is_done)

        # Animation state
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._update_scramble_animation)
        self.animation_step = 0
        self.total_steps = len(self.real_description) + 5  # A few extra steps for effect

        if not is_done:
            self.start_scramble_animation()
        else:
            self.description_label.setText(self.real_description)

    def start_scramble_animation(self):
        """Kicks off the decoding animation."""
        self.animation_step = 0
        self.animation_timer.start(30)  # Fire every 30ms

    def _update_scramble_animation(self):
        """Called by the QTimer to update the text for one frame."""
        self.animation_step += 1

        if self.animation_step >= self.total_steps:
            # Animation finished, show the real text and stop
            self.description_label.setText(self.real_description)
            self.animation_timer.stop()
            return

        # Determine how much of the real text to reveal
        reveal_count = int((self.animation_step / self.total_steps) * len(self.real_description))

        revealed_text = self.real_description[:reveal_count]
        scrambled_text = ""
        for _ in range(len(self.real_description) - reveal_count):
            scrambled_text += random.choice(SCRAMBLE_CHARS)

        self.description_label.setText(revealed_text + scrambled_text)

    def _on_state_changed(self, is_checked: bool):
        self.set_done_state(is_checked)
        self.task_state_changed.emit(self.task_id, is_checked)

    def set_done_state(self, is_done: bool):
        """Updates the visual style based on the task's completion state."""
        self.checkbox.setChecked(is_done)

        font = self.description_label.font()
        font.setStrikeOut(is_done)
        self.description_label.setFont(font)

        if is_done:
            self.description_label.setStyleSheet("color: #888888; font-family: 'Courier New', monospace;")
            self.checkbox.color = QColor("#888888")
        else:
            # Use the main brand orange for pending tasks
            self.description_label.setStyleSheet("color: #FFB74D; font-family: 'Courier New', monospace;")
            self.checkbox.color = QColor("#FFB74D")

        self.checkbox.update()  # Redraw checkbox with new color if needed```

