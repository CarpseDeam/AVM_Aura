# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from PySide6.QtCore import Qt, QPoint


class AIMessageWidget(QFrame):
    """
    A custom widget for displaying messages from Aura, styled to look like
    a retro terminal transmission box. It handles its own painting to resize correctly.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("AIMessageWidget")

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5)

        self.author_label = QLabel("[ Aura ]")
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

        painter.drawLine(rect.left(), top_line_y, gap_start_x, top_line_y)
        painter.drawLine(gap_end_x, top_line_y, rect.right(), top_line_y)
        painter.drawLine(rect.left(), top_line_y, rect.left(), rect.bottom())
        painter.drawLine(rect.right(), top_line_y, rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        painter.drawText(QPoint(rect.left() - 1, top_line_y + char_h_offset), "┌")
        painter.drawText(QPoint(rect.right() - 2, top_line_y + char_h_offset), "┐")
        painter.drawText(QPoint(rect.left() - 1, rect.bottom() + char_h_offset), "└")
        painter.drawText(QPoint(rect.right() - 2, rect.bottom() + char_h_offset), "┘")

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