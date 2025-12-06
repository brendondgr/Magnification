"""Command-line argument parsing for LocalLMM."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence


class CLIArgumentParser:
    """Build and parse CLI arguments for LocalLMM."""

    def __init__(self, argv: Optional[Sequence[str]] = None) -> None:
        self.parser = self._create_parser()
        self.args = self.parser.parse_args(argv)
        self._validate_args(self.args)

    def _create_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Run a farm of llama.cpp servers.")

        parser.add_argument(
            "--model",
            type=str,
            default="1.5B-DeepSeek-R1-Q6KL.gguf",
            help="Model filename or nickname from config.json (e.g., 'deepseek-1.5b' or '1.5B-DeepSeek-R1-Q6KL.gguf').",
        )
        parser.add_argument(
            "--host",
            type=str,
            default="127.0.0.1",
            help="Host address to bind the server to.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8080,
            help="Starting port number.",
        )

        compute_mode_group = parser.add_mutually_exclusive_group()
        compute_mode_group.add_argument(
            "--cpu",
            action="store_true",
            help="Force CPU mode even if a GPU is detected.",
        )
        compute_mode_group.add_argument(
            "--gpu",
            action="store_true",
            help="Force GPU mode regardless of detection.",
        )

        serving_mode_group = parser.add_mutually_exclusive_group()
        serving_mode_group.add_argument(
            "--server-only",
            action="store_true",
            help="Run the server in the background without an interactive prompt.",
        )
        serving_mode_group.add_argument(
            "--inference-only",
            action="store_true",
            help="Connect to an already running server instead of starting a new one.",
        )
        parser.add_argument(
            "--inference-port",
            type=int,
            default=None,
            help="Port number where an external LLM server is running. Required with --inference-only.",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=0,
            help="Number of CPU threads to dedicate to inference. Set to 0 to auto use cpu_count-2.",
        )
        parser.add_argument(
            "--gpu-layers",
            "-ngl",
            type=int,
            default=999,
            help="Number of layers to offload to GPU (GPU mode only).",
        )
        parser.add_argument("--logs", action="store_true", help="Enable server logging to the console.")
        parser.add_argument(
            "--n-predict",
            dest="n_predict",
            type=int,
            default=8192,
            help="Number of tokens to predict at once.",
        )
        parser.add_argument(
            "--token",
            "--max-new-tokens",
            dest="max_new_tokens",
            type=int,
            default=None,
            help="Maximum number of new tokens to generate.",
        )
        parser.add_argument(
            "--context",
            "--context-size",
            dest="context_size",
            type=int,
            default=32768,
            help="Context size for the model (default 32768).",
        )
        parser.add_argument(
            "--temperature",
            type=float,
            default=0.1,
            help="Adjust the randomness of the generated text.",
        )
        parser.add_argument(
            "--repeat-penalty",
            type=float,
            default=1.2,
            help="Penalty for repeating tokens.",
        )
        parser.add_argument(
            "--stop",
            type=str,
            action="append",
            default=["<|eot_id|>"],
            help="Specify a stop string. Can be provided multiple times.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=None,
            help="Timeout for server requests in seconds.",
        )
        parser.add_argument(
            "--kv-cache",
            type=str,
            choices=["none", "basic", "optimized", "full"],
            default="optimized",
            help="KV cache level: none (disabled), basic (minimal), optimized (balanced), full (maximum).",
        )
        parser.add_argument(
            "--session-id",
            type=str,
            default="default",
            help="Session ID for conversation memory (default: 'default').",
        )
        parser.add_argument(
            "--slot-id",
            type=int,
            default=0,
            help="Slot ID for server-side KV cache hints (default: 0).",
        )
        parser.add_argument(
            "--remember",
            action="store_true",
            default=True,
            help="Remember conversation context across requests (default: True).",
        )
        parser.add_argument(
            "--no-remember",
            action="store_false",
            dest="remember",
            help="Disable conversation memory.",
        )
        parser.add_argument(
            "--reset-session",
            action="store_true",
            help="Clear session memory before starting.",
        )
        parser.add_argument(
            "--clear-slot",
            type=int,
            default=None,
            help="Clear server-side slot (by ID) at startup. Optional.",
        )
        parser.add_argument(
            "--slot-save-path",
            type=str,
            default=None,
            help="Path to save/restore KV cache slots. Required for save_kv_cache/restore_kv_cache.",
        )

        return parser

    def get_args(self):
        return self.args

    def _validate_args(self, args) -> None:
        if getattr(args, "inference_only", False):
            if args.inference_port is None:
                self.parser.error("--inference-only requires --inference-port.")
            if getattr(args, "cpu", False) or getattr(args, "gpu", False):
                self.parser.error("--inference-only cannot be combined with --cpu or --gpu.")
        elif args.inference_port is not None:
            self.parser.error("--inference-port can only be used together with --inference-only.")
