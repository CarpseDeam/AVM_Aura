# gui/chat_widgets/system_alert_widget.py
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer

class SystemAlertWidget(QFrame):
    """A dramatic, flashing ASCII art banner for a system alert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SystemAlertWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setObjectName("SystemAlertLabel")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._setup_animation()
        self._apply_stylesheet()

    def _setup_animation(self):
        self.banner_text = """
███████╗██╗   ██╗███████╗████████╗███╗   ███╗      █████╗  ██╗     ███████╗████████╗
██╔════╝╚██╗ ██╔╝██╔════╝╚══██╔══╝████╗ ████║     ██╔══██╗██║     ██╔════╝╚══██╔══╝
███████╗ ╚████╔╝ ███████╗   ██║   ██╔████╔██║     ███████║██║     █████╗     ██║
╚════██║  ╚██╔╝  ╚════██║   ██║   ██║╚██╔╝██║     ██╔══██║██║     ██╔══╝     ██║
███████║   ██║   ███████║   ██║   ██║ ╚═╝ ██║     ██║  ██║███████╗███████╗   ██║
╚══════╝   ╚═╝   ╚══════╝   ╚═╝   ╚═╝     ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
"""
        self.flash_on = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(500) # Flash every 500ms

    def update_animation(self):
        self.flash_on = not self.flash_on
        if self.flash_on:
            self.label.setStyleSheet("color: #F44336;") # Red
        else:
            self.label.setStyleSheet("color: #440000;") # Dark Red
        self.label.setText(f"<pre>{self.banner_text}</pre>")

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #SystemAlertLabel {
                font-family: "Courier New", monospace;
                font-size: 10px;
                line-height: 1.0;
                font-weight: bold;
                text-align: center;
                padding: 20px;
            }
        """)