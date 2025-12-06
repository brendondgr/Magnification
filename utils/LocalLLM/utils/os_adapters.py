"""OS specific adapters for managing llama.cpp servers."""

from __future__ import annotations

import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union


class OsAdapter(ABC):
    @abstractmethod
    def get_server_run_config(
        self,
        model_path: str,
        host: str,
        port: int,
        threads_per_instance: int,
        n_predict: int,
        temperature: float,
        repeat_penalty: float,
        gpu_layers: Union[int, None] = None,
        context_size: int | None = None,
        kv_cache: str = "optimized",
        slot_save_path: str | None = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cleanup_lingering_processes(self) -> None:
        raise NotImplementedError

    def _build_common_command(
        self,
        base_command: List[str],
        model_path: str,
        host: str,
        port: int,
        threads_per_instance: int,
        n_predict: int,
        temperature: float,
        repeat_penalty: float,
        gpu_layers: Union[int, None] = None,
        context_size: int | None = None,
        kv_cache: str = "optimized",
        slot_save_path: str | None = None,
    ) -> List[str]:
        command = base_command + [
            "-m",
            model_path,
            "--host",
            host,
            "--port",
            str(port),
            "--jinja",
        ]

        if gpu_layers is not None:
            command.extend(["-ngl", str(gpu_layers)])

        if context_size is not None:
            command.extend(["-c", str(context_size)])

        if threads_per_instance != 0:
            command.extend(["-t", str(threads_per_instance)])

        command.extend(["-n", str(n_predict)])
        command.extend(["--temp", str(temperature)])
        command.extend(["--repeat-penalty", str(repeat_penalty)])

        if slot_save_path is not None:
            command.extend(["--slot-save-path", slot_save_path])

        return command


class UnixWineAdapter(OsAdapter):
    def get_server_run_config(
        self,
        model_path: str,
        host: str,
        port: int,
        threads_per_instance: int,
        n_predict: int,
        temperature: float,
        repeat_penalty: float,
        gpu_layers: Union[int, None] = None,
        context_size: int | None = None,
        kv_cache: str = "optimized",
        slot_save_path: str | None = None,
    ) -> Dict[str, Any]:
        base_command = ["wine", "llama-dlls/llama-server.exe"]
        command = self._build_common_command(
            base_command,
            model_path,
            host,
            port,
            threads_per_instance,
            n_predict,
            temperature,
            repeat_penalty,
            gpu_layers,
            context_size,
            kv_cache,
            slot_save_path,
        )
        return {"command": command, "popen_kwargs": {}}

    def cleanup_lingering_processes(self) -> None:
        try:
            subprocess.run(["pkill", "-f", "llama-server.exe"], check=False)
        except FileNotFoundError:
            pass


class WindowsNativeAdapter(OsAdapter):
    def get_server_run_config(
        self,
        model_path: str,
        host: str,
        port: int,
        threads_per_instance: int,
        n_predict: int,
        temperature: float,
        repeat_penalty: float,
        gpu_layers: Union[int, None] = None,
        context_size: int | None = None,
        kv_cache: str = "optimized",
        slot_save_path: str | None = None,
    ) -> Dict[str, Any]:
        base_command = ["llama-dlls/llama-server.exe"]
        command = self._build_common_command(
            base_command,
            model_path,
            host,
            port,
            threads_per_instance,
            n_predict,
            temperature,
            repeat_penalty,
            gpu_layers,
            context_size,
            kv_cache,
            slot_save_path,
        )
        return {
            "command": command,
            "popen_kwargs": {"creationflags": subprocess.CREATE_NO_WINDOW},
        }

    def cleanup_lingering_processes(self) -> None:
        subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe", "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def get_os_adapter() -> OsAdapter:
    if sys.platform in ["linux", "darwin"]:
        return UnixWineAdapter()
    if sys.platform == "win32":
        return WindowsNativeAdapter()
    raise NotImplementedError(f"Unsupported OS: {sys.platform}")
