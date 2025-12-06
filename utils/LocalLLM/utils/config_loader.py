"""Configuration loader for LocalLMM models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


class ConfigLoader:
    """Singleton class to load and cache configuration."""

    _instance = None
    _config = None
    _config_path = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the config loader and load config on first use."""
        if ConfigLoader._config is None:
            self._load_config()

    def _load_config(self) -> None:
        """Load the llm_config.json file from the LocalLMM directory."""
        # Import config initializer
        from utils.LocalLLM.utils.config_initializer import get_config_path
        
        # Get config path and ensure it exists
        config_path = get_config_path()
        ConfigLoader._config_path = config_path

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                ConfigLoader._config = data if data else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file {config_path}: {exc}") from exc

        # Validate the configuration structure
        if ConfigLoader._config and not self._validate_config(ConfigLoader._config):
            raise ValueError(f"Invalid configuration structure in {config_path}")

    def _validate_config(self, config: dict) -> bool:
        """Validate that the config has the required structure."""
        if not isinstance(config, dict):
            return False

        # Check for required top-level keys
        if "model_directories" not in config:
            return False
        if "language_models" not in config:
            return False

        # Validate model_directories
        directories = config["model_directories"]
        if not isinstance(directories, dict):
            return False
        if "language" not in directories:
            return False

        # Validate language_models is a list
        if not isinstance(config["language_models"], list):
            return False

        # Validate each model entry has required fields
        for model in config["language_models"]:
            if not isinstance(model, dict):
                return False
            if "file_name" not in model:
                return False
            # nickname and parameters_billions are optional but recommended

        return True

    def _find_model_by_identifier(self, identifier: str) -> Optional[dict]:
        """Find a model by filename or nickname.

        Args:
            identifier: Either a filename (e.g., "1.5B-DeepSeek-R1-Q6KL.gguf") 
                       or nickname (e.g., "deepseek-1.5b")

        Returns:
            Model dictionary if found, None otherwise
        """
        if ConfigLoader._config is None:
            return None

        language_models = ConfigLoader._config.get("language_models", [])

        # First try to match by filename
        for model in language_models:
            if model.get("file_name") == identifier:
                return model

        # Then try to match by nickname
        for model in language_models:
            if model.get("nickname") == identifier:
                return model

        return None

    def get_model_path(self, model_identifier: str) -> str:
        """Get the full path to a model file.

        Args:
            model_identifier: Either a filename or nickname from the config

        Returns:
            Full path to the model file

        Raises:
            FileNotFoundError: If the model is not found in config or doesn't exist
        """
        # Try to find in config first
        model_entry = self._find_model_by_identifier(model_identifier)

        if model_entry:
            # Found in config, build path from config
            file_name = model_entry["file_name"]
            language_dir = ConfigLoader._config["model_directories"]["language"]
            model_path = os.path.join(language_dir, file_name)

            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found at: {model_path}")

            return model_path

        # Fallback: try as direct filename in default directory
        default_dir = "models/language"
        fallback_path = os.path.join(default_dir, model_identifier)

        if os.path.exists(fallback_path):
            return fallback_path

        # If we get here, model was not found
        raise FileNotFoundError(
            f"Model '{model_identifier}' not found in config and does not exist "
            f"at fallback path: {fallback_path}"
        )

    def get_model_parameters(self, model_identifier: str) -> Optional[float]:
        """Get the parameter count (in billions) for a model.

        Args:
            model_identifier: Either a filename or nickname from the config

        Returns:
            Parameter count in billions, or None if not found/specified
        """
        model_entry = self._find_model_by_identifier(model_identifier)

        if model_entry:
            return model_entry.get("parameters_billions")

        return None

    def get_language_model_dir(self) -> str:
        """Get the configured language models directory.

        Returns:
            Path to the language models directory
        """
        if ConfigLoader._config is None:
            return "models/language"  # Fallback default

        return ConfigLoader._config["model_directories"]["language"]

    def get_voice_model_dir(self) -> str:
        """Get the configured voice models directory.

        Returns:
            Path to the voice models directory
        """
        if ConfigLoader._config is None:
            return "models/voice"  # Fallback default

        return ConfigLoader._config["model_directories"].get("voice", "models/voice")

    def get_all_language_models(self) -> list[dict]:
        """Get all configured language models.

        Returns:
            List of model dictionaries
        """
        if ConfigLoader._config is None:
            return []

        return ConfigLoader._config.get("language_models", [])


# Module-level convenience functions
_loader = None


def _get_loader() -> ConfigLoader:
    """Get or create the singleton config loader."""
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader


def get_model_path(model_identifier: str) -> str:
    """Get the full path to a model file.

    Args:
        model_identifier: Either a filename or nickname from the config

    Returns:
        Full path to the model file

    Raises:
        FileNotFoundError: If the model is not found
    """
    return _get_loader().get_model_path(model_identifier)


def get_model_parameters(model_identifier: str) -> Optional[float]:
    """Get the parameter count (in billions) for a model.

    Args:
        model_identifier: Either a filename or nickname from the config

    Returns:
        Parameter count in billions, or None if not found/specified
    """
    return _get_loader().get_model_parameters(model_identifier)


def get_language_model_dir() -> str:
    """Get the configured language models directory.

    Returns:
        Path to the language models directory
    """
    return _get_loader().get_language_model_dir()


def get_voice_model_dir() -> str:
    """Get the configured voice models directory.

    Returns:
        Path to the voice models directory
    """
    return _get_loader().get_voice_model_dir()


def get_all_language_models() -> list[dict]:
    """Get all configured language models.

    Returns:
        List of model dictionaries
    """
    return _get_loader().get_all_language_models()
