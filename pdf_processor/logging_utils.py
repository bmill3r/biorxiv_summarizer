#!/usr/bin/env python3
"""
Logging utility functions for the PDF Processor package.
"""

import logging
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform colored terminal output
colorama.init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored log messages"""
    
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }
    
    def format(self, record):
        log_message = super().format(record)
        return f"{self.COLORS.get(record.levelname, '')}{log_message}{Style.RESET_ALL}"


def setup_logging(logger_name, log_level):
    """Configure logging with the specified name and level.
    
    Args:
        logger_name (str): Name for the logger
        log_level (int): Logging level (e.g., logging.DEBUG, logging.INFO)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Get the logger
    logger = logging.getLogger(logger_name)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Set log level
    logger.setLevel(log_level)
    
    # Create console handler and set level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = ColoredFormatter('%(message)s')
    
    # Add formatter to handler
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Log the configuration
    logger.info(f"{Fore.CYAN}PDF Processor{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    
    # Log verbose mode if enabled
    if log_level == logging.DEBUG:
        logger.debug("Verbose logging enabled")
    
    return logger
