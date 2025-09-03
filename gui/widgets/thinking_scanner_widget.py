# gui/widgets/thinking_scanner_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor, QPainter, QBrush

class ThinkingScannerWidget(QWidget):
    """
    A Knight Rider-style scanner to indicate that a background process is running.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)  # Slim profile
        self.setMinimumWidth(200)
        
        self.scanner_position = 0
        self.direction = 1  # 1 for right, -1 for left

        # Animation for the scanner bar
        self.animation = QPropertyAnimation(self, b"scanner_position_prop")
        self.animation.setDuration(1200)  # Slower, more deliberate scan
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setLoopCount(-1)  # Loop indefinitely
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.start()

    def paintEvent(self, event):
        """Overrides the paint event to draw the scanner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        
        # Scanner gradient
        bar_width = self.width() * 0.25  # The glowing bar is 25% of the widget width
        center_x = self.width() * self.scanner_position
        
        for i in range(int(bar_width)):
            ratio = i / bar_width
            alpha = 255 * (1.0 - ratio**2)  # Fade out from the center
            
            # Draw on both sides of the center
            painter.setPen(QColor(255, 183, 77, alpha)) # Amber color
            painter.drawPoint(int(center_x + i), self.height() // 2)
            painter.drawPoint(int(center_x - i), self.height() // 2)

    def get_scanner_position(self):
        return self.scanner_position

    def set_scanner_position(self, position):
        """Slot for the QPropertyAnimation to update."""
        self.scanner_position = position
        self.update()  # Trigger a repaint

    # Define a QProperty for the animation to target
    scanner_position_prop = Property(float, get_scanner_position, set_scanner_position)
