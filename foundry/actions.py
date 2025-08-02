# foundry/actions.py

"""
This module provides concrete implementations of file system operations.
"""

import logging
import os
from pathlib import Path
from typing import List

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
        # --- THIS IS THE FIX ---
        # If the path provided is an empty string or None, default to "."
        # which represents the current directory.
        if not path:
            path = "."
        # --- END FIX ---

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