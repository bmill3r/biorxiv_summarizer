#!/usr/bin/env python3
"""
PDF Processor Package

This package provides functionality to:
1. Extract text from PDF files
2. Generate summaries of the extracted text using OpenAI API
3. Save both the extracted text and summaries to files
"""

__version__ = "0.1.0"

from .pdf_processor import PDFProcessor
