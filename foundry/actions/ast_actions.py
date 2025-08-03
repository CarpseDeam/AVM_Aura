# foundry/actions/ast_actions.py
"""
Contains actions related to creating and manipulating Python AST nodes.
"""
import ast
import logging
from typing import List, Any

logger = logging.getLogger(__name__)


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
        # We only look at the direct children of the module body for top-level functions
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
    Parses a Python file and returns the full source code for a specific function.

    Args:
        path: The path to the Python file.
        function_name: The name of the function to retrieve.

    Returns:
        A formatted string with the function's source code, or an error message.
    """
    logger.info(f"Attempting to get source for function '{function_name}' in file: {path}")
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
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                source_code = ast.unparse(node)
                logger.info(f"Successfully extracted source code for '{function_name}'.")
                return f"Source code for '{function_name}' from '{path}':\n```python\n{source_code}\n```"

        # If the loop finishes and we haven't found the function
        not_found_msg = f"Error: Function '{function_name}' not found as a top-level function in '{path}'."
        logger.warning(not_found_msg)
        return not_found_msg

    except SyntaxError as e:
        return f"Error: The file at '{path}' contains a syntax error and could not be parsed. Line {e.lineno}, Column {e.offset}: {e.msg}"
    except Exception as e:
        return f"An unexpected error occurred while parsing file '{path}': {e}"


def define_class(name: str, bases: List[str] = []) -> ast.ClassDef:
    """
    Creates an AST node for a class definition.

    Args:
        name: The name of the class.
        bases: A list of strings representing the names of base classes.

    Returns:
        An ast.ClassDef node representing the new class.
    """
    logger.info(f"Creating AST for class: class {name}({', '.join(bases) if bases else ''}): pass")

    # Convert base class names (strings) into AST nodes
    base_nodes = [ast.Name(id=base, ctx=ast.Load()) for base in bases]

    # Create an empty body with a 'pass' statement
    body = [ast.Pass()]

    # Create the ClassDef node
    class_def = ast.ClassDef(
        name=name,
        bases=base_nodes,
        keywords=[],
        body=body,
        decorator_list=[]
    )

    ast.fix_missing_locations(class_def)
    return class_def