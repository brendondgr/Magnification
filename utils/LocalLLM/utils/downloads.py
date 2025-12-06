"""Download utilities for LocalLMM."""

import os
import zipfile

import requests

from utils.LocalLLM.utils.logger import NoOpLogger


class DownloadProcessor:
    def __init__(self, logger=None) -> None:
        self.logger = logger if logger is not None else NoOpLogger()

    def download_and_extract_zip(self, url: str, extract_to_folder: str) -> None:
        local_zip_path = "temp.zip"
        try:
            self.logger.info(f"Downloading from {url}...")
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(local_zip_path, "wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        file_handle.write(chunk)

            self.logger.info(f"Extracting to {extract_to_folder}...")
            with zipfile.ZipFile(local_zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_to_folder)
            self.logger.info(f"Successfully downloaded and extracted to {extract_to_folder}")

        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Error downloading the file: {exc}")
            raise
        except zipfile.BadZipFile:
            self.logger.error("The downloaded file is not a valid zip file.")
            raise
        except Exception as exc:  # noqa: BLE001 - keep broad for logging parity
            self.logger.error(f"An unexpected error occurred: {exc}")
            raise
        finally:
            if os.path.exists(local_zip_path):
                os.remove(local_zip_path)
