#!/usr/bin/env python3
"""
PDF Processor CLI

Main entry point for the PDF Processor package.
This script imports and runs the main function from the package.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from pdf_processor.cli import main

if __name__ == "__main__":
    main()
