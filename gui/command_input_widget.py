# gui/command_input_widget.py
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent

class CommandInputWidget(QTextEdit):
    """
    A custom QTextEdit that emits a signal when Ctrl+Enter is pressed.
    """
    send_message_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent):
        """
        Overrides the key press event to handle the Ctrl+Enter shortcut.
        """
        is_ctrl_enter = (
            event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return) and
            (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        )

        if is_ctrl_enter:
            # User wants to send the message
            self.send_message_requested.emit()
            event.accept()  # We've handled this event
        else:
            # Default behavior for all other keys (including just Enter for a new line)
            super().keyPressEvent(event)