# gui/chat_widgets/mission_accomplished_widget.py
import random
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer


class MissionAccomplishedWidget(QFrame):
    """A cinematic, animated ASCII art banner for a successful mission."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MissionAccomplishedWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setObjectName("MissionAccomplishedLabel")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._setup_animation()
        self._apply_stylesheet()

    def _setup_animation(self):
        # Corrected "SUCCESS" banner
        self.banner_text = r"""
███████╗██╗   ██╗██████╗ ██████╗ ███████╗███████╗███████╗
██╔════╝██║   ██║██╔════╝██╔════╝ ██╔════╝██╔════╝██╔════╝
███████╗██║   ██║██║     ██║      █████╗  ███████╗███████╗
╚════██║██║   ██║██║     ██║      ██╔══╝  ╚════██║╚════██║
███████║╚██████╔╝╚██████╗╚██████╗ ███████╗███████║███████║
╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝
"""
        self.clean_banner_lines = [line for line in self.banner_text.strip("\n").split("\n")]
        self.scramble_chars = "▓▒░"
        self.animation_step = 0
        self.total_steps = len(self.clean_banner_lines) * 2  # Reveal takes half the time

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(80)

    def update_animation(self):
        self.animation_step += 1
        if self.animation_step > self.total_steps:
            self.timer.stop()
            self.label.setText(f"<pre>{self.banner_text}</pre>")  # Final clean version
            return

        animated_lines = []
        for i, line in enumerate(self.clean_banner_lines):
            reveal_point = (i + 1) * 2
            if self.animation_step < reveal_point:
                # Scramble the line
                animated_lines.append("".join(random.choice(self.scramble_chars) for _ in line))
            else:
                # Show the clean line
                animated_lines.append(line)

        animated_banner = "\n".join(animated_lines)
        self.label.setText(f"<pre>{animated_banner}</pre>")

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #MissionAccomplishedLabel {
                color: #4CAF50; /* Success Green */
                font-family: "Courier New", monospace;
                font-size: 10px;
                line-height: 1.0;
                font-weight: bold;
                text-align: center;
                padding: 20px;
            }
        """)