#!/usr/bin/env python3
"""
File utility functions for the BioRxiv Summarizer package.
"""

import os
import logging
from pathlib import Path
from colorama import Fore, Style

# Get logger
logger = logging.getLogger('biorxiv_summarizer')

def ensure_output_dir(output_dir: str) -> str:
    """
    Ensure the output directory exists and is writable.
    Handles path conversion for better cross-platform compatibility.
    
    Args:
        output_dir: Requested output directory path
        
    Returns:
        Validated output directory path
    """
    # Convert to Path object for better path handling
    path = Path(output_dir)
    
    # If it's an absolute path starting with / but not a full Windows path, make it relative
    # This fixes the issue with paths like "/papers" being interpreted as absolute from root
    if str(path).startswith('/') and not (len(str(path)) > 2 and str(path)[1] == ':'):
        path = Path('.') / str(path).lstrip('/')
        logger.warning(f"Converting absolute path to relative: {path}")
    
    try:
        # Create directory if it doesn't exist
        path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using output directory: {path}")
        
        # Test if directory is writable
        test_file = path / '.write_test'
        try:
            test_file.write_text('test')
            test_file.unlink()  # Remove test file
        except Exception as e:
            logger.error(f"Output directory is not writable: {e}")
            logger.warning("Falling back to current directory")
            return '.'
    except Exception as e:
        logger.error(f"Error creating output directory: {e}")
        logger.warning("Falling back to current directory")
        return '.'
    
    return str(path)
