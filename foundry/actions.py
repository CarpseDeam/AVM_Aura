# foundry/actions.py

"""
This module provides concrete implementations of file system operations
and AST manipulation actions.
"""

import ast
import logging
import os
from pathlib import Path
from typing import List, Union

logger = logging.getLogger(__name__)


def write_file(path: str, content: str) -> str:
    """Writes content to a specified file, creating directories if necessary."""
    try:
        logger.info(f"Attempting to write to file: {path}")
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = path_obj.write_text(content, encoding='utf-8')
        success_message = f"Successfully wrote {bytes_written} bytes to {path}"
        logger.info(success_message)
        return success_message
    except Exception as e:
        error_message = f"An unexpected error occurred while writing to file {path}: {e}"
        logger.exception(error_message)
        return error_message


def read_file(path: str) -> str:
    """Reads the content of a specified file."""
    try:
        logger.info(f"Attempting to read file: {path}")
        path_obj = Path(path)
        if not path_obj.exists():
            return f"Error: File not found at path '{path}'"
        if not path_obj.is_file():
            return f"Error: Path '{path}' is a directory, not a file."
        content = path_obj.read_text(encoding='utf-8')
        logger.info(f"Successfully read {len(content)} characters from {path}")
        return content
    except Exception as e:
        error_message = f"An unexpected error occurred while reading file {path}: {e}"
        logger.exception(error_message)
        return error_message


def list_files(path: str) -> str:
    """Lists files and directories at a given path."""
    try:
        if not path:
            path = "."

        logger.info(f"Listing contents of directory: {path}")
        path_obj = Path(path)

        if not path_obj.exists():
            return f"Error: Directory not found at path '{path}'"
        if not path_obj.is_dir():
            return f"Error: Path '{path}' is a file, not a directory."

        entries: List[str] = []
        for entry in sorted(os.listdir(path)):
            if os.path.isdir(os.path.join(path, entry)):
                entries.append(f"{entry}/")
            else:
                entries.append(entry)

        if not entries:
            return f"Directory '{path}' is empty."

        result = f"Contents of '{path}':\n" + "\n".join(entries)
        logger.info(f"Successfully listed {len(entries)} items in {path}")
        return result
    except Exception as e:
        error_message = f"An unexpected error occurred while listing directory {path}: {e}"
        logger.exception(error_message)
        return error_message


def assign_variable(variable_name: str, value: str) -> ast.Assign:
    """
    Creates an AST node for a variable assignment.

    This function attempts to parse the `value` as a Python literal (e.g.,
    number, string, boolean). If it fails, it treats the value as a
    variable name (identifier), allowing for assignments like `x = y`.

    Args:
        variable_name: The name of the variable to assign to.
        value: The value to assign. This can be a literal (e.g., "123",
               "'hello'", "True") or an identifier (e.g., "other_var").

    Returns:
        An ast.Assign node representing the variable assignment.
    """
    logger.info(f"Creating AST for: {variable_name} = {value}")

    target = ast.Name(id=variable_name, ctx=ast.Store())

    value_node: Union[ast.Constant, ast.Name]
    try:
        evaluated_value = ast.literal_eval(value)
        value_node = ast.Constant(value=evaluated_value)
        logger.debug(f"Treated assignment value '{value}' as a literal.")
    except (ValueError, SyntaxError):
        value_node = ast.Name(id=value, ctx=ast.Load())
        logger.debug(f"Treated assignment value '{value}' as an identifier.")

    assignment = ast.Assign(targets=[target], value=value_node)

    # --- THIS IS THE FIX ---
    # Add the missing line number and column offset attributes that
    # ast.unparse() requires to function correctly.
    ast.fix_missing_locations(assignment)
    # --- END FIX ---

    return assignment


def define_function(name: str, args: str) -> ast.FunctionDef:
    """
    Creates an AST node for a function definition with an empty body.

    The function body is initialized with a single `pass` statement.
    Arguments are provided as a single comma-separated string.

    Args:
        name: The name of the function.
        args: A comma-separated string of argument names (e.g., "x, y, z").

    Returns:
        An ast.FunctionDef node representing the function definition.
    """
    logger.info(f"Creating AST for function definition: def {name}({args}): ...")

    # Parse argument string into a list of ast.arg nodes
    arg_names = [arg.strip() for arg in args.split(',') if arg.strip()]
    arguments = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=name) for name in arg_names],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[]
    )

    # Create a body with a single 'pass' statement
    body = [ast.Pass()]

    # Create the function definition node
    func_def = ast.FunctionDef(
        name=name,
        args=arguments,
        body=body,
        decorator_list=[],
        returns=None
    )

    ast.fix_missing_locations(func_def)
    return func_def


def function_call(function_name: str, args: str) -> ast.Expr:
    """
    Creates an AST node for a function call statement.

    Arguments are provided as a single comma-separated string. Each argument
    is parsed as a literal (e.g., "123", "'hello'") or treated as a
    variable name if literal parsing fails.

    Args:
        function_name: The name of the function to call.
        args: A comma-separated string of arguments.

    Returns:
        An ast.Expr node containing an ast.Call node.
    """
    logger.info(f"Creating AST for function call: {function_name}({args})")

    # Create the function name node
    func_node = ast.Name(id=function_name, ctx=ast.Load())

    # Parse arguments
    arg_nodes = []
    if args:
        arg_values = [arg.strip() for arg in args.split(',')]
        for value in arg_values:
            try:
                evaluated_value = ast.literal_eval(value)
                arg_nodes.append(ast.Constant(value=evaluated_value))
            except (ValueError, SyntaxError):
                arg_nodes.append(ast.Name(id=value, ctx=ast.Load()))

    # Create the call node
    call_node = ast.Call(
        func=func_node,
        args=arg_nodes,
        keywords=[]
    )

    # Wrap in an expression to make it a statement
    expr_statement = ast.Expr(value=call_node)

    ast.fix_missing_locations(expr_statement)
    return expr_statement


def return_statement(value: str) -> ast.Return:
    """
    Creates an AST node for a return statement.

    If the value is an empty string, a bare `return` is created.
    Otherwise, the value is parsed as a literal (e.g., "123", "'hello'")
    or treated as a variable name if literal parsing fails.

    Args:
        value: The value to return, or an empty string for a bare return.

    Returns:
        An ast.Return node.
    """
    logger.info(f"Creating AST for return statement: return {value or ''}")

    value_node = None
    if value:
        try:
            evaluated_value = ast.literal_eval(value)
            value_node = ast.Constant(value=evaluated_value)
            logger.debug(f"Treated return value '{value}' as a literal.")
        except (ValueError, SyntaxError):
            value_node = ast.Name(id=value, ctx=ast.Load())
            logger.debug(f"Treated return value '{value}' as an identifier.")

    return_node = ast.Return(value=value_node)

    ast.fix_missing_locations(return_node)
    return return_node


def get_generated_code(code_ast: ast.Module) -> str:
    """
    Unparses a complete AST module into a Python code string.

    Args:
        code_ast: The ast.Module object to unparse.

    Returns:
        A string containing the formatted Python code.
    """
    logger.info("Unparsing the current AST to generate code string.")
    try:
        # --- ADDED A SAFETY FIX HERE TOO ---
        # As a best practice, fix any missing locations on the entire tree
        # before attempting to unparse it.
        ast.fix_missing_locations(code_ast)
        # --- END FIX ---

        generated_code = ast.unparse(code_ast)
        logger.info("Successfully unparsed AST to code.")
        return generated_code
    except Exception as e:
        error_message = f"An unexpected error occurred while unparsing the AST: {e}"
        logger.exception(error_message)
        return error_message