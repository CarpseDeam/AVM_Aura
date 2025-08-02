# foundry/actions.py

"""
This module provides concrete implementations of file system operations.

These functions are designed to be the "actions" that the AI agent can execute.
Each function handles a specific, atomic file system task like reading, writing,
or listing files, and includes robust error handling and logging.
"""

import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def write_file(path: str, content: str) -> str:
    """Writes content to a specified file, creating directories if necessary.

    Args:
        path (str): The relative or absolute path to the file.
        content (str): The string content to write to the file.

    Returns:
        str: A message indicating the result of the operation.
    """
    try:
        logger.info(f"Attempting to write to file: {path}")
        path_obj = Path(path)

        # Ensure the parent directory exists
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Write the content to the file
        bytes_written = path_obj.write_text(content, encoding='utf-8')
        success_message = f"Successfully wrote {bytes_written} bytes to {path}"
        logger.info(success_message)
        return success_message
    except (IOError, OSError) as e:
        error_message = f"Error writing to file {path}: {e}"
        logger.error(error_message)
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while writing to file {path}: {e}"
        logger.exception(error_message)
        return error_message


def read_file(path: str) -> str:
    """Reads the content of a specified file.

    Args:
        path (str): The path to the file to be read.

    Returns:
        str: The content of the file, or an error message if it cannot be read.
    """
    try:
        logger.info(f"Attempting to read file: {path}")
        path_obj = Path(path)

        if not path_obj.exists():
            error_message = f"Error: File not found at path '{path}'"
            logger.warning(error_message)
            return error_message

        if not path_obj.is_file():
            error_message = f"Error: Path '{path}' is a directory, not a file."
            logger.warning(error_message)
            return error_message

        content = path_obj.read_text(encoding='utf-8')
        logger.info(f"Successfully read {len(content)} characters from {path}")
        return content
    except (IOError, OSError) as e:
        error_message = f"Error reading file {path}: {e}"
        logger.error(error_message)
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while reading file {path}: {e}"
        logger.exception(error_message)
        return error_message


def list_files(path: str = ".") -> str:
    """Lists files and directories at a given path.

    Args:
        path (str): The directory path to list. Defaults to the current directory.

    Returns:
        str: A formatted string of the directory's contents, or an error message.
    """
    try:
        logger.info(f"Listing contents of directory: {path}")
        path_obj = Path(path)

        if not path_obj.exists():
            error_message = f"Error: Directory not found at path '{path}'"
            logger.warning(error_message)
            return error_message

        if not path_obj.is_dir():
            error_message = f"Error: Path '{path}' is a file, not a directory."
            logger.warning(error_message)
            return error_message

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
    except (IOError, OSError) as e:
        error_message = f"Error listing directory {path}: {e}"
        logger.error(error_message)
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while listing directory {path}: {e}"
        logger.exception(error_message)
        return error_message