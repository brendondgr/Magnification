"""Server availability helpers for inference-only mode."""

from __future__ import annotations

import socket
import time
from typing import Optional, Sequence

import requests


_HEALTH_ENDPOINTS: Sequence[str] = ("/health", "/healthz", "/")


def _log_debug(logger: Optional[object], message: str) -> None:
    if logger and hasattr(logger, "debug"):
        logger.debug(message)


def _log_info(logger: Optional[object], message: str) -> None:
    if logger and hasattr(logger, "info"):
        logger.info(message)


def check_server_availability(
    host: str,
    port: int,
    *,
    timeout: float = 5.0,
    logger: Optional[object] = None,
) -> bool:
    """Return True if a server responds on the supplied host and port."""

    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        _log_debug(logger, f"Socket probe to {host}:{port} failed: {exc}")
        return False

    for endpoint in _HEALTH_ENDPOINTS:
        url = f"http://{host}:{port}{endpoint}"
        try:
            response = requests.get(url, timeout=timeout)
            _log_debug(
                logger,
                f"HTTP probe to {url} returned status {response.status_code}.",
            )
            return True
        except requests.exceptions.RequestException as exc:
            _log_debug(logger, f"HTTP probe to {url} failed: {exc}")
            continue

    return True


def wait_for_server(
    host: str,
    port: int,
    *,
    timeout: float = 5.0,
    max_attempts: int = 30,
    retry_delay: float = 1.0,
    logger: Optional[object] = None,
) -> bool:
    """Poll the target server until it becomes available or attempts are exhausted."""

    for attempt in range(1, max_attempts + 1):
        if check_server_availability(host, port, timeout=timeout, logger=logger):
            if attempt > 1:
                _log_info(
                    logger,
                    f"Server at {host}:{port} became available after {attempt} attempts.",
                )
            return True

        if attempt < max_attempts:
            _log_debug(
                logger,
                f"Server at {host}:{port} not yet available. Retrying in {retry_delay} seconds.",
            )
            time.sleep(retry_delay)

    _log_info(logger, f"Server at {host}:{port} did not respond after {max_attempts} attempts.")
    return False


def check_model_readiness(
    host: str,
    port: int,
    *,
    timeout: float = 5.0,
    logger: Optional[object] = None,
) -> bool:
    """Check if the model is ready by polling the /health endpoint.
    
    Returns True if the endpoint returns HTTP 200 with {"status": "ok"},
    False otherwise (including HTTP 503 which indicates the model is still loading).
    
    Args:
        host: Server host address
        port: Server port number
        timeout: Request timeout in seconds
        logger: Optional logger instance
        
    Returns:
        True if model is ready, False otherwise
    """
    # Try both /health and /v1/health endpoints
    health_endpoints = ["/health", "/v1/health"]
    
    for endpoint in health_endpoints:
        url = f"http://{host}:{port}{endpoint}"
        try:
            response = requests.get(url, timeout=timeout)
            
            # HTTP 200 with {"status": "ok"} means model is ready
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "ok":
                        _log_debug(logger, f"Model ready at {url}")
                        return True
                    else:
                        _log_debug(logger, f"Health endpoint responded but status is not 'ok': {data}")
                except Exception as exc:
                    _log_debug(logger, f"Failed to parse JSON from {url}: {exc}")
                    
            # HTTP 503 means model is still loading
            elif response.status_code == 503:
                _log_debug(logger, f"Model still loading at {url} (HTTP 503)")
                return False
            else:
                _log_debug(logger, f"Unexpected status code {response.status_code} from {url}")
                
        except requests.exceptions.RequestException as exc:
            _log_debug(logger, f"Health check to {url} failed: {exc}")
            continue
    
    return False


def wait_for_model_ready(
    host: str,
    port: int,
    *,
    max_timeout: float = 150.0,
    poll_interval: float = 0.5,
    logger: Optional[object] = None,
) -> bool:
    """Poll the health endpoint until the model is ready or timeout occurs.
    
    Continuously polls the /health endpoint every poll_interval seconds until:
    - The model returns HTTP 200 with {"status": "ok"} (success)
    - The max_timeout is reached (failure)
    
    Args:
        host: Server host address
        port: Server port number
        max_timeout: Maximum time to wait in seconds (e.g., params * 10)
        poll_interval: Time between polling attempts in seconds (default: 0.5)
        logger: Optional logger instance
        
    Returns:
        True if model became ready, False if timeout occurred
    """
    _log_info(logger, f"Waiting for model to be ready at {host}:{port} (timeout: {max_timeout}s)...")
    
    start_time = time.time()
    attempt = 0
    
    while True:
        attempt += 1
        elapsed = time.time() - start_time
        
        # Check if we've exceeded the timeout
        if elapsed >= max_timeout:
            _log_info(
                logger,
                f"Model readiness timeout after {elapsed:.1f}s ({attempt} attempts). "
                f"Model may still be loading."
            )
            return False
        
        # Check if model is ready
        if check_model_readiness(host, port, timeout=poll_interval, logger=logger):
            _log_info(
                logger,
                f"Model ready at {host}:{port} after {elapsed:.1f}s ({attempt} attempts)."
            )
            return True
        
        # Wait before next poll
        time.sleep(poll_interval)
