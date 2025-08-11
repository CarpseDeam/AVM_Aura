# gui/chat_widgets/ai_message_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QTextDocument, QTextOption
from PySide6.QtCore import Qt, QPoint, QSize


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
        self.text = text

        # This size policy is crucial for heightForWidth to work correctly
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(5)

        self.author_label = QLabel(f"[ {self.author} ]")
        self.author_label.setObjectName("AuraAuthorLabel")
        self.author_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.author_label.adjustSize()

        # This invisible label helps the layout manager understand there's content
        self.message_label = QLabel()
        self.message_label.setObjectName("AIMessageLabel")
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)  # We do our own drawing

        layout.addWidget(self.author_label, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.message_label)

        self._apply_stylesheet()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculates the required height based on the text and a given width."""
        margins = self.layout().contentsMargins()
        # The available width for text is the widget's width minus horizontal margins.
        text_width = width - margins.left() - margins.right()

        # Use a QTextDocument to accurately measure wrapped text height
        doc = QTextDocument()
        doc.setDefaultFont(self.message_label.font())  # Use the label's font for consistency
        doc.setPlainText(self.text)
        doc.setTextWidth(text_width)

        text_height = doc.size().height()
        author_height = self.author_label.sizeHint().height()

        # Total height is the sum of all components and layout spacing
        return int(text_height + author_height + margins.top() + margins.bottom() + self.layout().spacing())

    def paintEvent(self, event):
        """Custom painting to draw the box and the wrapped text."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # We need to call the superclass paintEvent to allow the child author_label to draw itself.
        super().paintEvent(event)

        border_color = QColor("#FFB74D")
        text_color = QColor("#d4d4d4")

        # Set up a pen for drawing borders
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)

        rect = self.rect().adjusted(1, 1, -1, -1)
        author_geom = self.author_label.geometry()

        # The top line of our box should align with the center of the author label
        top_line_y = author_geom.center().y()

        # --- Draw the Box ---
        # Draw left part of top line
        painter.drawLine(rect.left(), top_line_y, author_geom.left() - 5, top_line_y)
        # Draw right part of top line
        painter.drawLine(author_geom.right() + 5, top_line_y, rect.right(), top_line_y)
        # Draw vertical and bottom lines
        painter.drawLine(rect.left(), top_line_y, rect.left(), rect.bottom())
        painter.drawLine(rect.right(), top_line_y, rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        # --- Custom Text Drawing with Wrapping ---
        painter.setPen(text_color)

        # Define the rectangle where the text will be drawn.
        text_rect = self.rect().adjusted(
            self.layout().contentsMargins().left(),
            author_geom.bottom() + self.layout().spacing(),  # Start below the author label
            -self.layout().contentsMargins().right(),
            -self.layout().contentsMargins().bottom()
        )

        # Use QTextDocument for robust word wrapping
        doc = QTextDocument()
        doc.setDefaultFont(self.message_label.font())
        doc.setPlainText(self.text)
        option = QTextOption(Qt.AlignmentFlag.AlignLeft)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        doc.setDefaultTextOption(option)
        doc.setTextWidth(text_rect.width())

        # Translate the painter to the top-left of our text area and draw
        painter.save()
        painter.translate(text_rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #AIMessageWidget {
                background-color: #0d0d0d;
                border: none;
            }
            #AuraAuthorLabel {
                color: #FFB74D;
                font-weight: bold;
                background-color: #0d0d0d;
                padding: 0 5px;
            }
        """)