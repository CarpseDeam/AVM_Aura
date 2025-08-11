# gui/chat_widgets/agent_activity_widget.py
from PySide6.QtWidgets import QFrame, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QTextDocument, QTextOption, QFontMetrics


class AgentActivityWidget(QFrame):
    """
    A versatile, fully responsive widget to display agent activity.
    It custom-paints its content to ensure it never causes horizontal overflow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentActivityWidget")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.activity_text = "Initializing..."
        self.agent_name = "AURA"
        self.logo = "O"

        self.animation_step = 0
        self.is_pulsing = False
        self.text_content = ""

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)

        self.main_font = QFont("Courier New", 14)
        self.fm = QFontMetrics(self.main_font)

        # Start with a reasonable minimum height
        self.setMinimumHeight(self.fm.height() * 4)

    def start_pulsing(self, text: str):
        """Starts the generic 'thinking' animation."""
        self.is_pulsing = True
        self.text_content = text
        if not self.timer.isActive():
            self.timer.start(100)
        self.update()

    def set_agent_status(self, logo: str, agent_name: str, activity: str):
        """Stops pulsing and sets the static agent status."""
        self.is_pulsing = False
        if self.timer.isActive():
            self.timer.stop()

        self.logo = logo
        self.agent_name = agent_name
        self.activity_text = activity
        self.update()

    def update_animation(self):
        """Drives the animation for the pulsing state."""
        if not self.is_pulsing:
            return
        self.animation_step += 1
        self.update()

    def stop_animation(self):
        self.timer.stop()
        self.is_pulsing = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.main_font)

        bg_color = QColor("#0d0d0d")
        border_color = QColor("#FFB74D")
        painter.fillRect(self.rect(), bg_color)

        # Define the main content rectangle with padding
        rect = self.rect().adjusted(10, 5, -10, -5)

        if self.is_pulsing:
            self._paint_pulsing_box(painter, rect, border_color)
        else:
            self._paint_static_box(painter, rect, border_color)

    def _paint_pulsing_box(self, painter: QPainter, rect, color: QColor):
        """Paints the animated, pulsing box."""
        # Simple two-frame animation
        is_faded = (self.animation_step % 2) == 0
        pulse_color = color.lighter(120) if is_faded else color
        painter.setPen(pulse_color)

        char_width = self.fm.horizontalAdvance(' ')
        if char_width == 0: return

        # Draw corners
        painter.drawText(rect.topLeft(), "+")
        painter.drawText(rect.topRight() - QPoint(char_width, 0), "+")
        painter.drawText(rect.bottomLeft() - QPoint(0, self.fm.height() - self.fm.ascent()), "+")
        painter.drawText(rect.bottomRight() - QPoint(char_width, self.fm.height() - self.fm.ascent()), "+")

        # Draw lines
        painter.drawLine(rect.left() + char_width, rect.top(), rect.right() - char_width, rect.top())
        painter.drawLine(rect.left() + char_width, rect.bottom(), rect.right() - char_width, rect.bottom())
        painter.drawLine(rect.left(), rect.top() + self.fm.height(), rect.left(), rect.bottom() - self.fm.height())
        painter.drawLine(rect.right(), rect.top() + self.fm.height(), rect.right(), rect.bottom() - self.fm.height())

        # Draw wrapped text inside
        text_rect = rect.adjusted(char_width * 2, self.fm.height(), -char_width * 2, -self.fm.height())
        self._draw_wrapped_text(painter, self.text_content, text_rect, Qt.AlignmentFlag.AlignCenter)

    def _paint_static_box(self, painter: QPainter, rect, color: QColor):
        """Paints the final, static status box."""
        painter.setPen(color)

        header_text = f" {self.logo} — [ {self.agent_name} ] "
        header_width = self.fm.horizontalAdvance(header_text)
        header_start_x = rect.center().x() - header_width // 2
        header_end_x = header_start_x + header_width

        top_line_y = rect.y() + self.fm.ascent() // 2

        # Draw the top border around the header
        painter.drawLine(rect.left(), top_line_y, header_start_x, top_line_y)
        painter.drawLine(header_end_x, top_line_y, rect.right(), top_line_y)

        # Draw the rest of the box
        painter.drawLine(rect.left(), top_line_y, rect.left(), rect.bottom())
        painter.drawLine(rect.right(), top_line_y, rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        # Draw the header text on top of the border line (effectively erasing it)
        painter.fillRect(header_start_x, top_line_y - 1, header_width, 3, QColor("#0d0d0d"))
        painter.drawText(QPoint(header_start_x, rect.y() + self.fm.ascent()), header_text)

        # Draw the main activity text, wrapped
        activity_rect = rect.adjusted(5, self.fm.height() * 1.5, -5, -5)
        self._draw_wrapped_text(painter, self.activity_text.upper(), activity_rect,
                                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    def _draw_wrapped_text(self, painter: QPainter, text: str, rect, alignment: Qt.AlignmentFlag):
        """Helper to draw wrapped text using QTextDocument."""
        doc = QTextDocument()
        doc.setDefaultFont(self.main_font)

        # Set alignment on the option, not the document directly
        option = QTextOption(alignment)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        doc.setDefaultTextOption(option)

        # Set the text and width
        doc.setPlainText(text)
        doc.setTextWidth(rect.width())

        # Save painter state, translate to the drawing position, and draw
        painter.save()
        painter.translate(rect.topLeft())
        doc.drawContents(painter)
        painter.restore()