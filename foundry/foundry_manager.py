# foundry/foundry_manager.py
"""
Provides a manager to centralize the creation and retrieval of Blueprint tools by
dynamically discovering them from the filesystem.
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from foundry.blueprints import Blueprint

logger = logging.getLogger(__name__)

class FoundryManager:
    """
    Manages Blueprint tools by dynamically discovering them from the 'blueprints' directory.
    """

    def __init__(self) -> None:
        self._blueprints: Dict[str, Blueprint] = {}
        self._discover_and_load_blueprints()
        logger.info("FoundryManager initialized with %d blueprints.", len(self._blueprints))

    def _add_blueprint(self, blueprint: Blueprint) -> None:
        # <-- FIX: Changed blueprint.name to blueprint.id
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
            # Assumes the 'blueprints' directory is a sibling to 'foundry'
            blueprints_dir = Path(__file__).parent.parent / "blueprints"
            package_name = "blueprints"

            for file_path in blueprints_dir.glob("*.py"):
                if file_path.name.startswith("__"):
                    continue

                module_name = f"{package_name}.{file_path.stem}"
                try:
                    module = importlib.import_module(module_name)
                    # Convention: each blueprint file must define a 'blueprint' variable.
                    if hasattr(module, "blueprint") and isinstance(module.blueprint, Blueprint):
                        self._add_blueprint(module.blueprint)
                        # <-- FIX: Changed module.blueprint.name to module.blueprint.id
                        logger.info("Loaded blueprint '%s' from %s.", module.blueprint.id, file_path.name)
                    else:
                        logger.warning("File %s does not contain a valid 'blueprint' instance.", file_path.name)
                except Exception as e:
                    logger.error("Failed to load blueprint from %s: %s", file_path.name, e)
        except Exception as e:
            logger.critical("A critical error occurred during blueprint discovery: %s", e)

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        return self._blueprints.get(name)

    def get_llm_tool_definitions(self) -> List[Dict[str, Any]]:
        definitions: List[Dict[str, Any]] = []
        for bp in self._blueprints.values():
            tool_def = {
                "type": "function",
                # <-- FIX: Changed bp.name to bp.id
                "function": {"name": bp.id, "description": bp.description, "parameters": bp.parameters},
            }
            definitions.append(tool_def)
        return definitions