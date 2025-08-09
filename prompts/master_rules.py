JSON_OUTPUT_RULE = """
**LAW: STRICT JSON OUTPUT**
- Your entire response MUST be a single, valid JSON object.
- Do not add any conversational text, explanations, or markdown before or after the JSON object.
- Your response must begin with `{` and end with `}`.
"""

RAW_CODE_OUTPUT_RULE = """
**LAW: RAW CODE OUTPUT ONLY**
- Your entire response MUST be only the raw Python code for the assigned file.
- Do not write any explanations, comments, or markdown before or after the code.
"""

TYPE_HINTING_RULE = """
**LAW: MANDATORY TYPE HINTING**
- All function and method signatures MUST include type hints for all arguments and for the return value.
- Use the `typing` module where necessary (e.g., `List`, `Dict`, `Optional`).
- Example of a correct signature: `def my_function(name: str, count: int) -> bool:`
"""

DOCSTRING_RULE = """
**LAW: COMPREHENSIVE DOCSTRINGS**
- Every module, class, and public function MUST have a comprehensive Google-style docstring.
- Docstrings must describe the purpose, arguments (`Args:`), and return value (`Returns:`).
"""