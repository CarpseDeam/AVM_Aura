# gui/chat_widgets/agent_activity_widget.py
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer


class AgentActivityWidget(QFrame):
    """
    A versatile widget to display agent activity, from an initial pulsing
    "thinking" state to specific ASCII art for different agents.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentActivityWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.art_label = QLabel()
        self.art_label.setObjectName("AsciiArtLabel")
        self.art_label.setTextFormat(Qt.TextFormat.RichText)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.art_label)

        # Animation state
        self.animation_step = 0
        self.blip_position = 0
        self.box_width = 50
        self.is_pulsing = False

        # Timer setup
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)

        self._apply_stylesheet()

    def start_pulsing(self, text: str):
        """Starts the generic 'thinking' animation."""
        self.is_pulsing = True
        self.text_content = text
        self.perimeter = (self.box_width - 1) * 2 + (3 - 1) * 2
        if not self.timer.isActive():
            self.timer.start(75)

    def set_agent_status(self, art: str, text: str):
        """Stops the pulsing and displays a specific agent's status and art."""
        self.is_pulsing = False
        if self.timer.isActive():
            self.timer.stop()

        full_text = f"{art}\n{text}"
        self.art_label.setText(f"<pre>{full_text}</pre>")

    def update_animation(self):
        """Redraws the ASCII box for the current animation frame if pulsing."""
        if not self.is_pulsing:
            return

        self.animation_step += 1
        self.blip_position = (self.blip_position + 1) % self.perimeter

        corner_chars = ['+', 'x']
        h_chars = ['─', '═']
        v_chars = ['│', '║']

        frame_index = self.animation_step % 2
        corner, h_bar, v_bar = corner_chars[frame_index], h_chars[frame_index], v_chars[frame_index]

        top = f"{corner}{h_bar * (self.box_width - 2)}{corner}"
        middle = f"{v_bar} {self.text_content.center(self.box_width - 4)} {v_bar}"
        bottom = f"{corner}{h_bar * (self.box_width - 2)}{corner}"

        lines = [list(top), list(middle), list(bottom)]
        blip_char = '█'

        if self.blip_position < self.box_width:
            lines[0][self.blip_position] = blip_char
        elif self.blip_position < self.box_width + 2:
            lines[1][self.box_width - 1] = blip_char
        elif self.blip_position < self.box_width * 2 + 1:
            lines[2][self.box_width - (self.blip_position - (self.box_width + 1))] = blip_char
        else:
            lines[1][0] = blip_char

        final_art = "\n".join("".join(line) for line in lines)
        self.art_label.setText(f"<pre>{final_art}</pre>")

    def stop_animation(self):
        self.timer.stop()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #AgentActivityWidget {
                background-color: #1a1a1a;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 10px;
            }
            #AsciiArtLabel {
                color: #FFB74D;
                font-family: "Courier New", monospace;
                font-size: 12px;
                line-height: 1.0;
            }
        """)