# gui/syntax_highlighter.py
import logging
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.style import Style
from pygments.styles import get_style_by_name
from pygments.token import Token

logger = logging.getLogger(__name__)


class PygmentsFormatter:
    """
    A custom Pygments formatter that converts style information from a theme
    into Qt's QTextCharFormat for use with QSyntaxHighlighter.
    """

    def __init__(self, style_name: str = 'monokai'):
        super().__init__()
        self.styles: dict[Token, QTextCharFormat] = {}
        try:
            # Use a theme that looks good on a dark background. 'monokai' is a classic.
            style: Style = get_style_by_name(style_name)
        except Exception:
            logger.warning(f"Pygments style '{style_name}' not found. Falling back to 'default'.")
            style: Style = get_style_by_name('default')

        # Create a QTextCharFormat for each token type in the theme
        for token, style_def in style:
            char_format = QTextCharFormat()
            if style_def['color']:
                char_format.setForeground(QColor(f"#{style_def['color']}"))
            if style_def['bgcolor']:
                char_format.setBackground(QColor(f"#{style_def['bgcolor']}"))
            if style_def['bold']:
                char_format.setFontWeight(QFont.Weight.Bold)
            if style_def['italic']:
                char_format.setFontItalic(True)
            if style_def['underline']:
                char_format.setFontUnderline(True)
            self.styles[token] = char_format


class AuraSyntaxHighlighter(QSyntaxHighlighter):
    """
    A syntax highlighter that uses Pygments to colorize Python code.
    """

    def __init__(self, parent_document):
        super().__init__(parent_document)
        self.lexer = PythonLexer()
        self.formatter = PygmentsFormatter(style_name='monokai')

    def highlightBlock(self, text: str):
        """This virtual method is called by Qt for each block of text to highlight."""
        if not text:
            return

        # Use pygments to break the text into tokens
        tokens = self.lexer.get_tokens_unprocessed(text)

        # Apply the corresponding format for each token
        for index, token_type, token_text in tokens:
            if token_type in self.formatter.styles:
                self.setFormat(index, len(token_text), self.formatter.styles[token_type])