# gui/code_viewer.py
import logging
from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QTabWidget, QMessageBox, QSplitter
from PySide6.QtCore import Qt

from .editor_manager import EditorManager
from .file_tree_manager import FileTreeManager
from services import ProjectManager
from event_bus import EventBus
from events import RefreshFileTreeRequest  # <-- THE MAIN FIX!

logger = logging.getLogger(__name__)


class CodeViewerWindow(QMainWindow):
    """
    The main code viewing and interaction window, with a file tree and editor tabs.
    """

    def __init__(self, project_manager: ProjectManager, event_bus: EventBus):
        super().__init__()
        self.project_manager = project_manager
        self.event_bus = event_bus
        self.setWindowTitle("Aura - Code Viewer")
        self.setGeometry(150, 150, 1200, 800)

        self._init_ui()
        self.event_bus.subscribe(RefreshFileTreeRequest, self.refresh_file_tree)

    def _init_ui(self):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        self.file_tree_manager = FileTreeManager(
            project_manager=self.project_manager,
            event_bus=self.event_bus
        )
        self.file_tree_manager.set_file_selection_callback(self._on_file_selected_from_tree)
        main_splitter.addWidget(self.file_tree_manager.widget())

        tab_widget = QTabWidget()
        tab_widget.setTabsClosable(True)
        tab_widget.setMovable(True)
        tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.editor_manager = EditorManager(tab_widget)
        main_splitter.addWidget(tab_widget)

        main_splitter.setSizes([300, 900])

    def load_project(self, project_path_str: str):
        self.file_tree_manager.load_project(Path(project_path_str))
        self.setWindowTitle(f"Aura - Code Viewer - [{Path(project_path_str).name}]")

    def refresh_file_tree(self, _event: RefreshFileTreeRequest): # <-- Linter fix
        logger.info("Received request to refresh file tree.")
        if self.project_manager.active_project_path:
            self.load_project(str(self.project_manager.active_project_path))

    def display_file(self, path_str: str, content: str):
        self.editor_manager.create_or_focus_tab(path_str, content)
        self.show_window()

    def _on_file_selected_from_tree(self, path: Path):
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
            self.editor_manager.reset_to_welcome_screen() # <-- Linter fix

    def show_window(self):
        if not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()