import logging
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit
from PySide6.QtCore import Qt, QRect, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QTextFormat, QTextCursor, QFont

from .syntax_highlighter import AuraSyntaxHighlighter

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
    Aura's custom code editor with line numbers, highlighting, and animations.
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
        self.highlighter = AuraSyntaxHighlighter(self.document())

        # --- Animation Components ---
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(5)  # Adjust for typing speed
        self.animation_timer.timeout.connect(self._animate_chunk)
        self.content_to_animate = ""
        self.animation_position = 0

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.textChanged.connect(self._on_content_changed)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def _setup_styling_and_behavior(self):
        editor_font = QFont("JetBrains Mono", 11)
        self.setFont(editor_font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)
        self.current_line_color = QColor("#2a2a2a")
        self.line_number_color = QColor("#888888")
        self.line_number_bg_color = QColor("#1a1a1a")
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #333333;
                padding-left: 5px;
                selection-background-color: #4a4a4a;
            }
        """)

    def animate_set_content(self, content: str):
        """Clears the editor and starts a streaming animation for new content."""
        if self.animation_timer.isActive():
            self.animation_timer.stop()

        self.clear()
        self.content_to_animate = content
        self.animation_position = 0
        self._original_content = content  # Set original content for dirty tracking
        self._is_dirty = False
        self.content_changed.emit()  # Ensure title bar is updated

        if self.content_to_animate:
            self.animation_timer.start()

    def _animate_chunk(self):
        """Appends the next chunk of text to the editor during animation."""
        chunk_size = 25  # How many characters to "type" per tick
        if self.animation_position < len(self.content_to_animate):
            chunk = self.content_to_animate[self.animation_position:self.animation_position + chunk_size]
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.insertPlainText(chunk)
            self.animation_position += chunk_size
        else:
            self.animation_timer.stop()
            self.content_to_animate = ""
            self.animation_position = 0

    def start_streaming(self):
        """Prepares the editor for a new stream of text."""
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        self.clear()
        self._original_content = ""
        self._is_dirty = False
        self.content_changed.emit()

    def append_stream_chunk(self, chunk: str):
        """Appends a chunk of text to the end of the editor."""
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(chunk)
        self._original_content += chunk # Keep track of the full content

    def keyPressEvent(self, event):
        """Stop animation if user starts typing."""
        if self.animation_timer.isActive():
            self.animation_timer.stop()
            self.setPlainText(self.content_to_animate)  # Instantly finish
        super().keyPressEvent(event)

    def _on_content_changed(self):
        """Internal slot to track if content has changed from original."""
        if self.animation_timer.isActive():
            return  # Don't mark as dirty during animation
        current_content = self.toPlainText()
        was_dirty = self._is_dirty
        self._is_dirty = current_content != self._original_content
        if was_dirty != self._is_dirty:
            self.content_changed.emit()

    def line_number_area_width(self):
        digits = 1
        count = max(1, self.blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
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
                painter.drawText(0, int(top), self.line_number_area.width() - 5, height, Qt.AlignmentFlag.AlignRight,
                                 number)
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(self.current_line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)