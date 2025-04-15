#!/usr/bin/env python3
"""
Command-line interface for the PDF Processor package.

This script provides a command-line interface to:
1. Extract text from PDF files
2. Generate summaries of the extracted text using OpenAI API
3. Save both the extracted text and summaries to files
"""

import os
import argparse
import logging
import colorama
from colorama import Fore, Style
from typing import Dict, Any, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Import package modules
from .pdf_processor import PDFProcessor
from .logging_utils import setup_logging

# Initialize colorama
colorama.init(autoreset=True)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process PDF files: extract text and generate summaries",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Input parameters
    input_group = parser.add_argument_group('Input Parameters')
    input_group.add_argument('--pdf', type=str, required=True,
                      help='Path to the PDF file to process')
    input_group.add_argument('--mode', type=str, choices=['extract', 'summarize', 'full'], default='full',
                      help='Processing mode: extract text only, summarize only, or full (both)')
    
    # Metadata parameters
    metadata_group = parser.add_argument_group('Metadata Parameters')
    metadata_group.add_argument('--title', type=str,
                         help='Title of the paper (optional)')
    metadata_group.add_argument('--authors', type=str,
                         help='Authors of the paper (optional)')
    metadata_group.add_argument('--abstract', type=str,
                         help='Abstract of the paper (optional)')
    metadata_group.add_argument('--journal', type=str,
                         help='Journal name (optional)')
    metadata_group.add_argument('--date', type=str,
                         help='Publication date (optional)')
    metadata_group.add_argument('--doi', type=str,
                         help='DOI of the paper (optional)')
    
    # Output parameters
    output_group = parser.add_argument_group('Output Parameters')
    output_group.add_argument('--output-dir', type=str, default='./output',
                        help='Directory to save extracted text and summaries')
    
    # Summary parameters
    summary_group = parser.add_argument_group('Summary Parameters')
    summary_group.add_argument('--openai-key', type=str,
                         help='OpenAI API key (can also be set as OPENAI_API_KEY environment variable)')
    summary_group.add_argument('--model', type=str, default='gpt-4o-mini',
                         help='OpenAI model to use for summarization')
    summary_group.add_argument('--temperature', type=float, default=0.2,
                         help='Temperature for OpenAI API (0.0-1.0)')
    summary_group.add_argument('--prompt', type=str,
                         help='Path to a file containing a custom prompt template')
    
    # Logging parameters
    logging_group = parser.add_argument_group('Logging Parameters')
    logging_group.add_argument('--verbose', action='store_true',
                         help='Enable verbose logging')
    
    return parser.parse_args()

def main():
    """Main function to run the PDF processor."""
    # Load environment variables from .env file
    load_dotenv()
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging('pdf_processor', log_level)
    
    # Check if PDF file exists
    if not os.path.exists(args.pdf):
        logger.error(f"{Fore.RED}Error: PDF file not found: {args.pdf}{Style.RESET_ALL}")
        return 1
    
    # Initialize metadata dictionary
    metadata = {}
    if args.title:
        metadata['title'] = args.title
    if args.authors:
        metadata['authors'] = args.authors
    if args.abstract:
        metadata['abstract'] = args.abstract
    if args.journal:
        metadata['journal'] = args.journal
    if args.date:
        metadata['date'] = args.date
    if args.doi:
        metadata['doi'] = args.doi
    
    # Initialize PDF processor
    try:
        processor = PDFProcessor(
            api_key=args.openai_key,
            custom_prompt_path=args.prompt,
            temperature=args.temperature,
            model=args.model,
            output_dir=args.output_dir
        )
    except ValueError as e:
        logger.error(f"{Fore.RED}Error initializing PDF processor: {e}{Style.RESET_ALL}")
        if args.mode in ['summarize', 'full']:
            logger.error("Make sure your OpenAI API key is set correctly.")
            logger.error("You can set it using the --openai-key argument or as the OPENAI_API_KEY environment variable.")
        return 1
    
    # Process the PDF
    logger.info(f"{Fore.BLUE}Processing PDF: {args.pdf} (Mode: {args.mode}){Style.RESET_ALL}")
    
    try:
        results = processor.process_pdf(
            pdf_path=args.pdf,
            mode=args.mode,
            metadata=metadata,
            output_dir=args.output_dir
        )
        
        # Check for errors
        if results.get('error'):
            logger.error(f"{Fore.RED}Error: {results['error']}{Style.RESET_ALL}")
            return 1
        
        # Print results
        if results.get('text_path'):
            logger.info(f"{Fore.GREEN}Extracted text saved to: {results['text_path']}{Style.RESET_ALL}")
        
        if results.get('summary_path'):
            logger.info(f"{Fore.GREEN}Summary saved to: {results['summary_path']}{Style.RESET_ALL}")
        
        logger.info(f"{Fore.GREEN}PDF processing completed successfully{Style.RESET_ALL}")
        return 0
        
    except Exception as e:
        logger.error(f"{Fore.RED}Error processing PDF: {e}{Style.RESET_ALL}")
        return 1

if __name__ == "__main__":
    exit(main())
