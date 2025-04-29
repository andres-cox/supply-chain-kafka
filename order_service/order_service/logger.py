"""Logger module for logging messages."""

import sys

from loguru import logger

# Remove default handler
logger.remove()

# Add a new handler that logs INFO level messages to stderr
logger.add(
    sys.stderr,
    level="INFO",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    colorize=True,
    enqueue=True,
    catch=True,
    backtrace=True,
    diagnose=True,
)

# You can also add file logging or other configurations here if needed
# logger.add("file.log", rotation="1 MB")  # Example for file logging

# Export the logger for use in other modules
__all__ = ["logger"]
