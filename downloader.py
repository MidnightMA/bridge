"""Media downloader and temporary storage manager."""

import logging
import os
import uuid
from pathlib import Path
import aiofiles
import aiohttp

logger = logging.getLogger("bridge.downloader")


class Downloader:
    """Handles async media file downloads and temporary file cleanup."""

    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def download_file(
        self, url: str, session: aiohttp.ClientSession, file_extension: str
    ) -> Path:
        """Downloads a remote file asynchronously to the temporary directory.

        Args:
            url: Remote media URL.
            session: Active aiohttp ClientSession.
            file_extension: File extension (e.g. '.jpg', '.mp4').

        Returns:
            Path: Path to the downloaded file.
        """
        filename = f"{uuid.uuid4().hex}{file_extension}"
        file_path = self.temp_dir / filename

        logger.info(f"Downloading media file from '{url}' to '{file_path}'...")
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
            response.raise_for_status()
            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in response.content.iter_chunked(16384):
                    await f.write(chunk)

        logger.info(f"Successfully downloaded file: {file_path}")
        return file_path

    @staticmethod
    def cleanup_file(file_path: Path) -> None:
        """Removes temporary file safely."""
        try:
            if file_path and file_path.exists():
                os.remove(file_path)
                logger.debug(f"Removed temporary media file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {file_path}: {e}")