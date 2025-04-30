"""Logger module for logging messages."""

import os
from logging_utils.config import setup_service_logger

logger = setup_service_logger(
    "tracking-service",
    log_level=os.getenv("LOG_LEVEL", "INFO")
)