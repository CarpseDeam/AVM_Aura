# gui/chat_widgets/user_message_widget.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame, QSizePolicy


class UserMessageWidget(QFrame):
    """A custom widget for displaying messages from the user, styled like a terminal input."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("UserMessageWidget")

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        prompt_label = QLabel("❯")
        prompt_label.setObjectName("UserPromptLabel")

        self.message_label = QLabel(text)
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(prompt_label)
        layout.addWidget(self.message_label, 1)

        self._apply_stylesheet()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #UserMessageWidget {
                background-color: #1f1f1f;
                border-radius: 5px;
            }
            #UserPromptLabel {
                color: #FFB74D;
                font-size: 18px;
                font-weight: bold;
            }
        """)