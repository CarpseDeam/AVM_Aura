# gui/task_widget.py
import logging
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFontMetrics

logger = logging.getLogger(__name__)


# --- Custom Checkbox Widget ---
class TaskCheckbox(QWidget):
    """A custom-painted, retro-styled checkbox."""
    stateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.update()  # Trigger a repaint
            self.stateChanged.emit(self._checked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)  # Add padding
        pen = QPen(QColor("#FFB74D"))  # Amber
        pen.setWidth(2)
        painter.setPen(pen)

        if self._checked:
            painter.setBrush(QColor("#FFB74D"))
            painter.drawRect(rect)
            # Draw a simple checkmark
            pen.setColor(QColor("#0d0d0d"))  # Dark background color
            painter.setPen(pen)
            painter.drawLine(rect.left() + 3, rect.center().y(), rect.center().x(), rect.bottom() - 3)
            painter.drawLine(rect.center().x(), rect.bottom() - 3, rect.right() - 3, rect.top() + 3)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.setChecked(not self.isChecked())
        super().mousePressEvent(event)


# --- The Main Task Widget ---
class TaskWidget(QWidget):
    """A widget representing a single task in the Mission Log."""
    task_state_changed = Signal(int, bool)  # task_id, is_done

    def __init__(self, task_id: int, description: str, is_done: bool, parent=None):
        super().__init__(parent)
        self.task_id = task_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.checkbox = TaskCheckbox()
        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.description_label)

        self.checkbox.stateChanged.connect(self._on_state_changed)
        self.set_done_state(is_done)

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
            self.description_label.setStyleSheet("color: #888888;")  # Muted grey
        else:
            self.description_label.setStyleSheet("color: #FFB74D;")  # Amber