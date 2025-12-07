"""
Logger Configuration Module
Centralized logging setup for the stock trading bot
"""
import glob
import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler


def setup_logging():
    """
    Configure logging with daily rotation and 10-day cleanup
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # create logs folder in the parent directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs (older than 10 days)
    cleanup_old_logs(log_dir, days=10)
    
    # Setup logger
    logger = logging.getLogger('stock_bot')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create file handler with daily rotation
    log_file = os.path.join(log_dir, 'stock_bot.log')
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=10,  # Keep 10 days of logs
        encoding='utf-8'
    )
    file_handler.suffix = '%Y-%m-%d'
    
    # Create console handler for critical errors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def cleanup_old_logs(log_dir, days=10):
    """
    Delete log files older than specified days
    
    Args:
        log_dir (str): Directory containing log files
        days (int): Number of days to keep logs (default: 10)
    """
    try:
        cutoff_time = time.time() - (days * 86400)  # 86400 seconds in a day
        log_pattern = os.path.join(log_dir, 'stock_bot.log*')
        
        for log_file in glob.glob(log_pattern):
            if os.path.isfile(log_file):
                file_time = os.path.getmtime(log_file)
                if file_time < cutoff_time:
                    os.remove(log_file)
                    # Use print here since logger isn't set up yet
                    print(f"Deleted old log file: {log_file}")
    except Exception as e:
        # Use print here since logger isn't set up yet
        print(f"Error cleaning up old logs: {e}")


def get_logger():
    """
    Get the configured logger instance
    
    Returns:
        logging.Logger: Logger instance for 'stock_bot'
    """
    return logging.getLogger('stock_bot')


# Initialize logging when module is imported
_logger = setup_logging()
