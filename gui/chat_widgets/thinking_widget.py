# gui/chat_widgets/thinking_widget.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import QTimer, Qt


class ThinkingWidget(QWidget):
    """A widget that displays a 'Thinking...' message with an animated ASCII loading bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ThinkingWidget")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)

        self.prompt_label = QLabel("🧠 Thinking...")
        self.prompt_label.setObjectName("ThinkingLabel")

        self.bar_label = QLabel("")
        self.bar_label.setObjectName("ThinkingBar")

        layout.addWidget(self.prompt_label)
        layout.addWidget(self.bar_label, 1)  # Let the bar take up remaining space

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)

        self.animation_step = 0
        self.bar_width = 40
        self._apply_stylesheet()

    def start_animation(self):
        """Starts the animation timer."""
        self.animation_step = 0
        self.timer.start(100)  # Update every 100ms

    def stop_animation(self):
        """Stops the animation timer."""
        self.timer.stop()

    def update_animation(self):
        """Updates the ASCII loading bar to the next frame."""
        self.animation_step = (self.animation_step + 1) % self.bar_width

        filled_chars = "■" * self.animation_step
        empty_chars = "·" * (self.bar_width - self.animation_step - 1)

        bar = f"[{filled_chars}{empty_chars}]"
        self.bar_label.setText(bar)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #ThinkingWidget {
                background-color: transparent;
            }
            #ThinkingLabel {
                color: #888888;
            }
            #ThinkingBar {
                color: #FFB74D;
                font-family: "Courier New", monospace;
            }
        """)