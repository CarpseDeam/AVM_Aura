# gui/syntax_highlighter.py
import logging
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.style import Style
from pygments.styles import get_style_by_name
from pygments.token import Token, Comment, String, Number, Keyword, Operator, Name, Text

logger = logging.getLogger(__name__)


class SyntaxHighlighter:
    """
    A service that uses Pygments to generate styled tokens for syntax highlighting.
    """

    def __init__(self, style_name: str = 'monokai'):
        self.style_name = style_name
        try:
            self.style: Style = get_style_by_name(self.style_name)
        except Exception:
            logger.warning(f"Pygments style '{style_name}' not found. Falling back to 'default'.")
            self.style: Style = get_style_by_name('default')

        # Create a mapping from Pygments Token types to our simple tag names
        self.token_map = {
            Token: "token_text",
            Comment: "token_comment",
            String: "token_string",
            Number: "token_number",
            Keyword: "token_keyword",
            Operator: "token_operator",
            Name.Function: "token_function",
            Name.Class: "token_class",
            Name.Namespace: "token_keyword",  # Treat 'import' and 'from' as keywords
        }

    def get_style_for_tag(self, tag_name: str) -> dict:
        """Gets the hex color for a simplified tag name from the Pygments style."""
        # This is a simplified mapping; a real-world app might be more complex.
        # We find the Pygments Token that corresponds to our tag.
        token_type = Text
        if tag_name == "token_comment":
            token_type = Comment
        elif tag_name == "token_string":
            token_type = String
        elif tag_name == "token_number":
            token_type = Number
        elif tag_name == "token_keyword":
            token_type = Keyword
        elif tag_name == "token_operator":
            token_type = Operator
        elif tag_name == "token_function":
            token_type = Name.Function
        elif tag_name == "token_class":
            token_type = Name.Class

        style_for_token = self.style.style_for_token(token_type)
        color = style_for_token.get('color')
        if color:
            return {'foreground': f'#{color}'}
        return {}  # Return empty dict if no color is defined

    def get_tokens(self, code: str):
        """
        Lexes the given code and yields tuples of (text, tag_name).
        """
        python_lexer = PythonLexer()
        tokens = lex(code, python_lexer)

        for token_type, text in tokens:
            # Find the most specific tag for the token type
            tag = "token_text"  # Default
            for t_type, t_name in self.token_map.items():
                if token_type in t_type:
                    tag = t_name
            yield text, tag