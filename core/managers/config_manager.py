import toml
from pathlib import Path
from typing import Any

class ConfigManager:
    """Manages loading and accessing application configuration from a TOML file."""

    def __init__(self, project_root: Path):
        self.config_path = project_root / "config" / "config.toml"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Loads the configuration from the TOML file."""
        try:
            return toml.load(self.config_path)
        except FileNotFoundError:
            # In a real application, you might want to create a default config
            # or raise a more specific error.
            raise FileNotFoundError(f"Configuration file not found at {self.config_path}")
        except toml.TomlDecodeError as e:
            raise ValueError(f"Error decoding TOML file: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from the configuration using dot notation.

        Args:
            key: The key to retrieve (e.g., "application.name").
            default: The default value to return if the key is not found.

        Returns:
            The configuration value or the default.
        """
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
