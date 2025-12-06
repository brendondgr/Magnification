"""Primary application interface for LocalLMM."""

from __future__ import annotations

import atexit
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import requests

from utils.LocalLLM.cli.argument_parser import CLIArgumentParser
from utils.LocalLLM.server.manager import ServerManager
from utils.LocalLLM.utils.config_loader import get_model_parameters
from utils.LocalLLM.utils.server_health import wait_for_server
from loguru import logger as global_logger


class LocalLMM:
    """High-level entry point that mirrors the legacy main_llm workflow."""

    def __init__(
        self,
        logger: Optional[object] = None,
        args: Optional[object] = None,
        *,
        cli_args: Optional[Sequence[str]] = None,
        use_cli: bool = False,
        inference_only_mode: Optional[bool] = None,
        inference_port: Optional[int] = None,
    ) -> None:
        self.logger = logger if logger is not None else global_logger
        self.logger.info("LocalLMM starting")

        if args is not None and (cli_args is not None or use_cli):
            raise ValueError("Provide either 'args' or CLI inputs, not both.")

        self.arg_parser = None
        if args is None:
            # When use_cli is False we bypass sys.argv to keep programmatic usage simple.
            effective_cli_args = None if use_cli else (cli_args if cli_args is not None else [])
            self.arg_parser = CLIArgumentParser(argv=effective_cli_args)
            self.args = self.arg_parser.get_args()
        else:
            self.args = args

        if not hasattr(self.args, "server_only"):
            setattr(self.args, "server_only", False)
        if not hasattr(self.args, "inference_only"):
            setattr(self.args, "inference_only", False)
        if not hasattr(self.args, "inference_port"):
            setattr(self.args, "inference_port", None)

        if inference_only_mode is not None:
            setattr(self.args, "inference_only", inference_only_mode)
        if inference_port is not None:
            setattr(self.args, "inference_port", inference_port)

        self.inference_only_mode = bool(getattr(self.args, "inference_only", False))
        self.inference_port = getattr(self.args, "inference_port", None)

        if self.inference_only_mode and getattr(self.args, "server_only", False):
            raise ValueError("'server_only' and 'inference_only' modes are mutually exclusive.")
        if self.inference_only_mode and self.inference_port is None:
            raise ValueError("'inference_port' must be provided when inference_only_mode is True.")

        if self.inference_only_mode:
            setattr(self.args, "server_only", False)
            self.logger.info(
                f"Inference-only mode enabled. Target server: {self.args.host}:{self.inference_port}."
            )

        self.logger.info(f"Arguments: {vars(self.args)}")

        self.manager = None
        if not self.inference_only_mode:
            self.manager = ServerManager(
                args=self.args,
                logger=self.logger,
                interactive_callback=self.interactive_mode,
            )
        self._model_load_wait_done = False
        # In-memory client-side sessions to carry prior turns between requests
        self._sessions: dict[str, list[dict]] = {}
        atexit.register(self.shutdown)

    def run(self) -> None:
        if self.inference_only_mode:
            timeout_value = getattr(self.args, "timeout", None) or 5.0
            if not wait_for_server(
                self.args.host,
                int(self.inference_port),
                timeout=timeout_value,
                max_attempts=3,
                retry_delay=1.0,
                logger=self.logger,
            ):
                message = (
                    f"No server found at {self.args.host}:{self.inference_port}. "
                    "Is the server running?"
                )
                self.logger.error(message)
                raise ConnectionError(message)

            self._model_load_wait_done = True
            return

        self.manager.run()
        # Only wait for model load in server-only mode; interactive mode handles its own wait
        if getattr(self.args, "server_only", False):
            self.wait_for_model_load()
        self._model_load_wait_done = True

    def refresh(self, args: Optional[object] = None, cli_args: Optional[Sequence[str]] = None) -> None:
        """Restart the server with new arguments.

        Args:
            args: Optional new arguments object.
            cli_args: Optional list of CLI arguments (e.g. ["--model", "foo"]).
        """
        if args is None and cli_args is None:
            self.logger.warning("refresh() called without any new arguments. Ignoring.")
            return

        self.logger.info("Refreshing LocalLMM with new arguments...")
        
        # Shutdown existing resources
        self.shutdown()

        # Update arguments
        # Priority: args > cli_args
        if args is not None:
            self.args = args
            # If we switched from CLI to object, we might want to clear the parser or just ignore it.
            # For consistency, we just replace self.args.
        elif cli_args is not None:
            # Re-parse CLI args
            self.arg_parser = CLIArgumentParser(argv=cli_args)
            self.args = self.arg_parser.get_args()

        # Re-validate/set defaults similar to __init__
        if not hasattr(self.args, "server_only"):
            setattr(self.args, "server_only", False)
        if not hasattr(self.args, "inference_only"):
            setattr(self.args, "inference_only", False)
        if not hasattr(self.args, "inference_port"):
            setattr(self.args, "inference_port", None)

        self.inference_only_mode = bool(getattr(self.args, "inference_only", False))
        self.inference_port = getattr(self.args, "inference_port", None)

        if self.inference_only_mode and getattr(self.args, "server_only", False):
            raise ValueError("'server_only' and 'inference_only' modes are mutually exclusive.")
        if self.inference_only_mode and self.inference_port is None:
            raise ValueError("'inference_port' must be provided when inference_only_mode is True.")

        if self.inference_only_mode:
            setattr(self.args, "server_only", False)
            self.logger.info(
                f"Inference-only mode enabled. Target server: {self.args.host}:{self.inference_port}."
            )

        self.logger.info(f"New Arguments: {vars(self.args)}")

        # Re-initialize manager if needed
        self.manager = None
        if not self.inference_only_mode:
            self.manager = ServerManager(
                args=self.args,
                logger=self.logger,
                interactive_callback=self.interactive_mode,
            )
        
        self._model_load_wait_done = False
        
        # Restart
        self.run()

    def trigger_inference(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        remember: bool = True,
        slot_id: int | None = None,
        cache_prompt: bool | None = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """Trigger inference with optional session memory and slot hints.

        - session_id: maintain a client-side conversation; previous turns are resent
        - remember: when True, store assistant reply into the session as context
        - slot_id/cache_prompt: forward to server if supported for KV reuse hints
        - stream: when True, yield tokens as they are generated
        """
        # Allow inference if model is loaded (via run() or interactive_mode)
        if not self._model_load_wait_done:
            self.logger.error("Model not loaded. Please call run() or interactive_mode() first.")
            return "Error: Model not loaded. Please call run() first."

        target_port = (
            int(self.inference_port)
            if self.inference_only_mode and self.inference_port is not None
            else int(self.args.port)
        )
        url = f"http://{self.args.host}:{target_port}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        
        # Use max_new_tokens if available, otherwise fall back to n_predict
        effective_n_predict = getattr(self.args, "max_new_tokens", None) or self.args.n_predict
        # Prepare messages: either session-accumulated or single turn
        if session_id:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            )
            messages = self._sessions[session_id]
        else:
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

        payload = {
            "messages": messages,
            "temperature": self.args.temperature,
            "n_predict": effective_n_predict,
            "stream": stream,
        }
        
        # Add optional parameters from WebArgs
        context_size = getattr(self.args, "context_size", None)
        if context_size is not None:
            payload["ctx_size"] = context_size
            
        repeat_penalty = getattr(self.args, "repeat_penalty", None)
        if repeat_penalty is not None:
            payload["repeat_penalty"] = repeat_penalty

        # Optional server-side slot hints (only include if provided)
        if slot_id is not None:
            payload["slot_id"] = int(slot_id)
            payload["cache_prompt"] = True if cache_prompt is None else bool(cache_prompt)
        elif cache_prompt is not None:
            payload["cache_prompt"] = bool(cache_prompt)

        try:
            if stream:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=getattr(self.args, "timeout", None),
                    stream=True,
                )
                response.raise_for_status()

                def streamer():
                    full_text = []
                    for line in response.iter_lines():
                        if line:
                            line = line.decode("utf-8")
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full_text.append(content)
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                    
                    # After streaming finishes, save to session if needed
                    if session_id and remember:
                        combined_text = "".join(full_text)
                        self._sessions[session_id].append(
                            {"role": "assistant", "content": [{"type": "text", "text": combined_text}]}
                        )

                return streamer()

            else:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=getattr(self.args, "timeout", None),
                )
                response.raise_for_status()
                json_response = response.json()
                text = json_response["choices"][0]["message"]["content"].strip()
                if session_id and remember:
                    self._sessions[session_id].append(
                        {"role": "assistant", "content": [{"type": "text", "text": text}]}
                    )
                return text
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Failed to connect to the server at {url}: {exc}")
            return f"Error: Failed to connect to server. Details: {exc}"

    def reset_session(self, session_id: str) -> None:
        """Clear stored client-side context for a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def clear_session(self, session_id: str, slot_id: int | None = None) -> bool:
        """Clear both client-side session and optionally server-side slot.

        Args:
            session_id: The session name to clear client-side
            slot_id: Optional server slot ID to clear

        Returns:
            True if at least one cleared successfully (or no-op but valid), False on error
        """
        try:
            # Clear client-side
            self.reset_session(session_id)
            self.logger.info(f"Cleared client-side session '{session_id}'")
            # Clear server-side slot if requested
            if slot_id is not None:
                ok = self.clear_slot(slot_id)
                if ok:
                    self.logger.info(f"Cleared server-side slot {slot_id}")
                return ok
            return True
        except Exception as exc:  # noqa: BLE001 - broad catch to log failures
            self.logger.error(f"Failed to clear session '{session_id}': {exc}")
            return False

    def interactive_mode(self) -> None:
        """Run interactive REPL with session memory."""
        if not self.manager or not self.manager.farm:
            self.logger.error("No farm available for interactive mode.")
            return

        self.logger.info("Entering interactive mode. Type 'exit' or 'quit' to stop.")
        
        # Wait for model to load
        model_name = os.path.basename(self.args.model)
        
        # Try to get parameters from config first
        params = get_model_parameters(model_name)
        
        # Fallback to regex parsing if not in config
        if params is None:
            params_match = re.match(r"(\d+(?:\.\d+)?)B-", model_name)
            if params_match:
                try:
                    params = float(params_match.group(1))
                except (ValueError, IndexError):
                    params = None
        
        # Import the function from server_health
        from utils.LocalLLM.utils.server_health import wait_for_model_ready
        
        # Calculate timeout: params * 10 seconds (or default 60s if params unknown)
        if params is not None:
            max_timeout = params * 10
            self.logger.info(
                f"Waiting up to {max_timeout:.1f}s for the model to load (params: {params}B)..."
            )
        else:
            max_timeout = 60.0
            self.logger.info(f"Waiting up to {max_timeout}s for model to load...")
        
        # Poll the health endpoint until model is ready
        success = wait_for_model_ready(
            self.args.host,
            int(self.args.port),
            max_timeout=max_timeout,
            poll_interval=0.5,
            logger=self.logger,
        )
        
        if not success:
            self.logger.warning(
                f"Model may not be fully ready after {max_timeout}s. Proceeding with warmup anyway..."
            )

        # Mark model as ready for inference within interactive mode
        self._model_load_wait_done = True

        # Get session settings from CLI args
        session_id = getattr(self.args, "session_id", "default")
        slot_id = getattr(self.args, "slot_id", 0)
        remember = getattr(self.args, "remember", True)
        
        # Reset session if requested
        if getattr(self.args, "reset_session", False):
            self.logger.info(f"Resetting session: {session_id}")
            self.reset_session(session_id)

        # Warmup inference
        self.logger.info("Performing initial warm-up inference...")
        warmup = self.trigger_inference(
            "What is your favorite color?",
            session_id=f"{session_id}_warmup",
            remember=False,
            slot_id=slot_id,
        )
        self.logger.info(f"Warmup: {warmup[:100]}...")
        self.logger.info("Warm-up complete.")

        # Interactive loop
        while True:
            try:
                prompt = input("User: ")
                if prompt.lower() in ["exit", "quit"]:
                    break

                # Handle simple REPL commands starting with '/'
                if prompt.startswith("/"):
                    command = prompt.lstrip("/").strip()
                    parts = command.split()
                    if parts[0].lower() in ("reset", "clear"):
                        # /reset [slot N]  -> clears session + optional slot
                        requested_slot = None
                        if len(parts) >= 2:
                            # Allow: /reset 1 or /reset slot 1
                            if parts[1].isdigit():
                                requested_slot = int(parts[1])
                            elif parts[1].lower() == "slot" and len(parts) >= 3 and parts[2].isdigit():
                                requested_slot = int(parts[2])
                        ok = self.clear_session(session_id, slot_id=requested_slot)
                        if ok:
                            self.logger.info(f"Session '{session_id}' cleared. Slot cleared: {requested_slot if requested_slot is not None else '(none)'}")
                        else:
                            self.logger.error(f"Failed to clear session '{session_id}'")
                        continue
                    elif parts[0].lower() in ("help", "commands"):
                        self.logger.info("Available REPL commands: /reset [slot N], /clear [slot N], /help, exit, quit")
                        continue

                response = self.trigger_inference(
                    prompt,
                    session_id=session_id,
                    remember=remember,
                    slot_id=slot_id,
                )
                self.logger.info(f"Response: {response}")

            except (KeyboardInterrupt, EOFError):
                break
        
        self.logger.info("Exiting interactive mode.")

    def clear_slot(self, slot_id: int = 0) -> bool:
        """Clear/release the KV cache for a specific slot.
        
        Args:
            slot_id: The slot ID to clear (default: 0)
            
        Returns:
            True if successful, False otherwise
        """
        # Allow slot clearing when model has been loaded in any mode or when in inference-only
        if not (self._model_load_wait_done or self.inference_only_mode or getattr(self.args, "server_only", False)):
            self.logger.error("clear_slot requires the model to be loaded or inference/server mode.")
            return False

        target_port = (
            int(self.inference_port)
            if self.inference_only_mode and self.inference_port is not None
            else int(self.args.port)
        )
        url = f"http://{self.args.host}:{target_port}/slots/{slot_id}?action=erase"
        
        try:
            response = requests.post(url, timeout=getattr(self.args, "timeout", None) or 5.0)
            response.raise_for_status()
            self.logger.info(f"Cleared KV cache for slot {slot_id}")
            return True
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Failed to clear slot {slot_id}: {exc}")
            return False

    def save_kv_cache(self, slot_id: int = 0, filepath: str | None = None) -> bool:
        """Save the KV cache from a specific slot to a file.
        
        This uses llama.cpp server's slot save functionality. The server must be
        started with --slot-save-path configured for this to work.
        
        Args:
            slot_id: The slot ID to save (default: 0)
            filepath: The filename to save the cache to (relative to server's slot-save-path).
                     If None, a default name based on slot_id will be used.
            
        Returns:
            True if successful, False otherwise
        """
        if not (self._model_load_wait_done or self.inference_only_mode or getattr(self.args, "server_only", False)):
            self.logger.error("save_kv_cache requires the model to be loaded or inference/server mode.")
            return False

        target_port = (
            int(self.inference_port)
            if self.inference_only_mode and self.inference_port is not None
            else int(self.args.port)
        )
        
        # Use default filename if not provided
        if filepath is None:
            filepath = f"slot_{slot_id}_cache"
        
        url = f"http://{self.args.host}:{target_port}/slots/{slot_id}?action=save"
        headers = {"Content-Type": "application/json"}
        payload = {"filename": filepath}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=getattr(self.args, "timeout", None) or 30.0)
            response.raise_for_status()
            self.logger.info(f"Saved KV cache for slot {slot_id} to '{filepath}'")
            return True
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Failed to save KV cache for slot {slot_id}: {exc}")
            return False

    def restore_kv_cache(self, slot_id: int = 0, filepath: str | None = None) -> bool:
        """Restore the KV cache from a file to a specific slot.
        
        This uses llama.cpp server's slot restore functionality. The server must be
        started with --slot-save-path configured for this to work.
        
        Args:
            slot_id: The slot ID to restore to (default: 0)
            filepath: The filename to restore from (relative to server's slot-save-path).
                     If None, a default name based on slot_id will be used.
            
        Returns:
            True if successful, False otherwise
        """
        if not (self._model_load_wait_done or self.inference_only_mode or getattr(self.args, "server_only", False)):
            self.logger.error("restore_kv_cache requires the model to be loaded or inference/server mode.")
            return False

        target_port = (
            int(self.inference_port)
            if self.inference_only_mode and self.inference_port is not None
            else int(self.args.port)
        )
        
        # Use default filename if not provided
        if filepath is None:
            filepath = f"slot_{slot_id}_cache"
        
        url = f"http://{self.args.host}:{target_port}/slots/{slot_id}?action=restore"
        headers = {"Content-Type": "application/json"}
        payload = {"filename": filepath}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=getattr(self.args, "timeout", None) or 30.0)
            response.raise_for_status()
            self.logger.info(f"Restored KV cache for slot {slot_id} from '{filepath}'")
            return True
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Failed to restore KV cache for slot {slot_id}: {exc}")
            return False

    def load_kv_cache(
        self,
        session_id: str,
        filepath: str,
        slot_id: int = 0,
    ) -> bool:
        """Load a saved KV cache into a session, clearing existing state first.
        
        This method performs two operations:
        1. Clears the existing client-side session and server-side slot
        2. Restores the KV cache from the specified file
        
        Args:
            session_id: The session name to reset before loading
            filepath: The filename to restore from (relative to server's slot-save-path,
                     without the .bin extension)
            slot_id: The slot ID to load into (default: 0)
            
        Returns:
            True if successful, False otherwise
            
        Example:
            >>> llm.load_kv_cache('demo', 'demo_session_cache', slot_id=0)
        """
        self.logger.info(f"Loading KV cache from '{filepath}' into session '{session_id}', slot {slot_id}")
        
        # Step 1: Clear existing session and slot
        clear_ok = self.clear_session(session_id, slot_id=slot_id)
        if not clear_ok:
            self.logger.warning(f"Failed to clear session '{session_id}' / slot {slot_id}, attempting restore anyway...")
        
        # Step 2: Restore the KV cache from file
        restore_ok = self.restore_kv_cache(slot_id=slot_id, filepath=filepath)
        if not restore_ok:
            self.logger.error(f"Failed to restore KV cache from '{filepath}'")
            return False
        
        self.logger.info(f"Successfully loaded KV cache from '{filepath}' into slot {slot_id}")
        return True

    def save_session(
        self,
        session_id: str,
        filepath: str,
        slot_id: int = 0,
    ) -> bool:
        """Save both session messages and KV cache to files.
        
        This saves:
        - Session messages to: {filepath}.session.json
        - KV cache to: {filepath} (via server's slot-save-path)
        
        Args:
            session_id: The session name to save
            filepath: Base filename (without extension) for the saved files
            slot_id: The slot ID to save KV cache from (default: 0)
            
        Returns:
            True if both saves succeeded, False otherwise
            
        Example:
            >>> llm.save_session('demo', 'cache/my_conversation', slot_id=0)
            # Creates: cache/my_conversation.session.json (messages)
            # Creates: <slot-save-path>/my_conversation.bin (KV cache)
        """
        self.logger.info(f"Saving session '{session_id}' to '{filepath}'")
        
        success = True
        
        # Step 1: Save session messages to JSON file
        session_file = f"{filepath}.session.json"
        if session_id in self._sessions:
            try:
                # Ensure directory exists
                Path(session_file).parent.mkdir(parents=True, exist_ok=True)
                
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(self._sessions[session_id], f, indent=2, ensure_ascii=False)
                self.logger.info(f"Saved {len(self._sessions[session_id])} messages to '{session_file}'")
            except Exception as exc:
                self.logger.error(f"Failed to save session messages: {exc}")
                success = False
        else:
            self.logger.warning(f"No session '{session_id}' found to save")
            success = False
        
        # Step 2: Save KV cache (uses just the base filename for the server)
        # Extract just the filename part for the KV cache
        cache_filename = Path(filepath).name
        kv_ok = self.save_kv_cache(slot_id=slot_id, filepath=cache_filename)
        if not kv_ok:
            self.logger.warning("KV cache save failed (server may not have --slot-save-path configured)")
            # Don't fail entirely if KV cache fails - session messages are more important
        
        return success

    def load_session(
        self,
        session_id: str,
        filepath: str,
        slot_id: int = 0,
    ) -> bool:
        """Load both session messages and KV cache from files.
        
        This loads:
        - Session messages from: {filepath}.session.json
        - KV cache from: {filepath} (via server's slot-save-path)
        
        The session is cleared before loading, and the slot is erased before
        restoring the KV cache.
        
        Args:
            session_id: The session name to load into
            filepath: Base filename (without extension) for the saved files
            slot_id: The slot ID to restore KV cache to (default: 0)
            
        Returns:
            True if session messages loaded successfully, False otherwise
            (KV cache restore failure is logged but doesn't fail the operation)
            
        Example:
            >>> llm.load_session('demo', 'cache/my_conversation', slot_id=0)
        """
        self.logger.info(f"Loading session '{session_id}' from '{filepath}'")
        
        # Step 1: Clear existing session and slot
        self.clear_session(session_id, slot_id=slot_id)
        
        # Step 2: Load session messages from JSON file
        session_file = f"{filepath}.session.json"
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                self._sessions[session_id] = json.load(f)
            self.logger.info(f"Loaded {len(self._sessions[session_id])} messages into session '{session_id}'")
        except FileNotFoundError:
            self.logger.error(f"Session file not found: {session_file}")
            return False
        except json.JSONDecodeError as exc:
            self.logger.error(f"Failed to parse session file: {exc}")
            return False
        except Exception as exc:
            self.logger.error(f"Failed to load session messages: {exc}")
            return False
        
        # Step 3: Restore KV cache (optional - for performance)
        cache_filename = Path(filepath).name
        kv_ok = self.restore_kv_cache(slot_id=slot_id, filepath=cache_filename)
        if kv_ok:
            self.logger.info(f"KV cache restored for faster inference")
        else:
            self.logger.info("KV cache not restored (will recompute on first inference)")
        
        return True

    def wait_for_model_load(self) -> None:
        model_name = os.path.basename(self.args.model)
        
        # Try to get parameters from config first
        params = get_model_parameters(model_name)
        
        # Fallback to regex parsing if not in config
        if params is None:
            self.logger.warning(
                f"Model parameters not found in config for '{model_name}'. Attempting regex extraction from filename."
            )
            match = re.match(r"(\d+(?:\.\d+)?)B-", model_name)
            if match:
                try:
                    params = float(match.group(1))
                except (ValueError, IndexError):
                    params = None
        
        # Import the function from server_health
        from utils.LocalLLM.utils.server_health import wait_for_model_ready
        
        # Calculate timeout: params * 10 seconds (or default 60s if params unknown)
        if params is not None:
            max_timeout = params * 10
            self.logger.info(
                f"Model: {model_name}. Parameters: {params}B. Waiting up to {max_timeout:.1f} seconds for the model to load."
            )
        else:
            max_timeout = 60.0
            self.logger.warning(
                f"Could not parse parameter count from model name: {model_name}. Using default timeout of {max_timeout}s."
            )
        
        # Poll the health endpoint until model is ready
        success = wait_for_model_ready(
            self.args.host,
            int(self.args.port),
            max_timeout=max_timeout,
            poll_interval=0.5,
            logger=self.logger,
        )
        
        if not success:
            self.logger.warning(
                f"Model may not be fully ready after {max_timeout}s. Proceeding anyway..."
            )

    def shutdown(self) -> None:
        """Gracefully shut down the application."""
        self.logger.info("LocalLMM shutting down.")
        if self.manager:
            self.manager.shutdown()
