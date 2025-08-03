# foundry/actions/ast_modification_actions.py
"""
Contains actions that read, parse, modify, and write Python files using AST.
These tools are for inspecting and surgically altering existing code on disk.
"""
import ast
import logging
from typing import List

logger = logging.getLogger(__name__)


def get_generated_code(code_ast: ast.Module) -> str:
    """Unparses a complete AST module into a Python code string."""
    logger.info("Unparsing the current AST to generate code string.")
    try:
        ast.fix_missing_locations(code_ast)
        # --- FIX --- Ensure this tool also returns a markdown block
        return f"Generated Code:\n```python\n{ast.unparse(code_ast)}\n```"
    except Exception as e:
        return f"An unexpected error occurred while unparsing the AST: {e}"


def list_functions_in_file(path: str) -> str:
    """
    Parses a Python file and returns a list of its top-level function names.

    Args:
        path: The path to the Python file.

    Returns:
        A string listing the function names, or an error message.
    """
    logger.info(f"Attempting to list functions in file: {path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        error_msg = f"Error: File not found at '{path}'."
        logger.warning(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error reading file at '{path}': {e}"
        logger.exception(error_msg)
        return error_msg

    try:
        tree = ast.parse(content)
        function_names = [
            node.name for node in tree.body
            if isinstance(node, ast.FunctionDef)
        ]

        if not function_names:
            return f"No top-level functions found in '{path}'."

        result_str = f"Functions in '{path}':\n" + "\n".join(f"- {name}" for name in sorted(function_names))
        logger.info(f"Found functions in '{path}': {', '.join(function_names)}")
        return result_str

    except SyntaxError as e:
        error_msg = f"Error: The file at '{path}' contains a syntax error and could not be parsed. Line {e.lineno}, Column {e.offset}: {e.msg}"
        logger.warning(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred while parsing file '{path}': {e}"
        logger.exception(error_msg)
        return error_msg


def get_code_for(path: str, function_name: str) -> str:
    """
    Parses a Python file and returns the full source code for a specific function or class.

    Args:
        path: The path to the Python file.
        function_name: The name of the node to retrieve.

    Returns:
        A formatted string with the node's source code, or an error message.
    """
    logger.info(f"Attempting to get source for node '{function_name}' in file: {path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: File not found at '{path}'."
    except Exception as e:
        return f"Error reading file at '{path}': {e}"

    try:
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == function_name:
                source_code = ast.unparse(node)
                logger.info(f"Successfully extracted source code for '{function_name}'.")
                # --- FIX --- Wrap the output in a markdown code block
                return f"Source code for '{function_name}' from '{path}':\n```python\n{source_code}\n```"

        not_found_msg = f"Error: Node '{function_name}' not found as a top-level function or class in '{path}'."
        logger.warning(not_found_msg)
        return not_found_msg

    except SyntaxError as e:
        return f"Error: The file at '{path}' contains a syntax error and could not be parsed. Line {e.lineno}, Column {e.offset}: {e.msg}"
    except Exception as e:
        return f"An unexpected error occurred while parsing file '{path}': {e}"


def add_method_to_class(path: str, class_name: str, name: str, args: list) -> str:
    """
    Adds an empty method to a class in a given file.

    Args:
        path: The path to the Python file.
        class_name: The name of the class to modify.
        name: The name of the new method.
        args: The arguments for the new method.

    Returns:
        A string indicating success or failure.
    """
    logger.info(f"Attempting to add method '{name}' to class '{class_name}' in file '{path}'.")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: File not found at '{path}'."
    except Exception as e:
        return f"Error reading file at '{path}': {e}"

    try:
        tree = ast.parse(content)
        class_node = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                class_node = node
                break

        if not class_node:
            return f"Error: Class '{class_name}' not found in '{path}'."

        arguments = ast.arguments(
            args=[ast.arg(arg=arg_name) for arg_name in args],
            posonlyargs=[], kwonlyargs=[], kw_defaults=[], defaults=[]
        )
        method_body = [ast.Pass()]
        new_method = ast.FunctionDef(
            name=name, args=arguments, body=method_body, decorator_list=[]
        )

        if len(class_node.body) == 1 and isinstance(class_node.body[0], ast.Pass):
            class_node.body = []

        class_node.body.append(new_method)

        new_code = ast.unparse(tree)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_code)

        success_message = f"Successfully added method '{name}' to class '{class_name}' in '{path}'."
        logger.info(success_message)
        return success_message

    except SyntaxError as e:
        return f"Error: The file at '{path}' contains a syntax error and could not be parsed. Line {e.lineno}, Column {e.offset}: {e.msg}"
    except Exception as e:
        error_message = f"An unexpected error occurred while adding method: {e}"
        logger.exception(error_message)
        return error_message


def add_import(path: str, module: str, names: List[str] = []) -> str:
    """
    Adds an import statement to a Python file if it doesn't already exist.

    Args:
        path: The path to the Python file.
        module: The module to import (e.g., 'os').
        names: A list of specific names to import from the module (for 'from ... import ...').

    Returns:
        A string indicating success, that it already existed, or failure.
    """
    logger.info(f"Attempting to add import for '{module}' to file '{path}'.")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: File not found at '{path}'."
    except Exception as e:
        return f"Error reading file at '{path}': {e}"

    try:
        tree = ast.parse(content)

        # Check for existing imports to avoid duplicates
        for node in tree.body:
            if isinstance(node, ast.Import) and not names:
                if any(alias.name == module for alias in node.names):
                    return f"Import 'import {module}' already exists in '{path}'."
            elif isinstance(node, ast.ImportFrom) and names and node.module == module:
                existing_names = {alias.name for alias in node.names}
                if set(names).issubset(existing_names):
                    return f"Import 'from {module} import {', '.join(names)}' already satisfied in '{path}'."

        # Create the new import node
        if names:
            import_node = ast.ImportFrom(module=module, names=[ast.alias(name=n) for n in names], level=0)
            import_str = f"from {module} import {', '.join(names)}"
        else:
            import_node = ast.Import(names=[ast.alias(name=module)])
            import_str = f"import {module}"

        # Find the first non-docstring/import line to insert the new import
        insert_pos = 0
        for i, node in enumerate(tree.body):
            if not isinstance(node, (ast.Import, ast.ImportFrom)) and \
                    not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Str)):
                break
            insert_pos = i + 1

        tree.body.insert(insert_pos, import_node)

        new_code = ast.unparse(tree)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_code)

        success_message = f"Successfully added import '{import_str}' to '{path}'."
        logger.info(success_message)
        return success_message

    except SyntaxError as e:
        return f"Error: The file at '{path}' contains a syntax error and could not be parsed. Line {e.lineno}, Column {e.offset}: {e.msg}"
    except Exception as e:
        error_message = f"An unexpected error occurred while adding import: {e}"
        logger.exception(error_message)
        return error_message