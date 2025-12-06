"""GPU detection helpers for LocalLMM."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from enum import Enum
from typing import Optional, Sequence


class GPUType(Enum):
    """Enumeration describing detected GPU capability."""

    NONE = "none"
    CUDA = "cuda"
    ROCM = "rocm"
    VULKAN = "vulkan"


def _command_path(command: str) -> Optional[str]:
    """Return a fully qualified executable path if it exists."""

    return shutil.which(command)


def _run_command(command: Sequence[str], timeout: float = 2.0) -> Optional[str]:
    """Execute command and return combined output when successful."""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError, OSError):
        return None

    if completed.returncode != 0:
        return None

    output = completed.stdout.strip() or completed.stderr.strip()
    return output if output else None


def _detect_cuda() -> bool:
    """Detect NVIDIA CUDA capable devices."""

    for command in ("nvidia-smi", "nvidia-smi.exe"):
        path = _command_path(command)
        if not path:
            continue

        # Query GPU count directly to avoid parsing verbose output.
        output = _run_command(
            [path, "--query-gpu=count", "--format=csv,noheader,nounits"],
            timeout=2.0,
        )
        if not output:
            continue

        counts = [line.strip() for line in output.splitlines() if line.strip()]
        try:
            if sum(int(value) for value in counts) > 0:
                return True
        except ValueError:
            return True

    cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_devices and cuda_devices not in {"", "-1"}:
        return True

    return False


def _detect_rocm() -> bool:
    """Detect AMD ROCm capable devices."""

    for command in ("rocm-smi", "rocm-smi.exe", "rocminfo"):
        path = _command_path(command)
        if not path:
            continue

        output = _run_command([path], timeout=3.0)
        if output:
            return True

    hip_devices = os.environ.get("HIP_VISIBLE_DEVICES")
    if hip_devices and hip_devices not in {"", "-1"}:
        return True

    return False


def _detect_vulkan() -> bool:
    """Detect Vulkan capable GPU devices."""

    command = _command_path("vulkaninfo")
    if not command:
        return False

    output = _run_command([command, "--summary"], timeout=3.0)
    return bool(output)


def detect_gpu() -> GPUType:
    """Detect GPU capability in priority order: CUDA > ROCm > Vulkan."""

    if sys.platform.startswith("win") or sys.platform.startswith("linux"):
        if _detect_cuda():
            return GPUType.CUDA
        if _detect_rocm():
            return GPUType.ROCM

    if _detect_vulkan():
        return GPUType.VULKAN

    return GPUType.NONE


def has_gpu() -> bool:
    """Return True when any GPU capability is detected."""

    return detect_gpu() is not GPUType.NONE
