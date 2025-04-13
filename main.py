#!/usr/bin/env python3
"""
BioRxiv Summarizer

Main entry point for the BioRxiv Summarizer package.
This script imports and runs the main function from the package.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from biorxiv_summarizer.cli import main

if __name__ == "__main__":
    main()
