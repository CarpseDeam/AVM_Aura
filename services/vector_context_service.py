# services/vector_context_service.py
"""
Manages the vector database for project-wide context (RAG).
Production-ready system with advanced code understanding and context awareness.
"""
import logging
import ast
import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

import chromadb
from sentence_transformers import SentenceTransformer
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# Default model - will try CodeBERT at runtime
DEFAULT_EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
CODEBERT_MODEL = 'microsoft/codebert-base'


class CodeElementType(Enum):
    """Types of code elements that can be indexed."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    DOCSTRING = "docstring"
    TEST = "test"


@dataclass
class CodeContext:
    """Rich context information about a code element."""
    element_id: str
    element_type: CodeElementType
    name: str
    content: str
    file_path: str
    line_start: int
    line_end: int
    parent_class: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    complexity_score: float = 0.0
    modified_at: datetime = field(default_factory=datetime.now)
    calls_made: Set[str] = field(default_factory=set)


class VectorContextService:
    """
    Handles the creation, storage, and retrieval of vector embeddings for
    code snippets and other project context with advanced understanding.
    """

    def __init__(self, db_path: str):
        try:
            logger.info(f"Initializing VectorContextService with DB path: {db_path}")
            self.db_path = db_path

            # Load embedding model with proper error handling
            self.embedding_model = self._load_embedding_model()

            # Set up the ChromaDB client and collection
            self.client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False)
            )

            self.collection = self.client.get_or_create_collection(
                name="aura_project_context",
                metadata={"hnsw:space": "cosine", "hnsw:M": 16}
            )

            # Track file changes and relationships with timestamps
            self.file_hashes = {}
            self.recently_modified = {}  # file_path -> timestamp
            self.temporal_cache_timeout = timedelta(hours=1)

            logger.info(f"Vector database connected. Collection contains {self.collection.count()} documents.")

        except Exception as e:
            logger.error(f"Failed to initialize VectorContextService: {e}", exc_info=True)
            raise

    def _load_embedding_model(self):
        """Load embedding model with CodeBERT first, fallback to default."""
        try:
            model = SentenceTransformer(CODEBERT_MODEL)
            logger.info(f"Using {CODEBERT_MODEL} for code embeddings")
            return model
        except Exception as e:
            logger.warning(f"CodeBERT unavailable ({e}), using fallback model")
            try:
                model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
                logger.info(f"Using fallback model {DEFAULT_EMBEDDING_MODEL}")
                return model
            except Exception as e2:
                logger.error(f"Failed to load any embedding model: {e2}")
                raise

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]]):
        """
        Adds or updates documents in the vector store with enhanced metadata.
        """
        if not documents:
            logger.warning("add_documents called with no documents to add.")
            return

        logger.info(f"Generating embeddings for {len(documents)} new documents...")

        # Create enhanced embedding content
        enhanced_documents = []
        for i, doc in enumerate(documents):
            enhanced_content = self._create_embedding_content(doc, metadatas[i])
            enhanced_documents.append(enhanced_content)

        embeddings = self.embedding_model.encode(enhanced_documents, show_progress_bar=True)

        # Generate unique IDs based on metadata
        ids = [
            f"{meta['file_path']}-{meta.get('node_type', 'file')}-{meta.get('node_name', '')}-{meta.get('line_start', 0)}"
            for meta in metadatas]

        logger.info(f"Adding {len(documents)} documents to the vector collection...")
        self.collection.upsert(
            embeddings=embeddings.tolist(),
            documents=enhanced_documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"Successfully added documents. Collection now has {self.collection.count()} items.")

    def index_project_comprehensive(self, project_root: Path, force_reindex: bool = False, batch_size: int = 100) -> Dict[str, int]:
        """
        Comprehensive project indexing with change detection and advanced analysis.
        Processes files in batches to avoid memory issues.
        """
        logger.info("Starting comprehensive project indexing...")
        stats = {"new": 0, "updated": 0, "skipped": 0, "errors": 0}

        # Get all Python files
        python_files = [f for f in project_root.rglob("*.py") if self._should_index_file(f)]
        logger.info(f"Found {len(python_files)} Python files to process")

        # Process files in batches
        for batch_start in range(0, len(python_files), batch_size):
            batch_end = min(batch_start + batch_size, len(python_files))
            batch_files = python_files[batch_start:batch_end]
            logger.info(f"Processing batch {batch_start//batch_size + 1}: files {batch_start + 1}-{batch_end}")

            batch_stats = self._process_file_batch(batch_files, project_root, force_reindex)
            
            # Merge batch stats
            for key in stats:
                stats[key] += batch_stats[key]

        logger.info(f"Indexing complete: {stats}")
        return stats

    def _process_file_batch(self, file_batch: List[Path], project_root: Path, force_reindex: bool) -> Dict[str, int]:
        """Process a batch of files for indexing."""
        batch_stats = {"new": 0, "updated": 0, "skipped": 0, "errors": 0}
        all_documents = []
        all_metadatas = []

        for file_path in file_batch:
            try:
                if not force_reindex and not self._file_changed(file_path):
                    batch_stats["skipped"] += 1
                    continue

                # Extract comprehensive code elements
                elements = self._extract_comprehensive_elements(file_path, project_root)

                for element in elements:
                    # Create embedding content and metadata
                    embedding_content = element.content
                    metadata = self._code_context_to_metadata(element)

                    all_documents.append(embedding_content)
                    all_metadatas.append(metadata)

                batch_stats["new"] += len(elements)

                # Update file hash
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.file_hashes[str(file_path)] = self._compute_file_hash(content)

            except Exception as e:
                logger.error(f"Error indexing {file_path}: {e}")
                batch_stats["errors"] += 1

        # Add batch documents to vector store
        if all_documents:
            self.add_documents(all_documents, all_metadatas)

        return batch_stats

    def smart_query(self, query_text: str, intent: str = "understand",
                    current_file: Optional[str] = None, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Intelligent query that understands coding intent and context.
        """
        if self.collection.count() == 0:
            logger.warning("Query attempted on an empty collection.")
            return []

        logger.info(f"Smart query: '{query_text[:50]}...' with intent '{intent}'")

        # Enhance query based on intent
        enhanced_query = self._enhance_query_for_intent(query_text, intent)

        # Get more results for reranking
        initial_results = min(50, n_results * 10)

        results = self.collection.query(
            query_texts=[enhanced_query],
            n_results=initial_results,
            include=['documents', 'metadatas', 'distances']
        )

        if not results['documents']:
            return []

        # Convert to structured results with scoring
        structured_results = []
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]

            # Calculate intent-based score
            intent_score = self._calculate_intent_score(metadata, intent)

            # Calculate context score
            context_score = self._calculate_context_score(metadata, current_file)

            # Calculate temporal score
            temporal_score = self._calculate_temporal_score(metadata)

            # Final composite score
            final_score = (
                    0.4 * (1.0 - distance) +  # Semantic similarity
                    0.3 * intent_score +  # Intent relevance
                    0.2 * context_score +  # File/module context
                    0.1 * temporal_score  # Recency
            )

            structured_results.append({
                "document": doc,
                "metadata": metadata,
                "semantic_score": 1.0 - distance,
                "intent_score": intent_score,
                "context_score": context_score,
                "temporal_score": temporal_score,
                "final_score": final_score,
                "explanation": self._generate_explanation(metadata, intent, final_score)
            })

        # Sort by final score and return top results
        structured_results.sort(key=lambda x: x['final_score'], reverse=True)

        # Apply diversity (max 2 results per file)
        diversified = self._apply_diversity(structured_results, max_per_file=2)

        logger.info(f"Returning {len(diversified[:n_results])} smart results")
        return diversified[:n_results]

    def query(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Standard query method (backward compatible).
        """
        return self.smart_query(query_text, "understand", None, n_results)

    def get_relevant_context(self, query: str, current_file: Optional[str] = None,
                             max_results: int = 10) -> str:
        """
        Backward-compatible method that returns formatted context string with smart results.
        """
        # Detect intent from query
        intent = self._detect_intent(query)

        results = self.smart_query(query, intent, current_file, max_results)

        if not results:
            return "No relevant context found in the project."

        context_parts = ["Here are the most relevant code snippets:\n"]

        for result in results:
            metadata = result['metadata']
            explanation = result['explanation']
            score = result['final_score']

            source_info = f"From {metadata.get('file_path', 'N/A')}"
            if metadata.get('parent_class'):
                source_info += f" (class {metadata['parent_class']})"

            context_parts.append(
                f"```python\n# {source_info}\n# Relevance: {score:.2f} - {explanation}\n{result['document']}\n```"
            )

        return "\n\n".join(context_parts)

    def mark_file_modified(self, file_path: str):
        """Mark a file as recently modified for temporal scoring."""
        self.recently_modified[file_path] = datetime.now()
        self._cleanup_temporal_cache()

    def _cleanup_temporal_cache(self):
        """Remove old entries from temporal cache."""
        cutoff = datetime.now() - self.temporal_cache_timeout
        expired_files = [
            file_path for file_path, timestamp in self.recently_modified.items()
            if timestamp < cutoff
        ]
        for file_path in expired_files:
            del self.recently_modified[file_path]
        
        if expired_files:
            logger.debug(f"Cleaned up {len(expired_files)} expired temporal entries")

    def _extract_comprehensive_elements(self, file_path: Path, project_root: Path) -> List[CodeContext]:
        """Extract comprehensive code elements with rich context."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            elements = []
            lines = content.split('\n')
            relative_path = str(file_path.relative_to(project_root))

            class ElementExtractor(ast.NodeVisitor):
                def __init__(self):
                    self.current_class = None

                def visit_ClassDef(self, node):
                    old_class = self.current_class
                    self.current_class = node.name

                    element = self._create_code_context_from_node(
                        node, CodeElementType.CLASS, content, lines, relative_path, self.current_class
                    )
                    elements.append(element)

                    self.generic_visit(node)
                    self.current_class = old_class

                def visit_FunctionDef(self, node):
                    element_type = CodeElementType.METHOD if self.current_class else CodeElementType.FUNCTION
                    if node.name.startswith('test_'):
                        element_type = CodeElementType.TEST

                    element = self._create_code_context_from_node(
                        node, element_type, content, lines, relative_path, self.current_class
                    )
                    elements.append(element)

                    # Don't visit child functions

            extractor = ElementExtractor()
            extractor.visit(tree)

            return elements

        except Exception as e:
            logger.warning(f"Could not extract elements from {file_path}: {e}")
            return []

    def _create_code_context_from_node(self, node: ast.AST, element_type: CodeElementType,
                                       content: str, lines: List[str], file_path: str,
                                       current_class: Optional[str]) -> CodeContext:
        """Create CodeContext from AST node."""

        # Extract source code
        source_lines = lines[node.lineno - 1:node.end_lineno]
        source_content = '\n'.join(source_lines)

        # Extract parameters for functions
        parameters = []
        return_type = None
        if isinstance(node, ast.FunctionDef):
            parameters = [arg.arg for arg in node.args.args]
            if node.returns:
                return_type = ast.unparse(node.returns)

        # Extract docstring
        docstring = None
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and
                node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant)):
            docstring = node.body[0].value.value

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        # Extract function calls
        calls_made = set()
        for child_node in ast.walk(node):
            if isinstance(child_node, ast.Call):
                if isinstance(child_node.func, ast.Name):
                    calls_made.add(child_node.func.id)
                elif isinstance(child_node.func, ast.Attribute):
                    calls_made.add(child_node.func.attr)

        element_id = f"{file_path}:{element_type.value}:{node.name}:{node.lineno}"

        return CodeContext(
            element_id=element_id,
            element_type=element_type,
            name=node.name,
            content=source_content,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno,
            parent_class=current_class,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            complexity_score=complexity,
            calls_made=calls_made,
            modified_at=datetime.now()
        )

    def _create_embedding_content(self, content: str, metadata: Dict[str, Any]) -> str:
        """Create rich content for embedding that includes context."""
        parts = []

        # Add element info
        element_type = metadata.get('node_type', 'unknown')
        name = metadata.get('node_name', 'unknown')
        parts.append(f"{element_type}: {name}")

        # Add docstring if available
        docstring = metadata.get('docstring')
        if docstring:
            parts.append(f"Documentation: {docstring}")

        # Add parameters for functions
        parameters = metadata.get('parameters', [])
        if parameters:
            parts.append(f"Parameters: {', '.join(parameters)}")

        # Add return type
        return_type = metadata.get('return_type')
        if return_type:
            parts.append(f"Returns: {return_type}")

        # Add the actual code
        parts.append(content)

        # Add usage context
        calls_made = metadata.get('calls_made', [])
        if calls_made:
            parts.append(f"Uses: {', '.join(calls_made[:5])}")

        return "\n".join(parts)

    def _code_context_to_metadata(self, context: CodeContext) -> Dict[str, Any]:
        """Convert CodeContext to metadata dictionary."""
        return {
            "element_id": context.element_id,
            "node_type": context.element_type.value,
            "node_name": context.name,
            "file_path": context.file_path,
            "line_start": context.line_start,
            "line_end": context.line_end,
            "parent_class": context.parent_class,
            "parameters": context.parameters,
            "return_type": context.return_type,
            "docstring": context.docstring,
            "complexity_score": context.complexity_score,
            "modified_at": context.modified_at.isoformat(),
            "calls_made": list(context.calls_made)
        }

    def _should_index_file(self, file_path: Path) -> bool:
        """Determine if a file should be indexed."""
        exclude_patterns = {
            '__pycache__', '.venv', 'venv', 'node_modules', '.git',
            'dist', 'build', '.pytest_cache', '.mypy_cache'
        }
        return not any(pattern in str(file_path) for pattern in exclude_patterns)

    def _file_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last indexing."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            current_hash = self._compute_file_hash(content)
            stored_hash = self.file_hashes.get(str(file_path))
            return current_hash != stored_hash
        except:
            return True

    def _compute_file_hash(self, content: str) -> str:
        """Compute hash of file content."""
        return hashlib.md5(content.encode()).hexdigest()

    def _calculate_complexity(self, node: ast.AST) -> float:
        """Calculate cyclomatic complexity."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
        return complexity

    def _detect_intent(self, query: str) -> str:
        """Detect coding intent from query text."""
        query_lower = query.lower()

        if any(word in query_lower for word in ['create', 'build', 'implement', 'add', 'make']):
            return 'implement'
        elif any(word in query_lower for word in ['fix', 'debug', 'error', 'bug', 'broken']):
            return 'debug'
        elif any(word in query_lower for word in ['test', 'verify', 'check', 'validate']):
            return 'test'
        elif any(word in query_lower for word in ['refactor', 'improve', 'clean', 'optimize']):
            return 'refactor'

        return 'understand'

    def _enhance_query_for_intent(self, query: str, intent: str) -> str:
        """Enhance query based on detected intent."""
        intent_keywords = {
            'implement': 'function class method implementation example',
            'debug': 'error exception try catch fix solution',
            'test': 'test assert mock verify validate',
            'refactor': 'clean optimize improve structure',
            'understand': 'documentation explanation example usage'
        }

        enhancement = intent_keywords.get(intent, '')
        return f"{query} {enhancement}".strip()

    def _calculate_intent_score(self, metadata: Dict, intent: str) -> float:
        """Calculate how well metadata matches the intent."""
        element_type = metadata.get('node_type', '')
        name = metadata.get('node_name', '').lower()

        # Intent-based scoring
        intent_weights = {
            'implement': {'function': 1.0, 'class': 0.9, 'method': 0.95},
            'debug': {'function': 0.8, 'method': 0.85, 'test': 0.95},
            'understand': {'class': 1.0, 'function': 0.9, 'method': 0.8},
            'test': {'test': 1.0, 'function': 0.8, 'method': 0.8},
            'refactor': {'function': 1.0, 'class': 0.95, 'method': 0.9}
        }

        base_score = intent_weights.get(intent, {}).get(element_type, 0.5)

        # Boost for name patterns
        if intent == 'test' and ('test_' in name or 'test' in name):
            base_score *= 1.5
        elif intent == 'debug' and any(word in name for word in ['error', 'exception', 'handle']):
            base_score *= 1.3

        return min(1.0, base_score)

    def _calculate_context_score(self, metadata: Dict, current_file: Optional[str]) -> float:
        """Calculate context relevance score."""
        if not current_file:
            return 0.5

        file_path = metadata.get('file_path', '')

        # Same file gets highest score
        if current_file == file_path:
            return 1.0

        # Same module/package gets good score
        if current_file and file_path:
            current_module = current_file.replace('/', '.').replace('\\', '.')
            result_module = file_path.replace('/', '.').replace('\\', '.')

            if current_module.startswith(result_module) or result_module.startswith(current_module):
                return 0.7

        return 0.3

    def _calculate_temporal_score(self, metadata: Dict) -> float:
        """Calculate temporal relevance score based on file modification time."""
        file_path = metadata.get('file_path', '')

        if file_path not in self.recently_modified:
            return 0.3  # Default score for files not recently modified

        # Calculate score based on how recently the file was modified
        modified_time = self.recently_modified[file_path]
        time_since_modification = datetime.now() - modified_time
        
        # Score decreases with time (1.0 for immediate, 0.5 for 1 hour old)
        hours_since_modification = time_since_modification.total_seconds() / 3600
        temporal_score = max(0.5, 1.0 - (hours_since_modification / self.temporal_cache_timeout.total_seconds()))
        
        return min(1.0, temporal_score)

    def _generate_explanation(self, metadata: Dict, intent: str, score: float) -> str:
        """Generate explanation for why result is relevant."""
        explanations = []

        if score > 0.8:
            explanations.append("high relevance")
        elif score > 0.6:
            explanations.append("good match")
        else:
            explanations.append("partial match")

        element_type = metadata.get('node_type', '')
        if intent == 'test' and element_type == 'test':
            explanations.append("test function")
        elif intent == 'implement' and element_type in ['function', 'class']:
            explanations.append(f"implementation {element_type}")

        if metadata.get('docstring'):
            explanations.append("documented")

        complexity = metadata.get('complexity_score', 0)
        if complexity > 10:
            explanations.append("complex")

        return ", ".join(explanations)

    def _apply_diversity(self, results: List[Dict], max_per_file: int = 2) -> List[Dict]:
        """Apply diversity to avoid too many results from same file."""
        file_counts = {}
        diversified = []

        for result in results:
            file_path = result['metadata'].get('file_path', '')
            current_count = file_counts.get(file_path, 0)

            if current_count < max_per_file:
                diversified.append(result)
                file_counts[file_path] = current_count + 1

        return diversified