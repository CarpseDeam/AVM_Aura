# gui/chat_widgets/user_message_widget.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame, QSizePolicy


class UserMessageWidget(QFrame):
    """A custom widget for displaying messages from the user, styled like a terminal input."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("UserMessageWidget")

        # Allow the widget to grow vertically to fit text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)  # Padding inside the bar
        layout.setSpacing(10)

        prompt_label = QLabel("❯")  # Using a classic terminal prompt symbol
        prompt_label.setObjectName("UserPromptLabel")

        self.message_label = QLabel(text)
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(prompt_label)
        layout.addWidget(self.message_label, 1)