# foundry/actions/copy_file_action.py
"""
Contains the action function for copying a file.
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

def copy_file(source_path: str, destination_path: str) -> str:
    """
    Copies a file from a source to a destination, preserving metadata.
    Creates parent directories for the destination if they don't exist.

    Args:
        source_path: The path of the file to be copied.
        destination_path: The target path for the new copy.

    Returns:
        A string indicating the success or failure of the operation.
    """
    try:
        source = Path(source_path)
        destination = Path(destination_path)
        logger.info(f"Attempting to copy '{source}' to '{destination}'.")

        # --- Safety Check: Ensure the source exists and is a file ---
        if not source.exists():
            error_message = f"Error: Source file not found at '{source_path}'."
            logger.warning(error_message)
            return error_message
        if not source.is_file():
            error_message = f"Error: Source path '{source_path}' is a directory, not a file. This tool only copies files."
            logger.warning(error_message)
            return error_message

        # --- Ensure destination directory exists ---
        destination.parent.mkdir(parents=True, exist_ok=True)

        # --- Perform the copy using copy2 to preserve metadata ---
        shutil.copy2(str(source), str(destination))

        success_message = f"Successfully copied file from '{source_path}' to '{destination_path}'."
        logger.info(success_message)
        return success_message

    except Exception as e:
        error_message = f"An unexpected error occurred while copying file: {e}"
        logger.exception(error_message)
        return error_message