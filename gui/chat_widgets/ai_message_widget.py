# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PySide6.QtCore import Qt, QPoint


class AIMessageWidget(QFrame):
    """
    A custom widget for displaying messages from Aura, styled to look like
    a retro terminal transmission box. It handles its own painting to resize correctly.
    """

    def __init__(self, text: str, author: str = "Aura", parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("AIMessageWidget")
        self.author = author.upper()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5)

        self.author_label = QLabel(f"[ {self.author} ]")
        self.author_label.setObjectName("AuraAuthorLabel")
        self.author_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.author_label.adjustSize()

        self.message_label = QLabel(text)
        self.message_label.setObjectName("AIMessageLabel")
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(self.author_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.message_label)

        self._apply_stylesheet()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Style Definitions for each Agent ---
        STYLES = {
            "ARCHITECT": {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"},
            "CODER": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│", "flair": "<>"},
            "TESTER": {"tl": "[", "tr": "]", "bl": "[", "br": "]", "h": "-", "v": "¦"},
            "FINALIZER": {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"},
            "CONDUCTOR": {"tl": "╓", "tr": "╖", "bl": "╙", "br": "╜", "h": "─", "v": "║"},
            "REVIEWER": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "·", "v": "│"},
            "AURA": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"},
            "DEFAULT": {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"},
        }

        style = STYLES.get(self.author, STYLES["DEFAULT"])

        label_geom = self.author_label.geometry()
        if label_geom.width() == 0 or not self.author_label.isVisible():
            painter.fillRect(self.rect(), QColor("#0d0d0d"))
            super().paintEvent(event)
            return

        border_color = QColor("#FFB74D")
        bg_color = QColor("#0d0d0d")

        painter.fillRect(self.rect(), bg_color)

        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)

        font = self.font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        char_h_offset = fm.ascent() / 2 - 2

        rect = self.rect().adjusted(2, 2, -2, -2)
        top_line_y = label_geom.center().y()
        gap_start_x = label_geom.x() - 5
        gap_end_x = label_geom.right() + 5

        # Draw box using styled characters
        # Top line
        painter.drawText(0, top_line_y, gap_start_x, fm.height(), Qt.AlignmentFlag.AlignRight, style['h'] * 50)
        painter.drawText(gap_end_x, top_line_y, rect.width(), fm.height(), Qt.AlignmentFlag.AlignLeft, style['h'] * 50)

        # Side and bottom lines
        for y in range(top_line_y, rect.bottom(), fm.height()):
            painter.drawText(rect.left() - 1, y + fm.height(), style['v'])
            painter.drawText(rect.right() - 2, y + fm.height(), style['v'])
        painter.drawText(0, rect.bottom(), rect.width(), fm.height(), Qt.AlignmentFlag.AlignHCenter, style['h'] * 100)

        # Draw corners
        painter.drawText(QPoint(rect.left() - 1, top_line_y + char_h_offset), style['tl'])
        painter.drawText(QPoint(rect.right() - 2, top_line_y + char_h_offset), style['tr'])
        painter.drawText(QPoint(rect.left() - 1, rect.bottom() + char_h_offset), style['bl'])
        painter.drawText(QPoint(rect.right() - 2, rect.bottom() + char_h_offset), style['br'])

        # Draw special flair if it exists
        if "flair" in style:
            painter.drawText(QPoint(gap_start_x - fm.horizontalAdvance(style["flair"][0]), top_line_y + char_h_offset),
                             style["flair"][0])
            painter.drawText(QPoint(gap_end_x, top_line_y + char_h_offset), style["flair"][1])

        super().paintEvent(event)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #AIMessageWidget {
                background-color: transparent;
                border: none;
            }
            #AuraAuthorLabel {
                color: #FFB74D;
                font-weight: bold;
                background-color: #0d0d0d;
                padding: 0 5px;
            }
            #AIMessageLabel {
                color: #d4d4d4;
            }
        """)