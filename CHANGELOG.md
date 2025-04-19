# Changelog

All notable changes to the BioRxiv Summarizer project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- SSL connection issues with bioRxiv API
  - Added robust retry mechanism with exponential backoff
  - Implemented proper timeout handling for API requests
  - Added session persistence for better connection management
  - Added explicit dependency on urllib3 for retry functionality
  - Added `--disable-ssl-verify` option for troubleshooting SSL connection issues
  - Implemented fallback mechanism to scrape bioRxiv website directly when API connection fails
  - Added `--bypass-api` option to skip the API entirely and use web scraping directly
  - Reduced API retry attempts from 5 to 2 for faster fallback to web scraping

- PDF download improvements
  - Enhanced PDF URL construction with better paper ID extraction
  - Added support for paper IDs with decimal points and version numbers
  - Improved date extraction from paper IDs for better metadata
  - Fixed streaming download with chunked transfer for better memory efficiency

- Summary file path handling in Docker
  - Fixed issue with saving summary files when using Docker volume mounts
  - Added directory creation to ensure output paths exist
  - Improved error handling for file operations

- Date handling in paper summarizer
  - Fixed error when publication date is None during prompt template replacement
  - Added safe handling of missing or invalid dates in paper sorting

- PDF processor CLI import and function compatibility issues
  - Fixed incorrect relative import in pdf_processor/cli.py
  - Created a custom logging_utils.py module in the pdf_processor package with a compatible setup_logging function
  - Updated import to use the local module `from .logging_utils import setup_logging`
  - Fixed function signature mismatch (setup_logging now accepts logger_name and log_level parameters)

## [1.0.0] - 2025-04-15

### Added
- Initial release of BioRxiv Summarizer
- Search functionality for bioRxiv papers by topic and author
- PDF downloading and text extraction
- AI-powered paper summarization using OpenAI models
- Google Drive integration for saving papers and summaries
- Command-line interface with extensive options
- Comprehensive logging system
- Support for custom summarization prompts
- Multiple ranking options (date, downloads, views, Altmetric)

### Fixed
- Regex search issues with special characters in search terms (e.g., "RNA-seq")
  - Implemented proper regex escaping for search terms
  - Added fuzzy matching option for more flexible searching

- Output directory path handling
  - Fixed issues with absolute paths like "/papers" being interpreted incorrectly
  - Implemented path conversion for better cross-platform compatibility
  - Added directory writability testing to prevent silent failures

- Author name formatting
  - Fixed issue where author names were displayed as individual characters separated by commas
  - Implemented robust author name extraction and formatting
  - Added fallback methods for extracting author information from different metadata fields
  - Added regex-based cleanup for common formatting issues

- OpenAI model compatibility
  - Added support for multiple AI models (gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o)
  - Implemented model selection via command-line arguments
  - Added fallback mechanisms for when preferred models are unavailable

- Memory management improvements
  - Optimized PDF text extraction to reduce memory usage
  - Implemented chunking for large papers to prevent token limit issues
  - Added garbage collection to free memory during processing

## [0.9.0] - 2025-03-15

### Added
- Beta version with basic functionality
- Initial implementation of bioRxiv search
- Basic PDF downloading
- Simple summarization using OpenAI API
- Command-line interface with limited options

### Known Issues
- Issues with special characters in search terms
- Problems with absolute paths in output directory
- Inconsistent author name formatting
- Limited OpenAI model support
- Memory usage issues with large PDFs
