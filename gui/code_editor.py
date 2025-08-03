# gui/code_editor.py
import logging
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit
from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QTextFormat, QTextCursor

logger = logging.getLogger(__name__)


class LineNumberArea(QWidget):
    """Widget for showing line numbers next to the code editor."""

    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class AuraCodeEditor(QPlainTextEdit):
    """
    Aura's custom code editor with line numbers and current-line highlighting,
    styled with a retro-futurist theme.
    """
    content_changed = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.line_number_area = LineNumberArea(self)
        self._is_dirty = False
        self._original_content = ""

        self._setup_styling_and_behavior()

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.textChanged.connect(self._on_content_changed)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def _setup_styling_and_behavior(self):
        """Sets fonts, colors, and other style-related properties."""
        font = "JetBrains Mono"
        # Fallback fonts
        if font not in self.font().family():
            font = "Consolas"
        if font not in self.font().family():
            font = "Courier New"

        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

        # Retro theme colors
        self.current_line_color = QColor("#2a2a2a")  # Slightly lighter than bg
        self.line_number_color = QColor("#888888") # Muted grey
        self.line_number_bg_color = QColor("#1a1a1a") # Same as main window bg

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0d0d0d;
                color: #FFB74D; /* Retro Amber/Orange */
                border: 1px solid #333333;
                padding-left: 5px;
                selection-background-color: #4a4a4a;
            }}
        """)

    def _on_content_changed(self):
        """Internal slot to track if content has changed from original."""
        current_content = self.toPlainText()
        was_dirty = self._is_dirty
        self._is_dirty = current_content != self._original_content
        if was_dirty != self._is_dirty:
            self.content_changed.emit()

    def line_number_area_width(self):
        """Calculates the width needed for the line number area."""
        digits = 1
        count = max(1, self.blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        # Adjust padding for a cleaner look
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        """Updates the left margin of the editor to make room for line numbers."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """Scrolls the line number area along with the editor's text."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        """Called on resize, updates the geometry of the line number area."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        """Paints the line numbers."""
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self.line_number_bg_color)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        height = self.fontMetrics().height()

        while block.isValid() and (top <= event.rect().bottom()):
            if block.isVisible() and (bottom >= event.rect().top()):
                number = str(block_number + 1)
                painter.setPen(self.line_number_color)
                painter.drawText(0, int(top), self.line_number_area.width() - 5, height,
                                 Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        """Highlights the line where the cursor is currently located."""
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(self.current_line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)