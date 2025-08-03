# gui/node_viewer_placeholder.py
from PySide6.QtWidgets import QMainWindow, QLabel
from PySide6.QtCore import Qt

class NodeViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Node Viewer")
        self.setGeometry(900, 100, 600, 500)
        label = QLabel("This is where the cool animated node viewer will go!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)