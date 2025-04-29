import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Optional

def configure_logger(
    name: str,
    log_level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Base logger configuration for all services"""
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # JSON formatter for structured logging
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "service": "%(name)s", "level": "%(levelname)s", '
        '"message": "%(message)s", "module": "%(module)s", "lineno": %(lineno)d}'
    )
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler (if specified)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    return logger