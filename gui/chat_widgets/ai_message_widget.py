# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy


class AIMessageWidget(QFrame):
    """
    A custom widget for displaying messages from Aura, styled to look like
    a retro terminal transmission box using box-drawing characters.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("AIMessageWidget")

        # This is crucial for the layout to correctly resize the widget
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Header ---
        header = QFrame(self)
        header.setObjectName("AIHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        corner_tl = QLabel("┌─")
        corner_tl.setObjectName("BoxChar")

        author_label = QLabel("[ AURA ]")
        author_label.setObjectName("AuraAuthorLabel")

        line_label = QLabel()
        line_label.setObjectName("HeaderLine")
        line_label.setText("─" * 200)  # Long line to be clipped

        corner_tr = QLabel("─┐")
        corner_tr.setObjectName("BoxChar")

        header_layout.addWidget(corner_tl)
        header_layout.addWidget(author_label)
        header_layout.addWidget(line_label, 1)
        header_layout.addWidget(corner_tr)

        # --- Content ---
        content = QFrame(self)
        content.setObjectName("AIContent")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        border_left = QLabel("│")
        border_left.setObjectName("BoxChar")

        self.message_label = QLabel(text)
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.message_label.setMinimumHeight(self.message_label.sizeHint().height())

        border_right = QLabel("│")
        border_right.setObjectName("BoxChar")

        content_layout.addWidget(border_left)
        content_layout.addWidget(self.message_label, 1)
        content_layout.addWidget(border_right)

        # --- Footer ---
        footer = QFrame(self)
        footer.setObjectName("AIFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        corner_bl = QLabel("└")
        corner_bl.setObjectName("BoxChar")

        line_bottom = QLabel()
        line_bottom.setObjectName("HeaderLine")
        line_bottom.setText("─" * 200)

        corner_br = QLabel("┘")
        corner_br.setObjectName("BoxChar")

        footer_layout.addWidget(corner_bl)
        footer_layout.addWidget(line_bottom, 1)
        footer_layout.addWidget(corner_br)

        # Add components to main layout
        main_layout.addWidget(header)
        main_layout.addWidget(content)
        main_layout.addWidget(footer)