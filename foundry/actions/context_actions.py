# foundry/actions/context_actions.py
"""
Contains actions related to managing and indexing project context.
"""
import logging
import ast
from pathlib import Path
from services.vector_context_service import VectorContextService

logger = logging.getLogger(__name__)


def index_project_context(vector_context_service: VectorContextService, path: str = ".") -> str:
    """
    Scans a directory for Python files, extracts functions and classes,
    and adds them to the vector database.

    Args:
        vector_context_service: The service for interacting with the vector DB.
        path: The root directory to scan.

    Returns:
        A summary of the indexing operation.
    """
    logger.info(f"Starting project indexing from path: {path}")
    root_path = Path(path)
    if not root_path.is_dir():
        return f"Error: The specified path '{path}' is not a valid directory."

    documents = []
    metadatas = []

    # Exclude common virtual environment and metadata folders
    exclude_dirs = {'venv', '.venv', '__pycache__', 'node_modules', '.git', 'chroma_db'}

    py_files = [p for p in root_path.rglob("*.py") if not any(excluded in p.parts for excluded in exclude_dirs)]

    for file_path in py_files:
        logger.debug(f"Processing file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)

            for node in tree.body:
                # We only care about top-level functions and classes for now
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    source_code = ast.unparse(node)
                    node_type = "function" if isinstance(node, ast.FunctionDef) else "class"

                    documents.append(source_code)
                    metadatas.append({
                        "file_path": str(file_path),
                        "node_type": node_type,
                        "node_name": node.name,
                    })

        except Exception as e:
            logger.warning(f"Could not parse or read file {file_path}: {e}")
            continue

    if not documents:
        return "No new functions or classes found to index in the specified path."

    vector_context_service.add_documents(documents, metadatas)

    return f"Successfully indexed {len(documents)} new code chunks (functions/classes) from {len(py_files)} Python files."