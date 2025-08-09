# gui/status_bar_widget.py
from PySide6.QtWidgets import QStatusBar, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import QTimer, Qt


class StatusBarWidget(QStatusBar):
    """
    A persistent status bar for displaying Aura's current state and activity.
    Inherits from QStatusBar to be compatible with QMainWindow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(30)
        self.setVisible(False)  # Hidden by default

        # QStatusBar doesn't use a layout, so we add widgets directly
        # with addWidget or addPermanentWidget. We'll add them and
        # they will be arranged from left to right.

        self.status_label = QLabel("[ IDLE ]")
        self.status_label.setObjectName("StatusLabel")
        self.addWidget(self.status_label)

        self.activity_label = QLabel("Waiting for input...")
        self.activity_label.setObjectName("ActivityLabel")
        # The 'stretch' parameter in addWidget will make it take up available space
        self.addWidget(self.activity_label, 1)

        self.bar_label = QLabel("")
        self.bar_label.setObjectName("ThinkingBar")
        self.bar_label.setFixedWidth(250)
        # Use addPermanentWidget to align it to the right
        self.addPermanentWidget(self.bar_label)


        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_step = 0
        self.bar_width = 30  # A bit smaller for the status bar

        self._apply_stylesheet()

    def start_animation(self):
        self.animation_step = 0
        self.bar_label.setVisible(True)
        self.animation_timer.start(100)

    def stop_animation(self):
        self.animation_timer.stop()
        self.bar_label.setVisible(False)
        self.bar_label.setText("")

    def update_animation(self):
        self.animation_step = (self.animation_step + 1) % self.bar_width
        filled_chars = "■" * self.animation_step
        empty_chars = "·" * (self.bar_width - self.animation_step - 1)
        bar = f"[{filled_chars}{empty_chars}]"
        self.bar_label.setText(bar)

    def show_status(self, status: str, activity: str, animate: bool):
        self.status_label.setText(f"[ {status.upper()} ]")
        self.activity_label.setText(activity)

        if animate:
            self.start_animation()
        else:
            self.stop_animation()

        # Update stylesheet for different states
        if "IDLE" in status.upper():
            self.status_label.setStyleSheet("color: #4CAF50;")  # Green
        elif "FAIL" in status.upper() or "ERROR" in status.upper():
            self.status_label.setStyleSheet("color: #F44336;")  # Red
        else:
            self.status_label.setStyleSheet("color: #FFB74D;")  # Amber

        self.setVisible(True)

    def hide_status(self):
        self.setVisible(False)
        self.stop_animation()

    def _apply_stylesheet(self):
        # Apply styles to the StatusBar itself and its children
        self.setStyleSheet("""
            QStatusBar#StatusBar {
                background-color: #101010;
                border-top: 1px solid #333333;
            }
            QLabel#StatusLabel {
                font-weight: bold;
                color: #FFB74D;
                padding-left: 10px;
            }
            QLabel#ActivityLabel {
                color: #bbbbbb;
            }
            QLabel#ThinkingBar {
                color: #FFB74D;
                font-family: "Courier New", monospace;
                padding-right: 10px;
            }
        """)