# services/config_manager.py

"""
Manages application configuration from a `config.yaml` file.

This service handles the creation of a default configuration file if one
does not exist, and provides a simple interface to access configuration
values, including nested ones.
"""

import logging
import os
import yaml
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH = "config.yaml"

DEFAULT_CONFIG = {
    'llm_provider': 'gemini',
    'gemini': {
        'api_key': 'YOUR_GEMINI_API_KEY_HERE'
    },
    'ollama': {
        'model': 'llama3',
        'base_url': 'http://localhost:11434'
    }
}


class ConfigManager:
    """
    Handles loading and accessing configuration from a YAML file.

    This class will check for the existence of `config.yaml` upon
    instantiation. If the file is not found, it will create one with
    default settings. It provides a `get` method to retrieve
    configuration values.
    """

    def __init__(self, config_path: str = CONFIG_FILE_PATH) -> None:
        """
        Initializes the ConfigManager.

        Args:
            config_path (str): The path to the configuration file.
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self._load_or_create_config()

    def _load_or_create_config(self) -> None:
        """
        Loads the configuration from the file or creates it if it doesn't exist.
        """
        if not os.path.exists(self.config_path):
            logger.info(f"Configuration file not found at '{self.config_path}'. Creating with default settings.")
            self._create_default_config()
        
        self._load_config()

    def _create_default_config(self) -> None:
        """
        Creates the default configuration file with placeholder values.
        """
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Default configuration file created at '{self.config_path}'.")
            logger.warning(f"Please update '{self.config_path}' with your specific settings (e.g., API keys).")
        except IOError as e:
            logger.error(f"Failed to create default configuration file at '{self.config_path}': {e}")
            # The application will likely fail later when trying to access config,
            # which is an acceptable outcome if the file cannot be created.

    def _load_config(self) -> None:
        """
        Loads the configuration from the YAML file into the instance.
        """
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                if config_data is None:
                    self.config = {}
                    logger.warning(f"Configuration file '{self.config_path}' is empty.")
                else:
                    self.config = config_data
                logger.info(f"Configuration loaded successfully from '{self.config_path}'.")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file '{self.config_path}': {e}")
            self.config = {}  # Use an empty config to prevent crashes
        except IOError as e:
            logger.error(f"Failed to read configuration file '{self.config_path}': {e}")
            self.config = {}

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Retrieves a configuration value for a given key.

        This method supports nested key access using dot notation. For example,
        `get('ollama.model')` will retrieve the 'model' value from the
        'ollama' dictionary.

        Args:
            key (str): The configuration key. Can be nested using dots.
            default (Optional[Any]): The default value to return if the key
                                     is not found. Defaults to None.

        Returns:
            Any: The configuration value, or the provided default if not found.
        """
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value[k]
                else:
                    # This handles cases where a sub-path is not a dict
                    logger.debug(f"Config key '{key}' not found. Path segment '{k}' is not a dictionary.")
                    return default
            return value
        except KeyError:
            logger.debug(f"Configuration key '{key}' not found in config file.")
            return default
        except TypeError:
            # This can happen if self.config is None or not a dict
            logger.warning(f"Configuration is not a valid dictionary. Cannot retrieve key '{key}'.")
            return default