import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def rename_file(source_path: str, destination_path: str) -> dict:
    """
    Renames (moves) a file from a source path to a destination path.

    Args:
        source_path (str): The original path of the file.
        destination_path (str): The new path for the file.

    Returns:
        dict: A dictionary with the status of the operation.
    """
    if not os.path.exists(source_path):
        message = f"Error: Source file not found at '{source_path}'"
        logging.error(message)
        return {"status": "error", "message": message}
    try:
        os.rename(source_path, destination_path)
        message = f"Successfully renamed '{source_path}' to '{destination_path}'."
        logging.info(message)
        return {"status": "success", "message": message}
    except OSError as e:
        message = f"Error renaming file: {e}"
        logging.error(message)
        return {"status": "error", "message": str(e)}
