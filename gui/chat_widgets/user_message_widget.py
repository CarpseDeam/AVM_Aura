# gui/chat_widgets/user_message_widget.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel


class UserMessageWidget(QWidget):
    """A custom widget for displaying messages from the user."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("UserMessageWidget")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)

        prompt_label = QLabel("👤")
        prompt_label.setObjectName("UserPromptLabel")

        self.message_label = QLabel(text)
        self.message_label.setWordWrap(True)

        layout.addWidget(prompt_label)
        layout.addWidget(self.message_label, 1)