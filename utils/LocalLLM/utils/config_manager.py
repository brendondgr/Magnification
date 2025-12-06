"""Configuration management utilities for LocalLMM models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


class ConfigManager:
    """Manage model configurations (add, remove, update)."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the config manager.

        Args:
            config_path: Optional path to llm_config.json. If None, auto-detects.
        """
        if config_path is None:
            # Auto-detect config path using config initializer
            from utils.LocalLLM.utils.config_initializer import get_config_path
            config_path = get_config_path()

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load the configuration file."""
        if not self.config_path.exists():
            # If config doesn't exist, create and return blank config
            from utils.LocalLLM.utils.config_initializer import ensure_config_exists
            ensure_config_exists(self.config_path)
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if data else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file: {exc}") from exc

    def _save_config(self) -> None:
        """Save the configuration file."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def add_language_model(
        self,
        file_name: str,
        nickname: str,
        parameters_billions: float,
        check_exists: bool = True,
    ) -> bool:
        """Add a new language model to the configuration.

        Args:
            file_name: The model filename (e.g., "7B-Model-Q4.gguf")
            nickname: A short nickname for easy reference (e.g., "model-7b")
            parameters_billions: Model size in billions of parameters
            check_exists: If True, verify the file exists before adding

        Returns:
            True if added successfully, False if model already exists

        Raises:
            FileNotFoundError: If check_exists=True and file doesn't exist
            ValueError: If nickname is already in use
        """
        # Check if file_name already exists
        for model in self.config.get("language_models", []):
            if model.get("file_name") == file_name:
                print(f"Model with filename '{file_name}' already exists in config.")
                return False

        # Check if nickname is already in use
        for model in self.config.get("language_models", []):
            if model.get("nickname") == nickname:
                raise ValueError(
                    f"Nickname '{nickname}' is already in use by '{model.get('file_name')}'. "
                    "Please choose a different nickname."
                )

        # Verify file exists if requested
        if check_exists:
            language_dir = self.config["model_directories"]["language"]
            model_path = Path(language_dir) / file_name
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Model file not found at: {model_path}. "
                    "Set check_exists=False to add without verification."
                )

        # Add the model
        new_model = {
            "file_name": file_name,
            "nickname": nickname,
            "parameters_billions": parameters_billions,
        }

        if "language_models" not in self.config:
            self.config["language_models"] = []

        self.config["language_models"].append(new_model)
        self._save_config()

        print(f"✓ Added model: {nickname} ({file_name}, {parameters_billions}B)")
        return True

    def remove_language_model(self, identifier: str) -> bool:
        """Remove a language model from the configuration.

        Args:
            identifier: Either the filename or nickname of the model to remove

        Returns:
            True if removed successfully, False if not found
        """
        language_models = self.config.get("language_models", [])
        original_count = len(language_models)

        # Filter out the model (by filename or nickname)
        self.config["language_models"] = [
            model
            for model in language_models
            if model.get("file_name") != identifier and model.get("nickname") != identifier
        ]

        removed_count = original_count - len(self.config["language_models"])

        if removed_count > 0:
            self._save_config()
            print(f"✓ Removed model: {identifier}")
            return True
        else:
            print(f"✗ Model not found: {identifier}")
            return False

    def list_language_models(self) -> list[dict]:
        """List all configured language models.

        Returns:
            List of model dictionaries
        """
        return self.config.get("language_models", [])

    def update_model_nickname(self, old_identifier: str, new_nickname: str) -> bool:
        """Update a model's nickname.

        Args:
            old_identifier: Current filename or nickname
            new_nickname: New nickname to set

        Returns:
            True if updated successfully, False if model not found

        Raises:
            ValueError: If new_nickname is already in use
        """
        # Check if new nickname is already in use
        for model in self.config.get("language_models", []):
            if model.get("nickname") == new_nickname:
                raise ValueError(
                    f"Nickname '{new_nickname}' is already in use by '{model.get('file_name')}'"
                )

        # Find and update the model
        for model in self.config.get("language_models", []):
            if (
                model.get("file_name") == old_identifier
                or model.get("nickname") == old_identifier
            ):
                old_nickname = model.get("nickname")
                model["nickname"] = new_nickname
                self._save_config()
                print(f"✓ Updated nickname: '{old_nickname}' → '{new_nickname}'")
                return True

        print(f"✗ Model not found: {old_identifier}")
        return False

    def update_model_parameters(self, identifier: str, parameters_billions: float) -> bool:
        """Update a model's parameter count.

        Args:
            identifier: Filename or nickname of the model
            parameters_billions: New parameter count in billions

        Returns:
            True if updated successfully, False if model not found
        """
        for model in self.config.get("language_models", []):
            if model.get("file_name") == identifier or model.get("nickname") == identifier:
                old_params = model.get("parameters_billions")
                model["parameters_billions"] = parameters_billions
                self._save_config()
                print(
                    f"✓ Updated parameters for {identifier}: {old_params}B → {parameters_billions}B"
                )
                return True

        print(f"✗ Model not found: {identifier}")
        return False

    def get_model_directory(self, model_type: str = "language") -> str:
        """Get the directory path for a model type.

        Args:
            model_type: Type of model ('language' or 'voice')

        Returns:
            Absolute path to the model directory
        """
        return self.config["model_directories"].get(model_type, "")

    def update_model_directory(self, model_type: str, new_path: str) -> None:
        """Update the directory path for a model type.

        Args:
            model_type: Type of model ('language' or 'voice')
            new_path: New absolute path to the model directory
        """
        # Expand and normalize the path
        new_path = os.path.abspath(os.path.expanduser(new_path))

        if not os.path.exists(new_path):
            print(f"⚠ Warning: Directory does not exist: {new_path}")
            response = input("Create directory? [y/N]: ")
            if response.lower() == "y":
                os.makedirs(new_path, exist_ok=True)
                print(f"✓ Created directory: {new_path}")
            else:
                print("✗ Directory update cancelled")
                return

        if "model_directories" not in self.config:
            self.config["model_directories"] = {}

        old_path = self.config["model_directories"].get(model_type, "(not set)")
        self.config["model_directories"][model_type] = new_path
        self._save_config()

        print(f"✓ Updated {model_type} model directory:")
        print(f"  Old: {old_path}")
        print(f"  New: {new_path}")

    def auto_discover_models(
        self, model_type: str = "language", interactive: bool = True
    ) -> int:
        """Auto-discover models in the configured directory.

        Args:
            model_type: Type of model to discover ('language' or 'voice')
            interactive: If True, prompt for nickname and parameters for each model

        Returns:
            Number of models discovered and added
        """
        model_dir = Path(self.config["model_directories"].get(model_type, ""))

        if not model_dir.exists():
            print(f"✗ Model directory does not exist: {model_dir}")
            return 0

        # Find .gguf files
        gguf_files = list(model_dir.glob("*.gguf"))

        if not gguf_files:
            print(f"No .gguf files found in {model_dir}")
            return 0

        # Get existing filenames
        existing_files = {
            model.get("file_name")
            for model in self.config.get(f"{model_type}_models", [])
        }

        # Filter to new files only
        new_files = [f for f in gguf_files if f.name not in existing_files]

        if not new_files:
            print(f"All models in {model_dir} are already configured.")
            return 0

        print(f"\nFound {len(new_files)} new model(s):")
        added_count = 0

        for model_file in new_files:
            print(f"\n  File: {model_file.name}")

            if interactive:
                # Prompt for nickname
                default_nickname = (
                    model_file.stem.lower().replace("_", "-").replace(" ", "-")
                )
                nickname = (
                    input(f"  Nickname [{default_nickname}]: ").strip() or default_nickname
                )

                # Try to extract parameters from filename
                import re

                params_match = re.match(r"(\d+(?:\.\d+)?)B", model_file.name, re.IGNORECASE)
                default_params = float(params_match.group(1)) if params_match else None

                params_prompt = (
                    f"  Parameters (billions) [{default_params}]: "
                    if default_params
                    else "  Parameters (billions): "
                )
                params_input = input(params_prompt).strip()

                if params_input:
                    try:
                        params = float(params_input)
                    except ValueError:
                        print("  Invalid number, skipping model")
                        continue
                elif default_params is not None:
                    params = default_params
                else:
                    print("  No parameters specified, skipping model")
                    continue

            else:
                # Auto-generate nickname and extract params
                nickname = model_file.stem.lower().replace("_", "-").replace(" ", "-")
                import re

                params_match = re.match(r"(\d+(?:\.\d+)?)B", model_file.name, re.IGNORECASE)
                if not params_match:
                    print(f"  ✗ Could not extract parameters from filename, skipping")
                    continue
                params = float(params_match.group(1))

            # Add the model
            try:
                self.add_language_model(
                    file_name=model_file.name,
                    nickname=nickname,
                    parameters_billions=params,
                    check_exists=False,  # We already know it exists
                )
                added_count += 1
            except ValueError as exc:
                print(f"  ✗ Error: {exc}")

        return added_count


# Module-level convenience functions
def add_model(
    file_name: str, nickname: str, parameters_billions: float, check_exists: bool = True
) -> bool:
    """Add a language model to the configuration.

    Args:
        file_name: The model filename
        nickname: A short nickname for easy reference
        parameters_billions: Model size in billions of parameters
        check_exists: If True, verify the file exists before adding

    Returns:
        True if added successfully, False if already exists
    """
    manager = ConfigManager()
    return manager.add_language_model(file_name, nickname, parameters_billions, check_exists)


def remove_model(identifier: str) -> bool:
    """Remove a language model from the configuration.

    Args:
        identifier: Either the filename or nickname of the model

    Returns:
        True if removed successfully, False if not found
    """
    manager = ConfigManager()
    return manager.remove_language_model(identifier)


def list_models() -> list[dict]:
    """List all configured language models.

    Returns:
        List of model dictionaries
    """
    manager = ConfigManager()
    return manager.list_language_models()


def update_nickname(old_identifier: str, new_nickname: str) -> bool:
    """Update a model's nickname.

    Args:
        old_identifier: Current filename or nickname
        new_nickname: New nickname to set

    Returns:
        True if updated successfully, False if not found
    """
    manager = ConfigManager()
    return manager.update_model_nickname(old_identifier, new_nickname)
