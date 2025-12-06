"""Configuration file initializer for LocalLMM.

This module handles the initialization of the llm_config.json file.
If the config file doesn't exist, a blank one is created.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def ensure_config_exists(config_path: Optional[Path] = None) -> Path:
    """Ensure the llm_config.json file exists. If not, create a blank one.

    Args:
        config_path: Optional path to the config file. If None, uses default location.

    Returns:
        Path: The path to the config file.
    """
    if config_path is None:
        # Default location: LocalLMM/llm_config.json
        config_path = Path(__file__).parent.parent / "llm_config.json"
    else:
        config_path = Path(config_path)

    # Create parent directories if they don't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # If config doesn't exist, create a blank one
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)

    return config_path


def get_config_path(config_path: Optional[Path] = None) -> Path:
    """Get the path to the llm_config.json file, creating it if necessary.

    Args:
        config_path: Optional path to the config file. If None, auto-detects.

    Returns:
        Path: The path to the config file.
    """
    if config_path is None:
        # Try to find llm_config.json in the LocalLMM package directory
        current_dir = Path(__file__).parent.parent  # Go up from utils/ to LocalLMM/
        config_path = current_dir / "llm_config.json"

        if not config_path.exists():
            # Fallback: try relative to current working directory
            config_path = Path("LocalLMM/llm_config.json")

    return ensure_config_exists(config_path)
