# foundry/actions.py

"""
This module provides concrete implementations of file system operations
and AST manipulation actions. These are the actual Python functions that get
executed when a blueprint is invoked.
"""

import ast
import logging
import os
from pathlib import Path
from typing import List, Union, Any

logger = logging.getLogger(__name__)


# --- File System Actions ---

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

def list_files(path: str = ".") -> str:
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

        entries: List[str] = [f"{entry.name}/" if entry.is_dir() else entry.name for entry in sorted(path_obj.iterdir())]

        if not entries:
            return f"Directory '{path}' is empty."

        result = f"Contents of '{path}':\n" + "\n".join(entries)
        logger.info(f"Successfully listed {len(entries)} items in {path}")
        return result
    except Exception as e:
        error_message = f"An unexpected error occurred while listing directory {path}: {e}"
        logger.exception(error_message)
        return error_message


# --- AST Manipulation Actions ---

def assign_variable(variable_name: str, value: str) -> ast.Assign:
    """Creates an AST node for a variable assignment."""
    logger.info(f"Creating AST for: {variable_name} = {value}")
    target = ast.Name(id=variable_name, ctx=ast.Store())
    try:
        evaluated_value = ast.literal_eval(value)
        value_node = ast.Constant(value=evaluated_value)
    except (ValueError, SyntaxError):
        value_node = ast.Name(id=value, ctx=ast.Load())
    assignment = ast.Assign(targets=[target], value=value_node)
    ast.fix_missing_locations(assignment)
    return assignment

def define_function(name: str, args: List[str] = []) -> ast.FunctionDef:
    """Creates an AST node for a function definition."""
    logger.info(f"Creating AST for function: def {name}({', '.join(args)}): pass")
    
    arguments = ast.arguments(
        args=[ast.arg(arg=name) for name in args],
        posonlyargs=[], kwonlyargs=[], kw_defaults=[], defaults=[]
    )
    
    body = [ast.Pass()]
    
    func_def = ast.FunctionDef(
        name=name, args=arguments, body=body, decorator_list=[]
    )
    
    ast.fix_missing_locations(func_def)
    return func_def

def function_call(func_name: str, args: List[Any] = []) -> ast.Expr:
    """Creates an AST node for a function call."""
    logger.info(f"Creating AST for function call: {func_name}({', '.join(map(str, args))})")

    arg_nodes = []
    for arg in args:
        try:
            val = ast.literal_eval(arg)
            arg_nodes.append(ast.Constant(value=val))
        except (ValueError, SyntaxError):
            arg_nodes.append(ast.Name(id=str(arg), ctx=ast.Load()))

    call_node = ast.Call(
        func=ast.Name(id=func_name, ctx=ast.Load()),
        args=arg_nodes,
        keywords=[]
    )
    
    expr = ast.Expr(value=call_node)
    ast.fix_missing_locations(expr)
    return expr

def return_statement(value: str) -> ast.Return:
    """Creates an AST node for a return statement."""
    logger.info(f"Creating AST for: return {value}")
    
    try:
        val = ast.literal_eval(value)
        value_node = ast.Constant(value=val)
    except (ValueError, SyntaxError):
        value_node = ast.Name(id=value, ctx=ast.Load())
        
    return_node = ast.Return(value=value_node)
    ast.fix_missing_locations(return_node)
    return return_node

def get_generated_code(code_ast: ast.Module) -> str:
    """Unparses a complete AST module into a Python code string."""
    logger.info("Unparsing the current AST to generate code string.")
    try:
        ast.fix_missing_locations(code_ast)
        return ast.unparse(code_ast)
    except Exception as e:
        return f"An unexpected error occurred while unparsing the AST: {e}"