"""Logging utilities for LocalLMM."""

from contextlib import contextmanager
from datetime import datetime
import os

from loguru import logger
from tqdm import tqdm


class NoOpLogger:
    """A no-op logger used when logging is disabled."""

    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass

    def critical(self, message):
        pass

    @contextmanager
    def progress_bar(self, total, description=""):
        """Yield a tqdm progress bar that is compatible with the caller."""
        with tqdm(total=total, desc=description) as progress:
            yield progress


class LoggerWrapper:
    """Configure loguru sinks for LocalLMM runs."""

    def __init__(self, config=None, level="INFO"):
        """Configure loguru sinks using project settings."""
        self.config = config
        log_file = None

        if self.config is not None:
            log_dir = self.config.config["PATHS"]["logs"]
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = os.path.join(log_dir, f"{timestamp}_run.log")
        else:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = os.path.join(log_dir, f"{timestamp}_run.log")

        logger.remove()
        if log_file:
            logger.add(
                log_file,
                format="<green>{time:HH:mm:ss}</green> | {level} | {message}",
                level="DEBUG",
            )
        logger.add(
            lambda msg: print(msg, end=""),
            format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
            colorize=True,
            level=level,
            diagnose=True,
            filter=self._color_filter,
        )

    def _color_filter(self, record):
        if record["level"].name == "WARNING":
            record["extra"]["color"] = "<yellow>"
        elif record["level"].name in ["ERROR", "CRITICAL"]:
            record["extra"]["color"] = "<red>"
        else:
            record["extra"]["color"] = ""
        return True

    def debug(self, message):
        logger.debug(message)

    def info(self, message):
        logger.info(message)

    @contextmanager
    def progress_bar(self, total, description=""):
        with tqdm(total=total, desc=description) as progress:
            yield progress

    def warning(self, message):
        logger.warning(message)

    def error(self, message):
        logger.error(message)

    def critical(self, message):
        logger.critical(message)
