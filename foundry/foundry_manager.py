# foundry/foundry_manager.py

"""
Provides a manager to centralize the creation and retrieval of Blueprint tools.

This module defines the FoundryManager class, which is responsible for dynamically
discovering, loading, and providing access to all available Blueprint objects
from the 'blueprints/' directory. It acts as a single source of truth for the
tools that the LLM can use.
"""

import importlib
import inspect
import logging
import os
from typing import Any, Dict, List, Optional

from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)


class FoundryManager:
    """
    Manages the lifecycle and retrieval of available Blueprint tools by
    dynamically discovering them from the filesystem.
    """

    def __init__(self) -> None:
        """Initializes the FoundryManager and loads all discoverable blueprints."""
        self._blueprints: Dict[str, Blueprint] = {}
        self._discover_and_load_blueprints()
        logger.info(
            "FoundryManager initialized with %d blueprints.", len(self._blueprints)
        )

    def _add_blueprint(self, blueprint: Blueprint) -> None:
        """
        Registers a single blueprint with the manager.

        Args:
            blueprint (Blueprint): The blueprint instance to register.
        """
        if blueprint.name in self._blueprints:
            logger.warning(
                "Blueprint with name '%s' is being overwritten.", blueprint.name
            )
        self._blueprints[blueprint.name] = blueprint
        logger.debug("Registered blueprint: %s", blueprint.name)

    def _discover_and_load_blueprints(self) -> None:
        """
        Discovers and loads all blueprints from the 'blueprints' directory.

        This method scans the 'blueprints' package, imports each module,
        and registers any instances of the Blueprint class it finds.
        """
        try:
            # Assumes 'foundry' and 'blueprints' are sibling directories.
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            blueprints_dir = os.path.join(project_root, "blueprints")
            package_name = "blueprints"

            if not os.path.isdir(blueprints_dir):
                logger.error(
                    "Blueprints directory not found at '%s'. No blueprints will be loaded.",
                    blueprints_dir,
                )
                return

            for filename in os.listdir(blueprints_dir):
                # Load only Python files that are not __init__.py
                if filename.endswith(".py") and not filename.startswith("__"):
                    module_name = filename[:-3]  # Remove .py extension
                    full_module_path = f"{package_name}.{module_name}"
                    try:
                        module = importlib.import_module(full_module_path)
                        # Find all Blueprint instances in the loaded module
                        for _, obj in inspect.getmembers(module):
                            if isinstance(obj, Blueprint):
                                self._add_blueprint(obj)
                                logger.info(
                                    "Successfully loaded blueprint '%s' from %s.",
                                    obj.name,
                                    filename,
                                )
                    except ImportError as e:
                        logger.error(
                            "Failed to import blueprint module %s: %s",
                            full_module_path,
                            e,
                        )
                    except Exception as e:
                        logger.error(
                            "An unexpected error occurred while loading from %s: %s",
                            filename,
                            e,
                        )
        except Exception as e:
            logger.critical(
                "A critical error occurred during blueprint discovery: %s", e
            )

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        """
        Retrieves a blueprint by its unique name.

        Args:
            name (str): The name of the blueprint to retrieve.

        Returns:
            Optional[Blueprint]: The blueprint instance if found, otherwise None.
        """
        return self._blueprints.get(name)

    def get_all_blueprints(self) -> List[Blueprint]:
        """
        Retrieves a list of all registered blueprint instances.

        Returns:
            List[Blueprint]: A list of all blueprints.
        """
        return list(self._blueprints.values())

    def get_llm_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Generates a list of tool definitions formatted for an LLM.

        This format is typically used to inform the LLM about the available
        functions it can call.

        Returns:
            List[Dict[str, Any]]: A list of tool definitions suitable for LLM APIs.
        """
        definitions: List[Dict[str, Any]] = []
        for blueprint in self._blueprints.values():
            try:
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": blueprint.name,
                        "description": blueprint.description,
                        "parameters": blueprint.parameters,
                    },
                }
                definitions.append(tool_def)
            except AttributeError as e:
                logger.error(
                    "Failed to create tool definition for blueprint '%s'. "
                    "The Blueprint object may be missing required attributes. Error: %s",
                    blueprint.name,
                    e,
                )
        return definitions