#!/usr/bin/env python3
"""
Logging utility functions for the BioRxiv Summarizer package.
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


class PaperMetadataFilter(logging.Filter):
    """Filter out paper metadata debug messages when in verbose mode."""
    
    def filter(self, record):
        # Filter out certain verbose debug messages about paper metadata
        if record.levelno == logging.DEBUG and any(x in record.getMessage() for x in ['Paper keys:', 'Paper category:', 'Paper type:', 'Paper collection:', 'Paper tags:']):
            return False
        return True


def setup_logging(args):
    """Configure logging based on command-line arguments."""
    # Get the logger
    logger = logging.getLogger('biorxiv_summarizer')
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Set log level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Create console handler and set level
    console_handler = logging.StreamHandler()
    
    if args.verbose:
        console_handler.setLevel(logging.DEBUG)
        
        # Add filter to exclude certain debug messages if not in full debug mode
        if not args.full_debug:
            console_handler.addFilter(PaperMetadataFilter())
    else:
        console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = ColoredFormatter('%(message)s')
    
    # Add formatter to handler
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Log the configuration
    logger.info(f"{Fore.CYAN}BioRxiv Paper Summarizer{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    
    # Log verbose mode if enabled
    if args.verbose:
        logger.debug("Verbose logging enabled")
        if args.full_debug:
            logger.debug("Full debug mode enabled (including paper metadata)")
    
    return logger
