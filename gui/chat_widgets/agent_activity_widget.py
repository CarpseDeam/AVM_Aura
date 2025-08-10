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
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.art_label)

        # Animation state
        self.animation_step = 0
        self.blip_position = 0
        self.box_width = 80
        self.box_height = 3
        self.perimeter = 2 * (self.box_width - 1) + 2 * (self.box_height - 1)
        self.is_pulsing = False
        self.text_content = ""

        # Timer setup
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)

        self._apply_stylesheet()

    def start_pulsing(self, text: str):
        """Starts the generic 'thinking' animation."""
        self.is_pulsing = True
        self.text_content = text
        if not self.timer.isActive():
            self.timer.start(75)

    def set_agent_status(self, logo: str, agent_name: str, activity: str):
        """Stops the pulsing and displays a specific agent's status and art in a static box."""
        self.is_pulsing = False
        if self.timer.isActive():
            self.timer.stop()

        final_text = f" {logo} — [ {agent_name} // {activity.upper()} ] "
        h_bar = '─'
        v_bar = '│'

        top = f"┌{h_bar * (self.box_width - 2)}┐"
        middle = f"{v_bar}{final_text.center(self.box_width - 2)}{v_bar}"
        bottom = f"└{h_bar * (self.box_width - 2)}┘"

        full_art = f"<pre>{top}\n{middle}\n{bottom}</pre>"
        self.art_label.setText(full_art)

    def update_animation(self):
        """Redraws the ASCII box for the current animation frame if pulsing."""
        if not self.is_pulsing:
            return

        self.animation_step += 1
        self.blip_position = (self.blip_position + 1) % self.perimeter

        # Pulsing characters
        corner_chars = ['+', 'x']
        h_chars = ['─', '═']
        v_chars = ['│', '║']

        frame_index = self.animation_step % 2
        corner, h_bar, v_bar = corner_chars[frame_index], h_chars[frame_index], v_chars[frame_index]

        # Create the lines of the box
        top = list(f"{corner}{h_bar * (self.box_width - 2)}{corner}")
        middle = list(f"{v_bar} {self.text_content.center(self.box_width - 4)} {v_bar}")
        bottom = list(f"{corner}{h_bar * (self.box_width - 2)}{corner}")
        lines = [top, middle, bottom]

        blip_char = '█'
        w = self.box_width
        h = self.box_height
        p = self.blip_position

        # Top edge
        if p < w:
            lines[0][p] = blip_char
        # Right edge
        elif p < w + (h - 2):
            lines[1][w - 1] = blip_char
        # Bottom edge
        elif p < w + (h - 2) + w:
            idx = (w - 1) - (p - (w + h - 2))
            lines[2][idx] = blip_char
        # Left edge
        else:
            lines[1][0] = blip_char

        final_art = "\n".join("".join(line) for line in lines)
        self.art_label.setText(f"<pre>{final_art}</pre>")

    def stop_animation(self):
        self.timer.stop()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #AgentActivityWidget {
                background-color: #0d0d0d;
                border-radius: 5px;
                padding: 10px;
            }
            #AsciiArtLabel {
                color: #FFB74D;
                font-family: "Courier New", monospace;
                font-size: 14px;
                line-height: 1.0;
            }
        """)