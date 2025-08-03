# gui/code_viewer_placeholder.py
from PySide6.QtWidgets import QMainWindow, QLabel
from PySide6.QtCore import Qt

class CodeViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Code Viewer")
        self.setGeometry(900, 650, 600, 400)
        label = QLabel("This is where the multi-tab code viewer will go!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)