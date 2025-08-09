# gui/log_viewer.py
import logging
from PySide6.QtWidgets import QMainWindow, QTextEdit
from PySide6.QtCore import Slot, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QFont

from event_bus import EventBus

logger = logging.getLogger(__name__)


class LogViewerWindow(QMainWindow):
    """A window for displaying real-time application log messages."""

    log_received_signal = Signal(str, str, str)

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.setWindowTitle("Aura - Log Viewer")
        self.setGeometry(250, 250, 800, 600)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #0d0d0d; color: #d4d4d4; font-family: 'Consolas', monospace;")
        self.setCentralWidget(self.log_display)

        self.log_received_signal.connect(self.append_log_message)
        self.event_bus.subscribe("log_message_received", self.on_log_message)

        # Color formats
        self.formats = {
            "info": self._create_format(QColor("cyan")),
            "success": self._create_format(QColor("lime")),
            "warning": self._create_format(QColor("yellow")),
            "error": self._create_format(QColor("red"), bold=True),
        }
        self.default_format = self._create_format(QColor("white"))
        self.source_format = self._create_format(QColor("#FFB74D"))  # Amber

    def _create_format(self, color: QColor, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def on_log_message(self, source: str, level: str, message: str):
        """Receives log from any thread and emits a signal to the main thread."""
        self.log_received_signal.emit(source, level, message)

    @Slot(str, str, str)
    def append_log_message(self, source: str, level: str, message: str):
        """Appends a formatted log message to the display on the main thread."""
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        # Source
        cursor.insertText("[", self.default_format)
        cursor.insertText(source, self.source_format)
        cursor.insertText("] ", self.default_format)

        # Level
        log_format = self.formats.get(level.lower(), self.default_format)
        cursor.insertText(f"({level.upper()}) ", log_format)

        # Message
        cursor.insertText(message + "\n", self.default_format)

        self.log_display.setTextCursor(cursor)
        self.log_display.ensureCursorVisible()