# gui/editor_manager.py
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import QTabWidget, QLabel
from PySide6.QtCore import Qt

from .code_editor import AuraCodeEditor

logger = logging.getLogger(__name__)


class EditorManager:
    """Manages editor tabs with our custom AuraCodeEditor."""

    def __init__(self, tab_widget: QTabWidget):
        self.tab_widget = tab_widget
        # Maps a normalized file path string to its AuraCodeEditor instance
        self.editors: Dict[str, AuraCodeEditor] = {}
        self._setup_initial_state()

    def _setup_initial_state(self):
        """Clears any existing tabs and shows a welcome message."""
        self.clear_all_tabs()
        welcome_label = QLabel("Awaiting files from Aura's core...")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("color: #888888; font-size: 18px;")
        self.tab_widget.addTab(welcome_label, "Welcome")

    def create_or_focus_tab(self, path_str: str, content: str):
        """
        Creates a new editor tab for the given file path and content,
        or focuses the tab if it already exists.
        """
        # Normalize the path for consistent dictionary keys
        norm_path = str(Path(path_str).resolve())

        if norm_path in self.editors:
            # Tab already exists, just focus it
            editor = self.editors[norm_path]
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == editor:
                    self.tab_widget.setCurrentIndex(i)
                    return
        else:
            # If this is the first real tab, remove the welcome message
            if self.tab_widget.count() == 1 and isinstance(self.tab_widget.widget(0), QLabel):
                self.tab_widget.removeTab(0)

            # Create a new editor and tab
            editor = AuraCodeEditor()
            editor.setPlainText(content)
            self.editors[norm_path] = editor

            tab_name = Path(norm_path).name
            tab_index = self.tab_widget.addTab(editor, tab_name)
            self.tab_widget.setTabToolTip(tab_index, norm_path)
            self.tab_widget.setCurrentIndex(tab_index)
            logger.info(f"Created new editor tab for: {norm_path}")

    def clear_all_tabs(self):
        """Removes all tabs and clears the editor cache."""
        while self.tab_widget.count() > 0:
            widget_to_remove = self.tab_widget.widget(0)
            self.tab_widget.removeTab(0)
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.editors.clear()
