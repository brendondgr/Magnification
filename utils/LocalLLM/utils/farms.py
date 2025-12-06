"""Server farm management helpers for LocalLMM."""

from __future__ import annotations

import atexit
import os
import subprocess
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import requests

from utils.LocalLLM.utils.config_loader import get_model_parameters, get_model_path
from utils.LocalLLM.utils.logger import NoOpLogger
from utils.LocalLLM.utils.os_adapters import get_os_adapter


class LlamaManager(ABC):
    def __init__(
        self,
        model_name,
        base_port,
        n_predict,
        temperature,
        repeat_penalty,
        stop,
        max_new_tokens=None,
        context_size=None,
        logs=False,
        kv_cache="optimized",
        slot_save_path=None,
        logger=None,
    ) -> None:
        self.logger = logger if logger is not None else NoOpLogger()
        
        # Use config loader to resolve model path (supports nicknames and filenames)
        try:
            self.model_path = get_model_path(model_name)
        except FileNotFoundError as exc:
            self.logger.error(f"Model lookup failed: {exc}")
            raise

        self.base_port = base_port
        self.n_predict = n_predict
        self.temperature = temperature
        self.repeat_penalty = repeat_penalty
        self.stop = stop
        self.max_new_tokens = max_new_tokens
        self.context_size = context_size
        self.kv_cache = kv_cache
        self.slot_save_path = slot_save_path
        self.processes = []
        self.ports = []
        self.logs = logs
        self.os_adapter = get_os_adapter()

    @abstractmethod
    def start_servers(self) -> None:
        """Start the target server configuration."""

    def stop_servers(self) -> None:
        self.logger.info("Stopping all llama server instances...")
        for process in self.processes:
            self.logger.info(f"Terminating process {process.pid}...")
            process.terminate()

        for process in self.processes:
            try:
                process.wait(timeout=5)
                self.logger.info(f"Process {process.pid} terminated.")
            except subprocess.TimeoutExpired:
                self.logger.warning(f"Process {process.pid} did not terminate in time. Killing it.")
                process.kill()
                try:
                    process.wait(timeout=5)
                    self.logger.info(f"Process {process.pid} killed.")
                except subprocess.TimeoutExpired:
                    self.logger.error(f"Failed to kill process {process.pid}.")

        self.processes = []
        self.logger.info("All instances stopped.")

    def _infer_single(
        self,
        port,
        text,
        temperature=None,
        top_k=40,
        top_p=0.9,
        min_p=0.05,
        n_predict=None,
    ):
        host = getattr(self, "host", "localhost")
        url = f"http://{host}:{port}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        
        # Use instance defaults if not specified
        effective_temperature = temperature if temperature is not None else self.temperature
        effective_n_predict_param = n_predict if n_predict is not None else self.n_predict
        
        payload = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
            "cache_prompt": True,
            "temperature": effective_temperature,
            "top_k": top_k,
            "top_p": top_p,
            "min_p": min_p,
        }

        # Prioritize max_new_tokens from WebArgs, then fall back to the n_predict parameter
        effective_n_predict = self.max_new_tokens if self.max_new_tokens is not None else effective_n_predict_param
        if effective_n_predict is not None:
            if effective_n_predict <= 0:
                payload["n_predict"] = -1
            else:
                payload["n_predict"] = effective_n_predict
        else:
            payload["n_predict"] = -1

        if self.context_size is not None:
            payload["ctx_size"] = self.context_size

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            json_response = response.json()
            res = json_response["choices"][0]["message"]["content"].strip()

            if "gpt-oss" in self.model_path.lower():
                if "<|message|>" in res:
                    res = res.split("<|message|>")[-1].strip()

            usage = json_response.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)

            duration = response.elapsed.total_seconds()
            tokens_per_second = completion_tokens / duration if duration > 0 else 0

            return f"Response: {res}\n[{completion_tokens} Tokens | {tokens_per_second:.2f} Tokens/s | Port: {port}]"
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"[Instance on Port {port}]: Error - {exc}")
            return f"[Instance on Port {port}]: Error - {exc}"

    def infer_all(self, text, n_predict=None, **kwargs):
        if n_predict is None:
            n_predict = self.n_predict
        with ThreadPoolExecutor(max_workers=len(self.ports)) as executor:
            futures = [executor.submit(self._infer_single, port, text, n_predict=n_predict, **kwargs) for port in self.ports]
            results = [future.result() for future in futures]
        return results

    def interactive_mode(self):
        self.logger.info("Entering interactive mode. Type 'exit' or 'quit' to stop.")

        # Try to get parameters from config first
        model_name = self.model_path.split("/")[-1]
        params = get_model_parameters(model_name)
        
        # Fallback to regex parsing if not in config
        if params is None:
            self.logger.warning(f"Model parameters not found in config for '{model_name}'. Attempting regex extraction from filename.")
            params_str = model_name.split("-")[0].replace("B", "").split("\\")[-1]
            try:
                params = float(params_str)
            except ValueError:
                params = None

        if params is not None:
            max_timeout = params * 10
            self.logger.info(
                f"Waiting up to {max_timeout:.1f}s for the model to load (params: {params}B)..."
            )
        else:
            max_timeout = 60.0
            self.logger.error(
                f"Failed to determine model parameters. Waiting up to {max_timeout}s for the model to load..."
            )
        
        # Import the function from server_health
        from utils.LocalLLM.utils.server_health import wait_for_model_ready
        
        # Poll the health endpoint until model is ready
        # Use self.host and first port from self.ports
        host = getattr(self, "host", "localhost")
        port = self.ports[0] if self.ports else self.base_port
        
        success = wait_for_model_ready(
            host,
            int(port),
            max_timeout=max_timeout,
            poll_interval=0.5,
            logger=self.logger,
        )
        
        if not success:
            self.logger.warning(
                f"Model may not be fully ready after {max_timeout}s. Proceeding with warmup anyway..."
            )

        self.logger.info("Performing initial warm-up inference...")
        warmup_results = self.infer_all("What is your favorite colors?", n_predict=128)
        for result in warmup_results:
            self.logger.info(result)
        self.logger.info("Warm-up inference complete.")

        while True:
            try:
                prompt = input("User: ")
                if prompt.lower() in ["exit", "quit"]:
                    break

                results = self.infer_all(prompt)
                for result in results:
                    self.logger.info(result)

            except (KeyboardInterrupt, EOFError):
                break
        self.logger.info("Exiting interactive mode.")


class CPUFarm(LlamaManager):
    def __init__(
        self,
        model_name,
        threads_per_instance,
        host,
        base_port,
        n_predict,
        temperature,
        repeat_penalty,
        stop,
        max_new_tokens=None,
        context_size=None,
        logs=False,
        kv_cache="optimized",
        slot_save_path=None,
        logger=None,
    ) -> None:
        super().__init__(
            model_name,
            base_port,
            n_predict,
            temperature,
            repeat_penalty,
            stop,
            max_new_tokens,
            context_size,
            logs,
            kv_cache,
            slot_save_path,
            logger,
        )
        self.threads_per_instance = threads_per_instance
        self.host = host
        self.ports = [self.base_port]

        self.start_servers()

    def start_servers(self) -> None:
        self.logger.info("Starting CPU llama server instance...")
        for index, port in enumerate(self.ports, start=1):
            run_config = self.os_adapter.get_server_run_config(
                model_path=self.model_path,
                host=self.host,
                port=port,
                threads_per_instance=self.threads_per_instance,
                n_predict=self.n_predict,
                temperature=self.temperature,
                repeat_penalty=self.repeat_penalty,
                gpu_layers=0,
                context_size=self.context_size,
                kv_cache=self.kv_cache,
                slot_save_path=self.slot_save_path,
            )
            command = run_config["command"]
            popen_kwargs = run_config["popen_kwargs"]

            try:
                if self.logs:
                    process = subprocess.Popen(command, **popen_kwargs)
                else:
                    popen_kwargs["stdout"] = subprocess.DEVNULL
                    popen_kwargs["stderr"] = subprocess.DEVNULL
                    process = subprocess.Popen(command, **popen_kwargs)
                self.processes.append(process)
                self.logger.info(
                    f"  - CPU Instance {index} started on port {port} with PID {process.pid}"
                )
            except (FileNotFoundError, OSError) as exc:
                self.logger.error(f"Failed to start server on port {port}: {exc}")
                self.logger.error(
                    "Please ensure 'llama-server.exe' is in the 'llama-dlls' directory and that you have the necessary permissions."
                )
                return


class GPUFarm(LlamaManager):
    def __init__(
        self,
        model_name,
        n_gpu_layers,
        host,
        base_port,
        n_predict,
        temperature,
        repeat_penalty,
        stop,
        max_new_tokens=None,
        context_size=None,
        logs=False,
        kv_cache="optimized",
        slot_save_path=None,
        logger=None,
    ) -> None:
        super().__init__(
            model_name,
            base_port,
            n_predict,
            temperature,
            repeat_penalty,
            stop,
            max_new_tokens,
            context_size,
            logs,
            kv_cache,
            slot_save_path,
            logger,
        )
        self.n_gpu_layers = n_gpu_layers
        self.host = host
        self.ports = [self.base_port]

        self.start_servers()

    def start_servers(self) -> None:
        self.logger.info("Starting GPU llama server instance...")
        port = self.ports[0]

        run_config = self.os_adapter.get_server_run_config(
            model_path=self.model_path,
            host=self.host,
            port=port,
            threads_per_instance=0,
            n_predict=self.n_predict,
            temperature=self.temperature,
            repeat_penalty=self.repeat_penalty,
            gpu_layers=self.n_gpu_layers,
            context_size=self.context_size,
            kv_cache=self.kv_cache,
            slot_save_path=self.slot_save_path,
        )
        command = run_config["command"]
        popen_kwargs = run_config["popen_kwargs"]

        try:
            if self.logs:
                process = subprocess.Popen(command, **popen_kwargs)
            else:
                popen_kwargs["stdout"] = subprocess.DEVNULL
                popen_kwargs["stderr"] = subprocess.DEVNULL
                process = subprocess.Popen(command, **popen_kwargs)
            self.processes.append(process)
            self.logger.info(f"  - GPU Instance started on port {port} with PID {process.pid}")
        except (FileNotFoundError, OSError) as exc:
            self.logger.error(f"Failed to start GPU server on port {port}: {exc}")
            self.logger.error(
                "Please ensure 'llama-server.exe' is in the 'llama-dlls' directory and that you have the necessary permissions."
            )
            return
