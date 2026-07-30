"""
Media manager module for handling temporary media files and safe cleanup.
"""

import contextlib
import logging
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class MediaManager:
    """Manages temporary media storage and lifecycle cleanup."""

    def __init__(self, media_dir: str = "./temp_media") -> None:
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def get_temp_path(self, filename: str) -> Path:
        """Constructs full path for a temporary media file."""
        return self.media_dir / filename

    @contextlib.asynccontextmanager
    async def temp_file_scope(self, filename: str) -> AsyncGenerator[Path, None]:
        """
        Async context manager providing temporary file path and ensuring cleanup.
        """
        file_path = self.get_temp_path(filename)
        try:
            yield file_path
        finally:
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.debug(f"Cleaned up temporary media file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {file_path}: {e}")

    def cleanup_all(self) -> None:
        """Cleans up all temporary files inside media directory on shutdown."""
        if self.media_dir.exists():
            for item in self.media_dir.glob("*"):
                if item.is_file():
                    try:
                        item.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to remove residue file {item}: {e}")