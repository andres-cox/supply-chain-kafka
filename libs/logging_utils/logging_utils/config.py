"""Logging configuration module for all microservices."""

import sys
from typing import Optional

from loguru import logger as loguru_logger

def setup_service_logger(
    service_name: str,
    log_level: str = "INFO",
    log_file: Optional[str] = None,
) -> loguru_logger:
    """Configure a logger for a microservice with standardized settings.

    Args:
        service_name: Name of the service (e.g., 'order-service')
        log_level: Logging level (default: INFO)
        log_file: Optional path to log file

    Returns:
        logger: Configured loguru logger instance
    """
    # Remove any existing handlers
    loguru_logger.remove()
    
    # Add console handler with formatting
    loguru_logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
    
    # Add file handler if specified
    if log_file:
        loguru_logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="1 week",
            compression="gz",
        )
    
    # Set service name context
    configured_logger = loguru_logger.bind(service=service_name)
    
    return configured_logger

def get_kafka_logger(service_name: str) -> loguru_logger:
    """Get a logger specifically configured for Kafka operations.

    Args:
        service_name: Name of the service

    Returns:
        logger: Logger configured with Kafka context
    """
    return setup_service_logger(f"{service_name}.kafka")