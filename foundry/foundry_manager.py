# foundry/foundry_manager.py

"""
Provides a manager to centralize the creation and retrieval of Blueprint tools.

This module defines the FoundryManager class, which is responsible for instantiating,
registering, and providing access to all available Blueprint objects in the system.
It acts as a single source of truth for the tools that the LLM can use.
"""

import logging
from typing import List, Dict, Optional, Any

# The architect has specified that `Blueprint` is available for import.
# We assume it has at least `name`, `description`, and `parameters` attributes.
from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)


class FoundryManager:
    """
    Manages the lifecycle and retrieval of available Blueprint tools.

    This class discovers, creates, and stores all Blueprint instances, making them
    accessible to other parts of the application, such as the LLMOperator. It
    also provides methods to format these blueprints into a schema that can be
    consumed by an LLM for tool-use functions.
    """

    def __init__(self) -> None:
        """Initializes the FoundryManager and registers all core blueprints."""
        self._blueprints: Dict[str, Blueprint] = {}
        self._register_core_blueprints()
        logger.info(
            "FoundryManager initialized with %d blueprints.", len(self._blueprints)
        )

    def _add_blueprint(self, blueprint: Blueprint) -> None:
        """
        Registers a single blueprint with the manager.

        Args:
            blueprint: The Blueprint instance to register.
        """
        if blueprint.name in self._blueprints:
            logger.warning(
                "Blueprint with name '%s' is being overwritten.", blueprint.name
            )
        self._blueprints[blueprint.name] = blueprint
        logger.debug("Registered blueprint: %s", blueprint.name)

    def _register_core_blueprints(self) -> None:
        """
        Creates and registers the set of core, built-in blueprints.

        This method defines the standard tools available to the AVM, such as
        file system operations.
        """
        # Define the schema for the write_file tool
        write_file_params = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative or absolute path to the file.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write into the file.",
                },
            },
            "required": ["path", "content"],
        }
        write_file_blueprint = Blueprint(
            name="write_file",
            description="Writes content to a specified file. Creates the file if it doesn't exist, or overwrites it if it does.",
            parameters=write_file_params,
        )
        self._add_blueprint(write_file_blueprint)

        # Define the schema for the read_file tool
        read_file_params = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The relative or absolute path of the file to read.",
                }
            },
            "required": ["path"],
        }
        read_file_blueprint = Blueprint(
            name="read_file",
            description="Reads the entire content of a specified file and returns it as a string.",
            parameters=read_file_params,
        )
        self._add_blueprint(read_file_blueprint)

        # Define the schema for the list_files tool
        list_files_params = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the directory to list. Defaults to the current directory if not provided.",
                }
            },
            "required": [],
        }
        list_files_blueprint = Blueprint(
            name="list_files",
            description="Lists all files and directories in a specified path.",
            parameters=list_files_params,
        )
        self._add_blueprint(list_files_blueprint)

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        """
        Retrieves a blueprint by its unique name.

        Args:
            name: The name of the blueprint to retrieve.

        Returns:
            The Blueprint instance if found, otherwise None.
        """
        return self._blueprints.get(name)

    def get_all_blueprints(self) -> List[Blueprint]:
        """
        Retrieves a list of all registered blueprint instances.

        Returns:
            A list containing all Blueprint objects managed by this instance.
        """
        return list(self._blueprints.values())

    def get_llm_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Generates a list of tool definitions formatted for an LLM.

        This method transforms the registered blueprints into a JSON-serializable
        list of dictionaries that conforms to the tool-calling schema of
        modern LLMs (e.g., OpenAI, Google Gemini).

        Returns:
            A list of dictionaries, where each dictionary defines a tool.
        """
        definitions: List[Dict[str, Any]] = []
        for blueprint in self._blueprints.values():
            try:
                # This structure is compatible with OpenAI's and Gemini's
                # function calling/tool use APIs.
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