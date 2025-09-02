# gui/widgets/thinking_scanner_widget.py
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer, Qt, QRect
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen


class ThinkingScannerWidget(QWidget):
    """
    A KITT-style scanning widget with an animated amber bar that sweeps back and forth.
    Shows during backend processing to indicate thinking/working state.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)  # Thin scanner bar
        self.setStyleSheet("background-color: #000000;")  # Match main window background
        
        # Animation state
        self.position = 0.0  # Position along the widget (0.0 to 1.0)
        self.direction = 1   # 1 for right, -1 for left
        self.animation_speed = 0.02  # How fast the scanner moves
        
        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_animation)
        self.timer.setInterval(16)  # ~60 FPS for smooth animation
        
        # Scanner properties
        self.scanner_width = 0.15  # Width of the scanning beam (as fraction of widget width)
        self.fade_edges = True     # Whether to fade the edges of the scanner
        
    def showEvent(self, event):
        """Start animation when widget becomes visible"""
        super().showEvent(event)
        self.start_scanning()
        
    def hideEvent(self, event):
        """Stop animation when widget is hidden"""
        super().hideEvent(event)
        self.stop_scanning()
        
    def start_scanning(self):
        """Start the scanning animation"""
        if not self.timer.isActive():
            self.timer.start()
            
    def stop_scanning(self):
        """Stop the scanning animation"""
        if self.timer.isActive():
            self.timer.stop()
            
    def _update_animation(self):
        """Update animation state and trigger repaint"""
        # Update position
        self.position += self.direction * self.animation_speed
        
        # Bounce at edges
        if self.position >= 1.0:
            self.position = 1.0
            self.direction = -1
        elif self.position <= 0.0:
            self.position = 0.0
            self.direction = 1
            
        # Trigger repaint
        self.update()
        
    def paintEvent(self, event):
        """Custom paint event to draw the KITT-style scanner"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get widget dimensions
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        if width <= 0 or height <= 0:
            return
            
        # Calculate scanner position and width
        scanner_pixel_width = int(width * self.scanner_width)
        center_x = int(self.position * (width - scanner_pixel_width))
        
        # Create the main amber scanner beam
        scanner_rect = QRect(center_x, 0, scanner_pixel_width, height)
        
        if self.fade_edges:
            # Create gradient for smooth fading effect
            gradient = QLinearGradient(center_x, 0, center_x + scanner_pixel_width, 0)
            gradient.setColorAt(0.0, QColor(255, 183, 77, 0))    # Transparent amber
            gradient.setColorAt(0.2, QColor(255, 183, 77, 100))  # Semi-transparent amber
            gradient.setColorAt(0.5, QColor(255, 183, 77, 255))  # Full amber
            gradient.setColorAt(0.8, QColor(255, 183, 77, 100))  # Semi-transparent amber  
            gradient.setColorAt(1.0, QColor(255, 183, 77, 0))    # Transparent amber
            
            painter.fillRect(scanner_rect, gradient)
        else:
            # Simple solid color scanner
            painter.fillRect(scanner_rect, QColor(255, 183, 77, 255))  # Solid amber
            
        # Add a subtle glow effect
        if self.fade_edges:
            glow_width = max(2, scanner_pixel_width // 4)
            glow_rect = QRect(center_x - glow_width, 0, 
                             scanner_pixel_width + (2 * glow_width), height)
            
            glow_gradient = QLinearGradient(glow_rect.left(), 0, glow_rect.right(), 0)
            glow_gradient.setColorAt(0.0, QColor(255, 183, 77, 0))   # Transparent
            glow_gradient.setColorAt(0.3, QColor(255, 183, 77, 30))  # Very faint amber
            glow_gradient.setColorAt(0.7, QColor(255, 183, 77, 30))  # Very faint amber
            glow_gradient.setColorAt(1.0, QColor(255, 183, 77, 0))   # Transparent
            
            painter.fillRect(glow_rect, glow_gradient)
            
        # Add subtle border lines for definition
        pen = QPen(QColor(255, 183, 77, 80), 1)  # Very subtle amber border
        painter.setPen(pen)
        painter.drawLine(0, 0, width, 0)  # Top border
        painter.drawLine(0, height - 1, width, height - 1)  # Bottom border
        
    def set_animation_speed(self, speed: float):
        """Set the animation speed (0.01 = slow, 0.05 = fast)"""
        self.animation_speed = max(0.001, min(0.1, speed))
        
    def set_scanner_width(self, width_fraction: float):
        """Set the scanner width as a fraction of the widget width (0.1 to 0.5)"""
        self.scanner_width = max(0.05, min(0.5, width_fraction))
        
    def set_fade_edges(self, fade: bool):
        """Enable or disable edge fading effect"""
        self.fade_edges = fade