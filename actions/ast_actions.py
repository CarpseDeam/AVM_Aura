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