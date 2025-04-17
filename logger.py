import logging
import os
import sys
from datetime import datetime
from hourly_log_handler import HourlyRotatingFileHandler

def setup_logger(log_level=logging.INFO):
    """
    Set up and configure a logger for the application.
    Logger will create a new log file every hour.
    
    Args:
        log_level: Logging level (default: INFO)
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger('video_translator')
    
    # Check if logger already has handlers to avoid duplicate logs
    if logger.handlers:
        return logger
        
    logger.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Create hourly rotating file handler - store logs in project directory
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    file_handler = HourlyRotatingFileHandler(
        log_dir=log_dir,
        prefix="video_translator",
        suffix=".log",
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"Logger initialized. Log directory: {log_dir}")
    
    return logger

def get_logger():
    """
    Get the existing logger or create a new one if it doesn't exist.
    
    Returns:
        Logger instance
    """
    logger = logging.getLogger('video_translator')
    if not logger.handlers:
        return setup_logger()
    return logger
