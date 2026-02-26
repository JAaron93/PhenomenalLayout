"""File handling utilities."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

logger = logging.getLogger(__name__)


class FileHandler:
    """Handles file operations for the application."""

    def __init__(self) -> None:
        """Initialize file handler with directory paths and create required directories."""
        self.upload_dir: str = "uploads"
        self.download_dir: str = "downloads"
        self.temp_dir: str = "temp"

        # Create directories
        for directory in [self.upload_dir, self.download_dir, self.temp_dir]:
            os.makedirs(directory, exist_ok=True)

    def save_uploaded_file(self, file: Any) -> str:
        """Save uploaded file and return path."""
        try:
            # Validate file type
            original_name = getattr(file, "name", "unknown")
            if not self._is_valid_file_type(original_name):
                raise ValueError(f"Unsupported file type: {original_name}")

            # Generate unique filename
            file_id = str(uuid.uuid4())
            file_ext = Path(original_name).suffix
            # Sanitize file extension
            file_ext = file_ext.lower()[:10]  # Limit extension length
            filename = f"{file_id}{file_ext}"

            file_path = os.path.join(self.upload_dir, filename)

            # Save file
            if hasattr(file, "read"):
                # File-like object
                with open(file_path, "wb") as f:
                    content = file.read()
                    f.write(content)
            else:
                # Gradio file object
                shutil.copy2(file, file_path)

            logger.info(f"File saved: {filename}")
            return file_path

        except Exception as e:
            logger.error(f"File save error: {e}")
            raise

    def _is_valid_file_type(self, filename: str) -> bool:
        """Validate file type based on extension (PDF only)."""
        allowed_extensions = {".pdf"}
        file_ext = Path(filename).suffix.lower()
        return file_ext in allowed_extensions

    def save_upload_file(self, upload_file: UploadFile) -> str:
        """Save FastAPI UploadFile and ensure its underlying stream is closed."""
        file_path: Optional[str] = None
        try:
            file_id = str(uuid.uuid4())
            file_ext = Path(upload_file.filename).suffix
            filename = f"{file_id}{file_ext}"

            file_path = os.path.join(self.upload_dir, filename)

            # Write file contents
            with open(file_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)

            logger.info(f"Upload file saved: {filename}")
            return file_path

        except Exception as e:
            # Clean up partially written file if any error occurs
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            logger.error(f"Upload file save error: {e}")
            raise

        finally:
            # Ensure the UploadFile stream is closed to release resources
            try:
                upload_file.file.close()
            except Exception as close_err:
                logger.debug(f"Could not close upload file stream: {close_err}")

    def create_temp_file(self, suffix: str = "") -> str:
        """Create temporary file."""
        try:
            fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=self.temp_dir)
            os.close(fd)
            return temp_path
        except Exception as e:
            logger.error(f"Temp file creation error: {e}")
            raise

    def cleanup_file(self, file_path: str) -> bool:
        """Clean up file."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File cleaned up: {file_path}")
                return True
            return False
        except Exception as e:
            logger.warning(f"File cleanup error: {e}")
            return False

    def get_file_info(self, file_path: str) -> dict:
        """Get file information."""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            file_stat = os.stat(file_path)
            return {
                "path": file_path,
                "size": file_stat.st_size,
                "created": file_stat.st_ctime,
                "modified": file_stat.st_mtime,
                "is_dir": os.path.isdir(file_path),
            }
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            raise

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """Clean up old files in the temp directory."""
        cleanup_count = 0
        error_count = 0

        try:
            import time
            from pathlib import Path

            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for directory in [self.upload_dir, self.download_dir, self.temp_dir]:
                try:
                    dir_path = Path(directory)
                    if not dir_path.exists():
                        continue

                    for file_path in dir_path.glob("*"):
                        try:
                            if file_path.is_file():
                                file_age = current_time - file_path.stat().st_mtime
                                if file_age > max_age_seconds:
                                    file_path.unlink()
                                    cleanup_count += 1
                                    logger.info(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            error_count += 1
                            logger.warning(f"Failed to cleanup {file_path}: {e}")
                except Exception as e:
                    error_count += 1
                    logger.warning(f"Cleanup error in {directory}: {e}")

            if error_count > 0:
                logger.warning(f"Completed cleanup with {error_count} errors")

            return cleanup_count

        except Exception as e:
            logger.error(f"Unexpected error during cleanup: {e}")
            raise
