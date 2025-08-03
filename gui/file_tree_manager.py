# gui/file_tree_manager.py
import logging
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QStyle, QWidget, QVBoxLayout, QMenu,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, QPoint

from services import ProjectManager
from event_bus import EventBus
from events import DirectToolInvocationRequest

logger = logging.getLogger(__name__)


class FileTreeManager:
    """
    Manages the file tree widget, populating it from the project directory
    and providing a context menu for file operations.
    """
    def __init__(self, project_manager: ProjectManager, event_bus: EventBus):
        self.project_manager = project_manager
        self.event_bus = event_bus
        self.on_file_selected_callback: Optional[Callable[[Path], None]] = None

        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree_widget = QTreeWidget()
        self._setup_tree_widget()
        layout.addWidget(self.tree_widget)

    def widget(self) -> QWidget:
        return self._widget

    def set_file_selection_callback(self, callback: Callable[[Path], None]):
        self.on_file_selected_callback = callback

    def _setup_tree_widget(self):
        self.tree_widget.setHeaderLabel("Project Explorer")
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border: none; background-color: #1a1a1a; color: #cccccc;
                font-family: "JetBrains Mono", "Consolas", monospace; font-size: 14px;
            }
            QHeaderView::section {
                background-color: #2a2a2a; color: #FFB74D; border: none;
                padding: 4px; font-weight: bold;
            }
            QTreeWidget::item { padding: 4px; border: none; }
            QTreeWidget::item:selected { background-color: #FFB74D; color: #0d0d0d; }
            QTreeWidget::item:hover { background-color: #3a3a3a; }
        """)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._show_context_menu)

    def load_project(self, project_path: Path):
        logger.info(f"Loading project into file tree: {project_path}")
        self.tree_widget.clear()
        root_item = self._create_tree_item(project_path.name, project_path, is_dir=True, is_root=True)
        self.tree_widget.addTopLevelItem(root_item)
        self._populate_from_disk(root_item, project_path)
        root_item.setExpanded(True)

    def _populate_from_disk(self, parent_item: QTreeWidgetItem, dir_path: Path):
        try:
            entries = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
            for entry in entries:
                if entry.name.startswith('.') or entry.name == '__pycache__':
                    continue
                item = self._create_tree_item(entry.name, entry, entry.is_dir())
                parent_item.addChild(item)
                if entry.is_dir():
                    self._populate_from_disk(item, entry)
        except Exception as e:
            logger.error(f"Error populating file tree from {dir_path}: {e}")

    def _create_tree_item(self, text: str, path: Path, is_dir: bool, is_root: bool = False) -> QTreeWidgetItem:
        icon = self.tree_widget.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon if is_dir else QStyle.StandardPixmap.SP_FileIcon)
        item = QTreeWidgetItem([text])
        item.setIcon(0, icon)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        if is_root:
            font = item.font(0); font.setBold(True); item.setFont(0, font)
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        path: Path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and path.is_file() and self.on_file_selected_callback:
            self.on_file_selected_callback(path)

    def _show_context_menu(self, position: QPoint):
        item = self.tree_widget.itemAt(position)
        if not item: return

        menu = QMenu()
        path: Path = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = path.is_dir()
        is_root = item.parent() is None

        target_dir = path if is_dir else path.parent

        new_file_action = menu.addAction("New File...")
        new_file_action.triggered.connect(lambda: self._handle_new_file(target_dir))
        new_folder_action = menu.addAction("New Folder...")
        new_folder_action.triggered.connect(lambda: self._handle_new_folder(target_dir))

        if not is_root:
            menu.addSeparator()
            rename_action = menu.addAction("Rename...")
            rename_action.triggered.connect(lambda: self._handle_rename(path))
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._handle_delete(path, is_dir))

        menu.exec(self.tree_widget.mapToGlobal(position))

    def _handle_new_file(self, target_dir: Path):
        name, ok = QInputDialog.getText(self._widget, "New File", "Enter file name:")
        if ok and name:
            new_path = target_dir / name
            self.event_bus.publish(DirectToolInvocationRequest('write_file', {'path': str(new_path), 'content': ''}))

    def _handle_new_folder(self, target_dir: Path):
        name, ok = QInputDialog.getText(self._widget, "New Folder", "Enter folder name:")
        if ok and name:
            new_path = target_dir / name
            self.event_bus.publish(DirectToolInvocationRequest('create_directory', {'path': str(new_path)}))

    def _handle_rename(self, old_path: Path):
        old_name = old_path.name
        new_name, ok = QInputDialog.getText(self._widget, "Rename", "Enter new name:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = old_path.with_name(new_name)
            self.event_bus.publish(DirectToolInvocationRequest('move_file', {'source_path': str(old_path), 'destination_path': str(new_path)}))

    def _handle_delete(self, path_to_delete: Path, is_dir: bool):
        reply = QMessageBox.question(self._widget, "Confirm Delete",
                                     f"Are you sure you want to delete '{path_to_delete.name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            tool_id = 'delete_directory' if is_dir else 'delete_file'
            self.event_bus.publish(DirectToolInvocationRequest(tool_id, {'path': str(path_to_delete)}))