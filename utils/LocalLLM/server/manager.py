"""Server manager orchestrating LocalLMM farms."""

from __future__ import annotations

import os

from utils.LocalLLM.utils.downloads import DownloadProcessor
from utils.LocalLLM.utils.farms import CPUFarm, GPUFarm
from utils.LocalLLM.utils.gpu_detection import GPUType, detect_gpu
from utils.LocalLLM.utils.logger import NoOpLogger
from utils.LocalLLM.utils.os_adapters import get_os_adapter


class ServerManager:
    def __init__(self, args, logger=None, interactive_callback=None) -> None:
        self.args = args
        self.logger = logger if logger is not None else NoOpLogger()
        self.farm = None
        self.os_adapter = get_os_adapter()
        self.interactive_callback = interactive_callback

        # Maintain backward compatibility with legacy args objects.
        if not hasattr(self.args, "cpu"):
            setattr(self.args, "cpu", False)
        if not hasattr(self.args, "gpu"):
            setattr(self.args, "gpu", False)
        if not hasattr(self.args, "threads"):
            setattr(self.args, "threads", 0)

        existing_instances = getattr(self.args, "instances", 1)
        if existing_instances not in (None, 1):
            self.logger.warning(
                f"Multi-instance configuration detected ({existing_instances}); enforcing single instance."
            )
        setattr(self.args, "instances", 1)

    def _resolve_thread_count(self) -> int:
        """Determine the thread count leaving two system threads free."""

        total_cpus = os.cpu_count() or 1
        reserve = 2 if total_cpus > 2 else max(0, total_cpus - 1)
        allowed = max(1, total_cpus - reserve)

        requested = getattr(self.args, "threads", 0) or 0
        if requested <= 0:
            self.logger.info(
                f"Auto-selecting {allowed} CPU threads (total={total_cpus}, reserved={reserve})."
            )
            return allowed

        if requested > allowed:
            self.logger.warning(
                f"Requested thread count {requested} exceeds allowed {allowed}; using {allowed}."
            )
            return allowed

        self.logger.info(f"Using {requested} CPU threads as requested.")
        return requested

    def _validate_cpu_args(self) -> None:
        if getattr(self.args, "gpu_layers", 999) != 999:
            self.logger.warning("--gpu-layers is ignored in CPU mode.")

        resolved_threads = self._resolve_thread_count()
        setattr(self.args, "threads", resolved_threads)

    def _validate_gpu_args(self) -> None:
        threads_value = getattr(self.args, "threads", 0) or 0
        if threads_value != 0:
            self.logger.error("--threads cannot be combined with --gpu mode.")
            raise ValueError("--threads cannot be used with --gpu mode.")

    def _create_farm(self) -> None:
        detected_capability = detect_gpu()

        if not getattr(self.args, "cpu", False) and not getattr(self.args, "gpu", False):
            if detected_capability is not GPUType.NONE:
                self.args.gpu = True
                self.logger.info(
                    f"GPU detected ({detected_capability.value}). Defaulting to GPU mode."
                )
            else:
                self.args.cpu = True
                self.logger.info("No GPU detected. Falling back to CPU mode.")
        elif getattr(self.args, "cpu", False) and detected_capability is not GPUType.NONE:
            self.logger.info(
                f"GPU detected ({detected_capability.value}), but CPU mode was explicitly selected."
            )
        elif getattr(self.args, "gpu", False) and detected_capability is GPUType.NONE:
            self.logger.warning("GPU mode selected but no GPU detected. Startup may fail.")

        if getattr(self.args, "cpu", False) and getattr(self.args, "gpu", False):
            self.logger.error("CPU and GPU modes cannot be enabled at the same time.")
            raise ValueError("CPU and GPU modes are mutually exclusive.")

        if self.args.cpu:
            self._validate_cpu_args()
            self.logger.info("Creating CPU farm")
            self.farm = CPUFarm(
                model_name=self.args.model,
                threads_per_instance=self.args.threads,
                host=self.args.host,
                base_port=self.args.port,
                n_predict=self.args.n_predict,
                max_new_tokens=self.args.max_new_tokens,
                context_size=self.args.context_size,
                temperature=self.args.temperature,
                repeat_penalty=self.args.repeat_penalty,
                stop=self.args.stop,
                logs=self.args.logs,
                kv_cache=getattr(self.args, "kv_cache", "optimized"),
                slot_save_path=getattr(self.args, "slot_save_path", None),
                logger=self.logger,
            )
        else:
            self._validate_gpu_args()
            self.logger.info("Creating GPU farm")
            self.farm = GPUFarm(
                model_name=self.args.model,
                n_gpu_layers=self.args.gpu_layers,
                host=self.args.host,
                base_port=self.args.port,
                n_predict=self.args.n_predict,
                max_new_tokens=self.args.max_new_tokens,
                context_size=self.args.context_size,
                temperature=self.args.temperature,
                repeat_penalty=self.args.repeat_penalty,
                stop=self.args.stop,
                logs=self.args.logs,
                kv_cache=getattr(self.args, "kv_cache", "optimized"),
                slot_save_path=getattr(self.args, "slot_save_path", None),
                logger=self.logger,
            )

    def run(self) -> None:
        self.logger.info("Cleaning up any lingering server processes...")
        self.os_adapter.cleanup_lingering_processes()

        dll_dir = "llama-dlls"
        if not os.path.exists(dll_dir):
            self.logger.info(f"'{dll_dir}' directory not found. Creating and downloading assets.")
            os.makedirs(dll_dir, exist_ok=True)
            downloader = DownloadProcessor(logger=self.logger)
            downloader.download_and_extract_zip(
                "https://github.com/ggml-org/llama.cpp/releases/download/b6699/llama-b6699-bin-win-vulkan-x64.zip",
                dll_dir,
            )

        try:
            self._create_farm()
            if not self.farm:
                return

            if self.args.server_only:
                self.logger.info(
                    f"Server-only mode is active. The server is running in the background on {self.args.host}:{self.args.port}."
                )
            else:
                # Use callback if provided (for session-aware interactive mode)
                if self.interactive_callback:
                    self.interactive_callback()
                else:
                    self.farm.interactive_mode()
                self.shutdown()
        except FileNotFoundError as exc:
            self.logger.error(f"Error: {exc}")
        except Exception as exc:  # noqa: BLE001 - preserve broad logging
            self.logger.error(f"An unexpected error occurred: {exc}")

    def shutdown(self) -> None:
        if self.farm:
            self.farm.stop_servers()
