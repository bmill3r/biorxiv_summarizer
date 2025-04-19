#!/usr/bin/env python3
"""
Command-line interface for the BioRxiv Summarizer package.

This script provides a command-line interface to:
1. Search bioRxiv for the latest papers on a specified topic
2. Rank papers based on various metrics
3. Download the top papers as PDFs
4. Generate comprehensive summaries
5. Save both the papers and summaries to Google Drive
"""

import os
import argparse
import tempfile
import logging
import colorama
from typing import Dict, Any, List, Optional, Tuple
from colorama import Fore, Style

# Import package modules
from .searcher import BioRxivSearcher
from .summarizer import PaperSummarizer
from .uploader import GoogleDriveUploader
from .utils import setup_logging, ensure_output_dir

# Initialize colorama
colorama.init(autoreset=True)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Search bioRxiv for papers, download them, generate summaries, and upload to Google Drive",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Search parameters
    search_group = parser.add_argument_group('Search Parameters')
    search_group.add_argument('--topic', type=str, help='Topic to search for')
    search_group.add_argument('--topics', type=str, nargs='+', help='Multiple topics to search for')
    search_group.add_argument('--topic-match', type=str, choices=['all', 'any'], default='all',
                        help='For multiple topics: require all topics to match (AND) or any topic to match (OR)')
    search_group.add_argument('--author', type=str, help='Author name to search for')
    search_group.add_argument('--authors', type=str, nargs='+', help='Multiple author names to search for')
    search_group.add_argument('--author-match', type=str, choices=['all', 'any'], default='any',
                        help='For multiple authors: require all authors to match (AND) or any author to match (OR)')
    search_group.add_argument('--days', type=int, default=30,
                        help='Number of days to look back for papers')
    search_group.add_argument('--max-papers', type=int, default=5,
                        help='Maximum number of papers to process')
    search_group.add_argument('--fuzzy-match', action='store_true',
                        help='Use fuzzy matching for topics (matches partial words)')
    
    # Ranking parameters
    ranking_group = parser.add_argument_group('Ranking Parameters')
    ranking_group.add_argument('--rank-by', type=str, choices=['date', 'downloads', 'abstract_views', 'altmetric', 'combined'],
                         default='date', help='How to rank papers')
    ranking_group.add_argument('--rank-direction', type=str, choices=['asc', 'desc'],
                         default='desc', help='Sort direction (ascending or descending)')
    ranking_group.add_argument('--weight-downloads', type=float, default=0.4,
                         help='Weight for PDF downloads in combined ranking')
    ranking_group.add_argument('--weight-views', type=float, default=0.2,
                         help='Weight for abstract views in combined ranking')
    ranking_group.add_argument('--weight-altmetric', type=float, default=0.3,
                         help='Weight for Altmetric score in combined ranking')
    ranking_group.add_argument('--weight-twitter', type=float, default=0.1,
                         help='Weight for Twitter mentions in combined ranking')
    ranking_group.add_argument('--altmetric-key', type=str,
                         help='Altmetric API key for altmetric-based ranking')
    
    # Output parameters
    output_group = parser.add_argument_group('Output Parameters')
    output_group.add_argument('--output-dir', type=str, default='./papers',
                        help='Directory to save papers and summaries')
    
    # Summary parameters
    summary_group = parser.add_argument_group('Summary Parameters')
    summary_group.add_argument('--openai-key', type=str,
                         help='OpenAI API key (can also be set as OPENAI_API_KEY environment variable)')
    summary_group.add_argument('--model', type=str, default='gpt-4o-mini',
                         help='AI model to use for summarization')
    summary_group.add_argument('--temperature', type=float, default=0.2,
                         help='Temperature for API (0.0-1.0)')
    summary_group.add_argument('--prompt', type=str,
                         help='Path to a file containing a custom prompt template')
    summary_group.add_argument('--prompt-text', type=str,
                         help='Custom prompt text to use instead of a prompt file')
    summary_group.add_argument('--api-provider', type=str, choices=['openai', 'anthropic'], default='openai',
                         help='AI provider to use for summarization (openai or anthropic)')
    summary_group.add_argument('--anthropic-key', type=str,
                         help='Anthropic API key (can also be set as ANTHROPIC_API_KEY environment variable)')
    summary_group.add_argument('--max-response-tokens', type=int,
                         help='Maximum number of tokens for model responses (defaults to 3000 for OpenAI and 8000 for Claude)')
    
    # Google Drive parameters
    drive_group = parser.add_argument_group('Google Drive Parameters')
    drive_group.add_argument('--use-drive', action='store_true',
                       help='Upload papers and summaries to Google Drive')
    drive_group.add_argument('--credentials', type=str, default='credentials.json',
                       help='Path to Google Drive API credentials JSON file')
    drive_group.add_argument('--drive-folder', type=str,
                       help='Name of the Google Drive folder to upload to (will be created if it doesn\'t exist)')
    
    # Logging parameters
    logging_group = parser.add_argument_group('Logging Parameters')
    logging_group.add_argument('--verbose', action='store_true',
                         help='Enable verbose logging')
    logging_group.add_argument('--full-debug', action='store_true',
                         help='Enable full debug logging (including paper metadata)')
    logging_group.add_argument('--log-file', type=str,
                         help='Path to save log file')
    
    # Advanced parameters
    advanced_group = parser.add_argument_group('Advanced Parameters')
    advanced_group.add_argument('--disable-ssl-verify', action='store_true',
                         help='Disable SSL verification (not recommended for production use, only for troubleshooting)')
    advanced_group.add_argument('--bypass-api', action='store_true',
                         help='Bypass the bioRxiv API and use web scraping directly (useful when the API is down)')
    advanced_group.add_argument('--skip-prompt', action='store_true',
                         help='Skip prompt for existing PDFs')
    advanced_group.add_argument('--download-only', action='store_true',
                         help='Only download PDFs without generating summaries')
    advanced_group.add_argument('--max-pdf-pages', type=int, 
                         help='Maximum number of pages to extract from PDFs (default: all pages)')
    
    return parser.parse_args()

def initialize_components(args):
    """Initialize the main components needed for the workflow."""
    # Initialize searcher with Altmetric API key if provided
    searcher = BioRxivSearcher(
        altmetric_api_key=args.altmetric_key,
        verify_ssl=not args.disable_ssl_verify,
        bypass_api=args.bypass_api
    )
    
    # Set up weights for combined ranking
    rank_weights = {
        'pdf_downloads': args.weight_downloads,
        'abstract_views': args.weight_views,
        'altmetric_score': args.weight_altmetric,
        'twitter_count': args.weight_twitter
    }
    
    # Initialize summarizer
    temp_prompt_file = None
    if args.prompt_text:
        # Create a temporary file for the prompt text
        try:
            temp_fd, temp_prompt_file = tempfile.mkstemp(suffix='.md')
            with os.fdopen(temp_fd, 'w') as f:
                f.write(args.prompt_text)
            logger.info(f"Created temporary prompt file: {temp_prompt_file}")
            prompt_path = temp_prompt_file
        except Exception as e:
            logger.error(f"Error creating temporary prompt file: {e}")
            prompt_path = None
    else:
        prompt_path = args.prompt
    
    try:
        summarizer = PaperSummarizer(
            api_key=args.openai_key,
            custom_prompt_path=prompt_path,
            temperature=args.temperature,
            model=args.model,
            api_provider=args.api_provider,
            anthropic_api_key=args.anthropic_key,
            max_response_tokens=args.max_response_tokens
        )
    except ValueError as e:
        logger.error(f"{Fore.RED}Error initializing summarizer: {e}{Style.RESET_ALL}")
        if args.api_provider == 'openai':
            logger.error("Make sure your OpenAI API key is set correctly.")
            logger.error("You can set it using the --openai-key argument or as the OPENAI_API_KEY environment variable.")
        elif args.api_provider == 'anthropic':
            logger.error("Make sure your Anthropic API key is set correctly.")
            logger.error("You can set it using the --anthropic-key argument or as the ANTHROPIC_API_KEY environment variable.")
        return None, None, None, None, rank_weights, temp_prompt_file
    
    # Initialize Google Drive uploader if requested
    uploader = None
    drive_folder_id = None
    if args.use_drive:
        if not os.path.exists(args.credentials):
            logger.error(f"{Fore.RED}Google Drive credentials file not found: {args.credentials}{Style.RESET_ALL}")
            logger.error("Please provide a valid credentials file or disable Google Drive upload.")
        else:
            try:
                uploader = GoogleDriveUploader(args.credentials)
                
                # Create folder if specified
                if args.drive_folder:
                    drive_folder_id = uploader.create_folder(args.drive_folder)
                    if not drive_folder_id:
                        logger.error(f"{Fore.RED}Failed to create Google Drive folder: {args.drive_folder}{Style.RESET_ALL}")
                        uploader = None
            except Exception as e:
                logger.error(f"{Fore.RED}Error initializing Google Drive uploader: {e}{Style.RESET_ALL}")
                uploader = None
    
    return searcher, summarizer, uploader, drive_folder_id, rank_weights, temp_prompt_file

def search_papers_based_on_args(args, searcher, rank_weights):
    """Search for papers based on command-line arguments."""
    # Check if we have topics or authors to search for
    if not args.topic and not args.topics and not args.author and not args.authors:
        logger.error(f"{Fore.RED}Error: At least one search parameter (topic, topics, author, or authors) must be provided{Style.RESET_ALL}")
        return []
    
    # Prepare topics list
    topics = []
    if args.topic:
        topics.append(args.topic)
    if args.topics:
        topics.extend(args.topics)
    
    # Prepare authors list
    authors = []
    if args.author:
        authors.append(args.author)
    if args.authors:
        authors.extend(args.authors)
    
    # Search for papers
    papers = searcher.search_papers(
        topics=topics if topics else None,
        authors=authors if authors else None,
        topic_match=args.topic_match,
        author_match=args.author_match,
        max_results=args.max_papers,
        days_back=args.days,
        rank_by=args.rank_by,
        rank_direction=args.rank_direction,
        rank_weights=rank_weights,
        fuzzy_match=args.fuzzy_match
    )
    
    return papers

def process_papers(papers, args, summarizer, uploader=None, drive_folder_id=None):
    """Process each paper (download, summarize, upload)."""
    logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}Starting to process {len(papers)} papers{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    
    api_quota_exceeded = False  # Flag to track if we've hit API quota limits
    
    # Add a new CLI argument for skipping the prompt for existing PDFs
    skip_prompt = getattr(args, 'skip_prompt', False)
    
    for i, paper in enumerate(papers, 1):
        title = paper.get('title', 'Unknown')
        logger.info(f"\n{Fore.CYAN}Processing paper {i}/{len(papers)}: {title}{Style.RESET_ALL}")
        
        # Download paper
        searcher = BioRxivSearcher()  # Create a temporary instance just for downloading
        pdf_path = searcher.download_paper(paper, args.output_dir, skip_prompt)
        
        # Check if the paper was skipped
        if pdf_path and "|skipped" in pdf_path:
            # Extract the actual path
            pdf_path = pdf_path.split("|")[0]
            logger.info(f"{Fore.YELLOW}Skipping paper: {title}{Style.RESET_ALL}")
            continue
            
        if not pdf_path:
            logger.error(f"Failed to download paper: {title}")
            continue
        
        # Skip summarization if we've already hit quota limits or if download-only is specified
        if api_quota_exceeded or args.download_only:
            logger.info(f"Paper downloaded to: {pdf_path}")
            continue
            
        # Generate summary
        summary_result = summarizer.generate_summary(
            pdf_path, 
            paper, 
            max_pdf_pages=args.max_pdf_pages
        )
        
        # Check if the result is an error dictionary
        if isinstance(summary_result, dict) and 'error' in summary_result:
            error_type = summary_result.get('error')
            error_message = summary_result.get('message', 'Unknown error')
            
            # Handle quota exceeded errors specially
            if error_type in ['quota_exceeded', 'rate_limit']:
                api_quota_exceeded = True
                logger.error(f"{Fore.RED}API quota or rate limit exceeded. Will download remaining papers without generating summaries.{Style.RESET_ALL}")
                logger.error(f"Error details: {error_message}")
                logger.info(f"Paper downloaded to: {pdf_path}")
                continue
                
            # For other errors, create a simple error summary
            summary = f"# Summary could not be generated\n\n**Error:** {error_message}\n\nThe paper has been downloaded to: {pdf_path}"
        else:
            # No error, use the summary as is
            summary = summary_result
        
        # Save summary to a file with the same naming format as the PDF
        # Extract the filename without extension from pdf_path
        pdf_filename = os.path.basename(pdf_path)
        summary_filename = os.path.splitext(pdf_filename)[0] + ".md"
        summary_path = os.path.join(args.output_dir, summary_filename)
        
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            # Verify the file was actually created
            if os.path.exists(summary_path) and os.path.getsize(summary_path) > 0:
                logger.info(f"{Fore.GREEN}Saved summary to: {summary_path}{Style.RESET_ALL}")
            else:
                logger.warning(f"Summary file was created but appears to be empty or missing: {summary_path}")
        except Exception as e:
            logger.error(f"Error saving summary file: {e}")
            logger.error(f"Attempted to save to: {summary_path}")
            # Try saving to current directory as fallback
            fallback_path = os.path.join(os.path.abspath('.'), summary_filename)
            try:
                with open(fallback_path, 'w', encoding='utf-8') as f:
                    f.write(summary)
                logger.info(f"{Fore.GREEN}Saved summary to fallback location: {fallback_path}{Style.RESET_ALL}")
                summary_path = fallback_path  # Update path for Google Drive upload
            except Exception as e2:
                logger.error(f"Failed to save summary even to fallback location: {e2}")
        
        # Upload the paper and its summary to Google Drive if using Google Drive
        if uploader and drive_folder_id:
            uploader.upload_file(pdf_path, drive_folder_id)
            uploader.upload_file(summary_path, drive_folder_id)

def main():
    """Main function to run the workflow."""
    # Parse arguments
    args = parse_arguments()
    
    # Setup logging
    global logger
    logger = setup_logging(args)
    
    # Initialize components
    searcher, summarizer, uploader, drive_folder_id, rank_weights, temp_prompt_file = initialize_components(args)
    
    try:
        # Search for papers
        papers = search_papers_based_on_args(args, searcher, rank_weights)
        
        # Process papers
        if papers:
            process_papers(papers, args, summarizer, uploader, drive_folder_id)
        else:
            logger.warning("No papers found matching the criteria.")
        
        logger.info(f"\n{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}Workflow complete!{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
    
    finally:
        # Clean up temporary prompt file if created
        if temp_prompt_file and os.path.exists(temp_prompt_file):
            try:
                os.remove(temp_prompt_file)
                logger.info(f"Temporary prompt file removed: {temp_prompt_file}")
            except Exception as e:
                logger.warning(f"Could not remove temporary prompt file {temp_prompt_file}: {e}")

if __name__ == "__main__":
    main()
