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
        self.editors: Dict[str, AuraCodeEditor] = {}
        self._setup_initial_state()

    def _setup_initial_state(self):
        """Clears any existing tabs and shows a welcome message."""
        self.clear_all_tabs()
        welcome_label = QLabel("Awaiting files from Aura's core...")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("color: #888888; font-size: 18px;")
        self.tab_widget.addTab(welcome_label, "Welcome")

    def reset_to_welcome_screen(self):
        """Public method to safely reset the editor view."""
        self._setup_initial_state()

    def create_or_focus_tab(self, path_str: str, content: str):
        """
        Creates a new editor tab and starts the animation,
        or focuses the tab if it already exists.
        """
        norm_path = str(Path(path_str).resolve())

        if norm_path in self.editors:
            editor = self.editors[norm_path]
            # If content is different, start animation. Otherwise, just focus.
            if editor.toPlainText() != content:
                editor.animate_set_content(content)
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == editor:
                    self.tab_widget.setCurrentIndex(i)
                    return
        else:
            if self.tab_widget.count() == 1 and isinstance(self.tab_widget.widget(0), QLabel):
                self.tab_widget.removeTab(0)

            editor = AuraCodeEditor()
            self.editors[norm_path] = editor

            # Connect signals for dirty status
            editor.content_changed.connect(lambda: self._update_tab_title(norm_path))

            tab_name = Path(norm_path).name
            tab_index = self.tab_widget.addTab(editor, tab_name)
            self.tab_widget.setTabToolTip(tab_index, norm_path)
            self.tab_widget.setCurrentIndex(tab_index)

            # Start the animation
            editor.animate_set_content(content)
            logger.info(f"Created new editor tab for: {norm_path}")

    def stream_to_tab(self, path_str: str, chunk: str):
        """Finds or creates a tab and streams a chunk of content to it."""
        norm_path = str(Path(path_str).resolve())

        # If this is the first chunk for this file, create the tab.
        if norm_path not in self.editors:
            # Ensure the welcome message is cleared if it exists
            if self.tab_widget.count() == 1 and isinstance(self.tab_widget.widget(0), QLabel):
                self.tab_widget.removeTab(0)

            editor = AuraCodeEditor()
            self.editors[norm_path] = editor
            editor.content_changed.connect(lambda: self._update_tab_title(norm_path))

            tab_name = Path(norm_path).name
            tab_index = self.tab_widget.addTab(editor, tab_name)
            self.tab_widget.setTabToolTip(tab_index, norm_path)
            self.tab_widget.setCurrentIndex(tab_index)

            # Prepare the editor for the new content stream
            editor.start_streaming()

        # Append the chunk to the correct editor
        editor = self.editors[norm_path]
        editor.append_stream_chunk(chunk)

    def _update_tab_title(self, norm_path_str: str):
        """Updates the tab title to show an asterisk for dirty files."""
        if norm_path_str not in self.editors: return
        editor = self.editors[norm_path_str]
        base_name = Path(norm_path_str).name
        title = f"*{base_name}" if editor._is_dirty else base_name
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabToolTip(i) == norm_path_str:
                self.tab_widget.setTabText(i, title)
                break

    def clear_all_tabs(self):
        while self.tab_widget.count() > 0:
            widget_to_remove = self.tab_widget.widget(0)
            self.tab_widget.removeTab(0)
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.editors.clear()