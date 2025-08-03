# gui/file_tree_manager.py
import logging
from pathlib import Path
from typing import Optional, Callable, Set

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QStyle, QWidget, QVBoxLayout
from PySide6.QtCore import Qt

from services import ProjectManager

logger = logging.getLogger(__name__)


class FileTreeManager:
    """
    Manages the file tree widget, populating it from the project directory
    and handling user interactions like double-clicking files.
    """
    def __init__(self, project_manager: ProjectManager):
        self.project_manager = project_manager
        self.on_file_selected_callback: Optional[Callable[[Path], None]] = None

        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree_widget = QTreeWidget()
        self._setup_tree_widget_appearance()
        layout.addWidget(self.tree_widget)

    def widget(self) -> QWidget:
        """Returns the container widget for the file tree."""
        return self._widget

    def set_file_selection_callback(self, callback: Callable[[Path], None]):
        """Sets the function to call when a file is double-clicked."""
        self.on_file_selected_callback = callback

    def _setup_tree_widget_appearance(self):
        """Configures the visual style of the QTreeWidget."""
        self.tree_widget.setHeaderLabel("Project Explorer")
        self.tree_widget.setStyleSheet(f"""
            QTreeWidget {{
                border: none;
                background-color: #1a1a1a;
                color: #cccccc;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 14px;
            }}
            QHeaderView::section {{
                background-color: #2a2a2a;
                color: #FFB74D;
                border: none;
                padding: 4px;
                font-weight: bold;
            }}
            QTreeWidget::item {{ padding: 4px; border: none; }}
            QTreeWidget::item:selected {{
                background-color: #FFB74D;
                color: #0d0d0d;
            }}
            QTreeWidget::item:hover {{
                background-color: #3a3a3a;
            }}
        """)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

    def load_project(self, project_path: Path):
        """Clears the current tree and populates it from the given project path."""
        logger.info(f"Loading project into file tree: {project_path}")
        self.tree_widget.clear()

        root_item = self._create_tree_item(
            text=project_path.name,
            path=project_path,
            is_dir=True,
            is_root=True
        )
        self.tree_widget.addTopLevelItem(root_item)
        self._populate_from_disk(root_item, project_path)
        root_item.setExpanded(True)

    def _populate_from_disk(self, parent_item: QTreeWidgetItem, directory_path: Path):
        """Recursively scans a directory and adds its contents to the tree."""
        try:
            # Sort entries to show directories first, then files, all alphabetically
            entries = sorted(list(directory_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
            for entry in entries:
                if entry.name.startswith('.') or entry.name == '__pycache__':
                    continue

                if entry.is_dir():
                    dir_item = self._create_tree_item(entry.name, entry, is_dir=True)
                    parent_item.addChild(dir_item)
                    self._populate_from_disk(dir_item, entry)
                else:
                    file_item = self._create_tree_item(entry.name, entry, is_dir=False)
                    parent_item.addChild(file_item)
        except Exception as e:
            logger.error(f"Error populating file tree from {directory_path}: {e}")

    def _create_tree_item(self, text: str, path: Path, is_dir: bool, is_root: bool = False) -> QTreeWidgetItem:
        """Helper function to create and configure a QTreeWidgetItem."""
        icon_provider = self.tree_widget.style()
        icon = icon_provider.standardIcon(QStyle.StandardPixmap.SP_DirIcon if is_dir else QStyle.StandardPixmap.SP_FileIcon)
        item = QTreeWidgetItem([text])
        item.setIcon(0, icon)
        item.setData(0, Qt.ItemDataRole.UserRole, path)  # Store the Path object
        if is_root:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handles the double-click event on a tree item."""
        path: Path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and path.is_file() and self.on_file_selected_callback:
            self.on_file_selected_callback(path)