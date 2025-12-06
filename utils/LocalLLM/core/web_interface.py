"""Helper utilities for integrating LocalLMM with web front-ends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence


@dataclass
class WebArgs:
    """Default argument set used when launching LocalLMM via the web UI."""

    model: str
    host: str = "127.0.0.1"
    port: int = 8080
    cpu: bool = False
    gpu: bool = True
    server_only: bool = True
    threads: int = 0
    gpu_layers: int = 999
    logs: bool = False
    n_predict: int = 8192
    max_new_tokens: int = 8192
    context_size: int = 65536
    temperature: float = 0.7
    repeat_penalty: float = 1.1
    stop: Sequence[str] = field(default_factory=lambda: ["<|eot_id|>"])
    timeout: float = 30.0


def build_args(model_name: str, overrides: Optional[Dict[str, Any]] = None) -> WebArgs:
    """Create a :class:`WebArgs` instance for the provided *model_name*.

    Parameters
    ----------
    model_name:
        The file name of the GGUF model to launch. The models directory prefix
        is appended by the LocalLMM server manager, so only the relative file
        name is required here.
    overrides:
        Optional mapping of attribute names to values that should override the
        defaults defined on :class:`WebArgs`.

    Returns
    -------
    WebArgs
        The populated argument object suitable for passing to
        :class:`LocalLMM.core.application.LocalLMM`.
    """

    args = WebArgs(model=model_name)

    if overrides:
        for key, value in overrides.items():
            if hasattr(args, key):
                setattr(args, key, value)

    return args
