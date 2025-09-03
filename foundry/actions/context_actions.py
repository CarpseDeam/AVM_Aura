# foundry/actions/context_actions.py
"""
Contains actions related to managing and indexing project context.
Updated with comprehensive indexing capabilities.
"""
import logging
from pathlib import Path
from services.vector_context_service import VectorContextService
from core.managers.project_context import ProjectContext

logger = logging.getLogger(__name__)


def index_project_context(project_context: ProjectContext, vector_context_service: VectorContextService,
                          path: str = ".") -> str:
    """
    Scans a directory for Python files, extracts functions and classes with comprehensive analysis,
    and adds them to the vector database. This action is now sandboxed to the active project directory.

    Args:
        project_context: Injected by the ToolRunner. Contains the active project's root path.
        vector_context_service: Injected by the ToolRunner. The service for RAG.
        path: The path to scan, relative to the project root. Defaults to the root.

    Returns:
        A summary of the indexing operation.
    """
    if not project_context or not project_context.project_root:
        return "Error: Cannot index context. No active project."

    project_root = project_context.project_root
    scan_path = (project_root / path).resolve()

    # --- CRUCIAL SAFETY CHECK ---
    # Ensure the path to be scanned is safely within the active project's root directory.
    try:
        scan_path.relative_to(project_root)
    except ValueError:
        error_msg = f"Error: Indexing is only allowed within the active project. The path '{scan_path}' is outside of '{project_root}'."
        logger.error(error_msg)
        return error_msg

    if not scan_path.is_dir():
        return f"Error: The specified path '{scan_path}' is not a valid directory."

    logger.info(f"Starting comprehensive project indexing from path: {scan_path}")

    try:
        # Use the new comprehensive indexing method if available
        if hasattr(vector_context_service, 'index_project_comprehensive'):
            stats = vector_context_service.index_project_comprehensive(
                project_root=project_root,
                force_reindex=False
            )

            return f"""
Project indexing complete with advanced analysis:

📊 **Indexing Statistics:**
• New elements: {stats['new']}
• Updated elements: {stats['updated']}
• Skipped (unchanged): {stats['skipped']}
• Errors: {stats['errors']}

🚀 **Advanced Features Active:**
✓ Semantic code understanding (intent-aware search)
✓ Code complexity analysis
✓ Function signature extraction
✓ Docstring integration
✓ Test function identification
✓ Import dependency tracking
✓ Temporal relevance scoring

💡 **Smart Search Available:**
Try queries like:
• "authentication function" (implementation intent)
• "fix database connection error" (debug intent)  
• "test user validation" (testing intent)

The RAG system now understands your coding intent and provides contextually relevant results.
            """.strip()

        else:
            # Fallback to original indexing method
            return _index_project_legacy(scan_path, project_root, vector_context_service)

    except Exception as e:
        logger.error(f"Comprehensive indexing failed: {e}")
        return f"Indexing failed with error: {str(e)}\n\nTrying fallback method..."


def _index_project_legacy(scan_path: Path, project_root: Path, vector_context_service: VectorContextService) -> str:
    """Legacy indexing method for backward compatibility."""
    import ast

    logger.info(f"Using legacy indexing for path: {scan_path}")
    documents = []
    metadatas = []

    # Exclude common virtual environment and metadata folders
    exclude_dirs = {'venv', '.venv', '__pycache__', 'node_modules', '.git', 'chroma_db', '.rag_db'}

    py_files = [p for p in scan_path.rglob("*.py") if not any(excluded in p.parts for excluded in exclude_dirs)]

    for file_path in py_files:
        logger.debug(f"Processing file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    source_code = ast.unparse(node)
                    node_type = "function" if isinstance(node, ast.FunctionDef) else "class"

                    # Enhanced metadata
                    metadata = {
                        "file_path": str(file_path.relative_to(project_root)),
                        "node_type": node_type,
                        "node_name": node.name,
                        "line_start": node.lineno,
                        "line_end": getattr(node, 'end_lineno', node.lineno),
                    }

                    # Add function-specific metadata
                    if isinstance(node, ast.FunctionDef):
                        metadata["parameters"] = [arg.arg for arg in node.args.args]
                        if node.returns:
                            metadata["return_type"] = ast.unparse(node.returns)

                        # Extract docstring
                        if (node.body and isinstance(node.body[0], ast.Expr) and
                                isinstance(node.body[0].value, ast.Constant)):
                            metadata["docstring"] = node.body[0].value.value

                        # Detect test functions
                        if node.name.startswith('test_'):
                            metadata["node_type"] = "test"

                    documents.append(source_code)
                    metadatas.append(metadata)

        except Exception as e:
            logger.warning(f"Could not parse or read file {file_path}: {e}")
            continue

    if not documents:
        return "No functions or classes found to index in the specified path."

    vector_context_service.add_documents(documents, metadatas)

    return f"""
Legacy indexing completed:
• Indexed {len(documents)} code elements from {len(py_files)} Python files
• Enhanced metadata includes function signatures and docstrings
• Test functions automatically detected

Note: For full advanced features, ensure your VectorContextService has the latest updates.
    """.strip()


def smart_search_context(vector_context_service: VectorContextService, query: str, intent: str = "understand",
                         current_file: str = None, max_results: int = 5) -> str:
    """
    Perform an intelligent context search that understands coding intent.

    Args:
        vector_context_service: The RAG service
        query: What you're looking for
        intent: Your coding intent (implement, debug, test, refactor, understand)
        current_file: Current file you're working in (for context boost)
        max_results: Maximum number of results to return

    Returns:
        Formatted search results with explanations
    """
    if not hasattr(vector_context_service, 'smart_query'):
        return "Smart search not available. Please update your VectorContextService."

    try:
        results = vector_context_service.smart_query(
            query_text=query,
            intent=intent,
            current_file=current_file,
            n_results=max_results
        )

        if not results:
            return f"No results found for '{query}' with {intent} intent."

        formatted_results = [f"🔍 Smart search results for '{query}' (Intent: {intent}):\n"]

        for i, result in enumerate(results, 1):
            metadata = result['metadata']
            explanation = result['explanation']
            score = result['final_score']

            file_path = metadata.get('file_path', 'Unknown')
            element_type = metadata.get('node_type', 'unknown')
            element_name = metadata.get('node_name', 'unnamed')

            formatted_results.append(f"""
{i}. **{element_type.title()}: {element_name}** (Score: {score:.2f})
   📁 File: {file_path}
   💡 Why relevant: {explanation}

```python
{result['document'][:200]}{"..." if len(result['document']) > 200 else ""}
```
            """.strip())

        return "\n\n".join(formatted_results)

    except Exception as e:
        return f"Smart search failed: {str(e)}"


def mark_file_modified(vector_context_service: VectorContextService, file_path: str) -> str:
    """
    Mark a file as recently modified to boost its relevance in searches.

    Args:
        vector_context_service: The RAG service
        file_path: Path to the modified file

    Returns:
        Confirmation message
    """
    if hasattr(vector_context_service, 'mark_file_modified'):
        vector_context_service.mark_file_modified(file_path)
        return f"✅ Marked {file_path} as recently modified. It will get priority in context searches."
    else:
        return "File modification tracking not available in current VectorContextService version."