# foundry/foundry_manager.py
import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)


class FoundryManager:
    """
    Manages Blueprints and Actions by dynamically discovering them from the filesystem.
    """

    def __init__(self) -> None:
        self._blueprints: Dict[str, Blueprint] = {}
        # --- NEW: A registry for our dynamically loaded action functions ---
        self._actions: Dict[str, Callable[..., Any]] = {}

        self._discover_and_load_blueprints()
        # --- NEW: Call the action loader ---
        self._discover_and_load_actions()

        logger.info(
            f"FoundryManager initialized with {len(self._blueprints)} blueprints and {len(self._actions)} actions.")

    def _add_blueprint(self, blueprint: Blueprint) -> None:
        if blueprint.id in self._blueprints:
            logger.warning("Blueprint with id '%s' is being overwritten.", blueprint.id)
        self._blueprints[blueprint.id] = blueprint
        logger.debug("Registered blueprint: %s", blueprint.id)

    def _discover_and_load_blueprints(self) -> None:
        """
        Scans the 'blueprints' package, imports each module, and registers the
        Blueprint instance named 'blueprint' found within.
        """
        try:
            blueprints_dir = Path(__file__).parent.parent / "blueprints"
            package_name = "blueprints"

            for file_path in blueprints_dir.glob("*.py"):
                if file_path.name.startswith("__"):
                    continue

                module_name = f"{package_name}.{file_path.stem}"
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, "blueprint") and isinstance(module.blueprint, Blueprint):
                        self._add_blueprint(module.blueprint)
                        logger.info("Loaded blueprint '%s' from %s.", module.blueprint.id, file_path.name)
                    else:
                        logger.warning("File %s does not contain a valid 'blueprint' instance.", file_path.name)
                except Exception as e:
                    logger.error("Failed to load blueprint from %s: %s", file_path.name, e)
        except Exception as e:
            logger.critical("A critical error occurred during blueprint discovery: %s", e)

    def _discover_and_load_actions(self) -> None:
        """
        Scans the 'foundry.actions' package, imports each module, and registers
        all functions found within into the action registry.
        """
        try:
            # --- The path to our new actions package ---
            actions_dir = Path(__file__).parent / "actions"
            # --- The importable name of the package ---
            package_name = "foundry.actions"

            for file_path in actions_dir.glob("*.py"):
                if file_path.name.startswith("__"):
                    continue

                module_name = f"{package_name}.{file_path.stem}"
                try:
                    module = importlib.import_module(module_name)
                    # Use inspect to find all function objects in the module
                    for name, func in inspect.getmembers(module, inspect.isfunction):
                        if name in self._actions:
                            logger.warning(f"Action function '{name}' is being overwritten by module '{module_name}'.")
                        self._actions[name] = func
                        logger.debug(f"Registered action function: {name} from {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to load actions from {file_path.name}: {e}")
        except Exception as e:
            logger.critical(f"A critical error occurred during action discovery: {e}")

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        return self._blueprints.get(name)

    def get_action(self, name: str) -> Optional[Callable[..., Any]]:
        """Retrieves a loaded action function from the registry by its name."""
        return self._actions.get(name)

    def get_llm_tool_definitions(self) -> List[Dict[str, Any]]:
        definitions: List[Dict[str, Any]] = []
        for bp in self._blueprints.values():
            tool_def = {
                "type": "function",
                "function": {"name": bp.id, "description": bp.description, "parameters": bp.parameters},
            }
            definitions.append(tool_def)
        return definitions