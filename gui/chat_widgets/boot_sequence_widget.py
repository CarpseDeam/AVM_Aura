# gui/chat_widgets/boot_sequence_widget.py
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from gui.utils import get_aura_banner


class BootSequenceWidget(QFrame):
    """A widget that displays a cinematic, line-by-line boot sequence on startup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BootSequenceWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setObjectName("BootSequenceLabel")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.label)

        self._setup_animation_data()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_animation)
        self.timer.start(150)

        self._apply_stylesheet()

    def _setup_animation_data(self):
        self.boot_lines = [
            "[ AURA // INITIALIZING KERNEL ]",
            "[ OK ] Mounting virtual file system...",
            "[ OK ] Calibrating quantum chronometer...",
            "[ OK ] Loading cognitive models...",
            "       - Gemini 2.5 Pro (Google)... LOADED",
            "       - Deepseek Coder (Ollama)... LOADED",
            "[ OK ] Waking agent swarm...",
            "[ OK ] Establishing secure link to command deck...",
            " "
        ]
        self.line_index = 0
        self.displayed_text = ""

    def _update_animation(self):
        # Animate the boot lines one by one
        if self.line_index < len(self.boot_lines):
            self.displayed_text += self.boot_lines[self.line_index] + "\n"
            self.label.setText(f"<pre>{self.displayed_text}</pre>")
            self.line_index += 1
        else:
            # Animation of boot lines is done, now add the banner and final message instantly.
            self.timer.stop()

            banner = get_aura_banner()
            final_message = "System online. Waiting for command..."

            # Combine the already-displayed boot text with the static banner and final message
            # Explicitly add the correct spacing for the final message here.
            full_content = f"{self.displayed_text.strip()}\n{banner}\n   {final_message}"

            self.label.setText(f"<pre>{full_content}</pre>")

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #BootSequenceLabel {
                color: #FFB74D;
                font-family: "Courier New", monospace;
                font-size: 12px;
                line-height: 1.0;
            }
        """)