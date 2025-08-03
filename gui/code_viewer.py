# gui/code_viewer.py
import logging
from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox, QSplitter
from PySide6.QtCore import Qt

from .editor_manager import EditorManager
from .file_tree_manager import FileTreeManager
from services import ProjectManager

logger = logging.getLogger(__name__)


class CodeViewerWindow(QMainWindow):
    """
    The main code viewing and interaction window, with a file tree and editor tabs.
    """

    def __init__(self, project_manager: ProjectManager):
        super().__init__()
        self.project_manager = project_manager
        self.setWindowTitle("Aura - Code Viewer")
        self.setGeometry(150, 150, 1200, 800)

        self._init_ui()

    def _init_ui(self):
        """Initializes the UI, setting up the splitter, file tree, and editor manager."""
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        # --- Left Panel: File Tree ---
        self.file_tree_manager = FileTreeManager(project_manager=self.project_manager)
        self.file_tree_manager.set_file_selection_callback(self._on_file_selected_from_tree)
        main_splitter.addWidget(self.file_tree_manager.widget())

        # --- Right Panel: Editor Tabs ---
        tab_widget = QTabWidget()
        tab_widget.setTabsClosable(True)
        tab_widget.setMovable(True)
        tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.editor_manager = EditorManager(tab_widget)
        main_splitter.addWidget(tab_widget)

        # Set initial sizes for the splitter panels
        main_splitter.setSizes([300, 900])

    def load_project(self, project_path_str: str):
        """Loads a project into the file tree."""
        self.file_tree_manager.load_project(Path(project_path_str))
        self.setWindowTitle(f"Aura - Code Viewer - [{Path(project_path_str).name}]")

    def display_file(self, path_str: str, content: str):
        """
        Public method to be called by the GUIController to show a file.
        Delegates the work to the editor manager.
        """
        self.editor_manager.create_or_focus_tab(path_str, content)
        self.show_window()

    def _on_file_selected_from_tree(self, path: Path):
        """Callback for when a file is double-clicked in the file tree."""
        try:
            content = path.read_text(encoding='utf-8')
            self.editor_manager.create_or_focus_tab(str(path), content)
        except Exception as e:
            logger.error(f"Could not read file from tree: {path}. Error: {e}")
            QMessageBox.warning(self, "Read Error", f"Could not read file:\n{path.name}\n\n{e}")

    def _on_tab_close_requested(self, index: int):
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