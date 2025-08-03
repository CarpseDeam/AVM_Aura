# foundry/actions/delete_file_action.py
"""
Contains the action function for deleting a file from the filesystem.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def delete_file(path: str) -> str:
    """
    Deletes a single file after performing safety checks.

    This function will not delete directories. It ensures the path exists and
    is a file before attempting deletion.

    Args:
        path: The path to the file to be deleted.

    Returns:
        A string indicating the success or failure of the operation.
    """
    try:
        logger.info(f"Attempting to delete file: {path}")
        path_obj = Path(path)

        # --- Safety Check 1: Ensure the path exists ---
        if not path_obj.exists():
            error_message = f"Error: Cannot delete. File not found at '{path}'."
            logger.warning(error_message)
            return error_message

        # --- Safety Check 2: Ensure the path is a file, not a directory ---
        if not path_obj.is_file():
            error_message = f"Error: Path '{path}' is a directory, not a file. This tool only deletes files."
            logger.warning(error_message)
            return error_message

        # --- If checks pass, proceed with deletion ---
        path_obj.unlink()
        success_message = f"Successfully deleted file: {path}"
        logger.info(success_message)
        return success_message

    except Exception as e:
        error_message = f"An unexpected error occurred while deleting file {path}: {e}"
        logger.exception(error_message)
        return error_message