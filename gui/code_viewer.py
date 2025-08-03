# gui/code_viewer.py
import logging
from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox
from PySide6.QtCore import Qt

from .editor_manager import EditorManager

logger = logging.getLogger(__name__)


class CodeViewerWindow(QMainWindow):
    """
    The main code viewing and interaction window.
    It uses an EditorManager to handle the logic of the tabs.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aura - Code Viewer")
        self.setGeometry(150, 150, 1200, 800)

        self._init_ui()

    def _init_ui(self):
        """Initializes the UI, setting up the tab widget and editor manager."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        tab_widget = QTabWidget()
        tab_widget.setTabsClosable(True)
        tab_widget.setMovable(True)
        tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)

        self.editor_manager = EditorManager(tab_widget)
        main_layout.addWidget(tab_widget)

    def display_file(self, path_str: str, content: str):
        """
        Public method to be called by the GUIController to show a file.
        Delegates the work to the editor manager.
        """
        self.editor_manager.create_or_focus_tab(path_str, content)
        self.show_window()

    def _on_tab_close_requested(self, index: int):
        """Handles the user clicking the 'x' on a tab."""
        # For now, just close it. We'll add "unsaved changes" checks later.
        widget_to_remove = self.editor_manager.tab_widget.widget(index)
        norm_path = self.editor_manager.tab_widget.tabToolTip(index)

        if norm_path in self.editor_manager.editors:
            del self.editor_manager.editors[norm_path]

        self.editor_manager.tab_widget.removeTab(index)
        if widget_to_remove:
            widget_to_remove.deleteLater()

        if self.editor_manager.tab_widget.count() == 0:
            self.editor_manager._setup_initial_state()

    def show_window(self):
        """Shows the code viewer window, bringing it to the front."""
        if not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()