#!/usr/bin/env python3
"""
BioRxiv Paper Summarizer and Google Drive Uploader

This script:
1. Searches bioRxiv for the latest papers on a specified topic
2. Ranks papers based on various metrics (downloads, views, Altmetric scores, etc.)
3. Downloads the top papers as PDFs
4. Generates comprehensive summaries for each paper including strengths, weaknesses and field impact
5. Saves both the papers and summaries to a specified Google Drive folder

Requirements:
- Python 3.6+
- Google Cloud project with Drive API enabled
- OAuth credentials for Google Drive API
- Altmetric API key (optional, for Altmetric-based ranking)

Dependencies:
pip install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib openai python-dotenv PyPDF2

Ranking Options:
- date: Sort by publication date (default)
- downloads: Sort by number of PDF downloads
- abstract_views: Sort by number of abstract views
- altmetric: Sort by Altmetric attention score
- combined: Use a weighted combination of metrics

Examples:
1. Basic search by date (most recent first):
   python biorxiv_summarizer.py --topic "CRISPR" --max_papers 3

2. Find the most downloaded papers on a topic:
   python biorxiv_summarizer.py --topic "genomics" --rank_by downloads --max_papers 3

3. Find papers with the highest social media impact:
   python biorxiv_summarizer.py --topic "COVID-19" --rank_by altmetric --altmetric_key YOUR_API_KEY

4. Use a custom weighted ranking:
   python biorxiv_summarizer.py --topic "neuroscience" --rank_by combined --altmetric_key YOUR_API_KEY \
       --weight_downloads 0.3 --weight_views 0.1 --weight_altmetric 0.5 --weight_twitter 0.1
"""

import os
import io
import re
import json
import time
import requests
import datetime
import logging
import colorama
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import argparse
from colorama import Fore, Style

# Google Drive API libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# PDF processing
import PyPDF2

# OpenAI for summaries (can be replaced with other AI APIs)
import openai
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize colorama for cross-platform colored terminal output
colorama.init(autoreset=True)

# Configure logging
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

# Create logger
logger = logging.getLogger('biorxiv_summarizer')
logger.setLevel(logging.INFO)

# Create console handler and set level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = ColoredFormatter('%(message)s')

# Add formatter to handler
console_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(console_handler)

# Define scopes for Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

class BioRxivSearcher:
    """Class to search and retrieve papers from bioRxiv."""
    
    def __init__(self, altmetric_api_key=None):
        """
        Initialize the bioRxiv searcher.
        
        Args:
            altmetric_api_key: API key for Altmetric (optional)
        """
        self.base_api_url = "https://api.biorxiv.org"
        self.altmetric_api_key = altmetric_api_key
        self.altmetric_base_url = "https://api.altmetric.com/v1"
    
    def _extract_searchable_text(self, paper: Dict[str, Any]) -> str:
        """Extract searchable text from a paper including title, abstract, authors, and category.
        
        Args:
            paper: Paper metadata dictionary
            
        Returns:
            String containing all searchable text from the paper
        """
        # Start with title and abstract
        searchable_text = paper.get('title', '') + ' ' + paper.get('abstract', '')
        
        # Add category/subject tags to searchable text with higher weight (repeat them)
        # bioRxiv uses 'category' field for the subject area
        category = paper.get('category', '')
        if category:
            # Add category multiple times to give it more weight in the search
            searchable_text += ' ' + category * 5  # Increased weight for categories
            if logger.level <= logging.DEBUG:
                logger.debug(f"Paper category: {category}")
        
        # Some papers might have 'type' or 'collection' fields that indicate the subject area
        paper_type = paper.get('type', '')
        if paper_type:
            searchable_text += ' ' + paper_type * 3
            if logger.level <= logging.DEBUG:
                logger.debug(f"Paper type: {paper_type}")
            
        collection = paper.get('collection', '')
        if collection:
            searchable_text += ' ' + collection * 3
            if logger.level <= logging.DEBUG:
                logger.debug(f"Paper collection: {collection}")
        
        # Add any other tags or keywords if available
        tags = paper.get('tags', [])
        if isinstance(tags, list) and tags:
            searchable_text += ' ' + ' '.join(tags) * 3
            if logger.level <= logging.DEBUG:
                logger.debug(f"Paper tags: {tags}")
        
        # Handle authors which could be in different formats
        authors = paper.get('authors', [])
        if authors:
            author_text = ''
            for author in authors:
                if isinstance(author, dict):
                    author_text += ' ' + author.get('name', '')
                elif isinstance(author, str):
                    author_text += ' ' + author
            searchable_text += ' ' + author_text
        
        # Only log paper keys in debug mode
        if logger.level <= logging.DEBUG:
            logger.debug(f"Paper keys: {list(paper.keys())}")
        
        return searchable_text
        
    def search_papers(self, 
                     topics: List[str] = None,
                     authors: List[str] = None,
                     topic_match: str = "all",
                     author_match: str = "any",
                     max_results: int = 5,
                     days_back: int = 30,
                     rank_by: str = 'date',
                     rank_direction: str = 'desc',
                     rank_weights: Dict[str, float] = None,
                     fuzzy_match: bool = False) -> List[Dict[str, Any]]:
        """
        Unified search method for bioRxiv papers with flexible filtering options.
        
        Args:
            topics: List of topics to search for (optional)
            authors: List of author names to search for (optional)
            topic_match: If "all", papers must match ALL topics; if "any", papers must match ANY topic
            author_match: If "all", papers must match ALL authors; if "any", papers must match ANY author
            max_results: Maximum number of papers to return
            days_back: Number of days to look back
            rank_by: How to rank papers ('date', 'downloads', 'abstract_views', 'altmetric', 'combined')
            rank_direction: 'asc' for ascending or 'desc' for descending
            rank_weights: Dictionary of weights for combined ranking
            
        Returns:
            List of paper details including metadata and metrics
        """
        # Validate that at least one search parameter is provided
        if not topics and not authors:
            logger.error("Error: At least one search parameter (topics or authors) must be provided")
            return []
            
        # Log search criteria
        search_criteria = []
        if topics:
            fuzzy_info = " with fuzzy matching" if fuzzy_match else ""
            search_criteria.append(f"topics: {', '.join(topics)} (Match {topic_match.upper()}{fuzzy_info})")
        if authors:
            search_criteria.append(f"authors: {', '.join(authors)} (Match {author_match.upper()})")
            
        logger.info(f"{Fore.CYAN}Searching for recent papers matching {' AND '.join(search_criteria)}{Style.RESET_ALL}")
        logger.debug(f"Date range: {(datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')} to {datetime.datetime.now().strftime('%Y-%m-%d')}")
        
        # Calculate date range
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # Structure the API request URL
        details_url = f"{self.base_api_url}/details/biorxiv/{start_date}/{end_date}/0"
        
        try:
            # Fetch papers for the date range
            response = requests.get(details_url)
            response.raise_for_status()
            data = response.json()
            
            if 'collection' not in data or not data['collection']:
                logger.warning(f"No papers found for the date range {start_date} to {end_date}")
                return []
                
            # Filter papers based on topics and authors
            matching_papers = []
            for paper in data['collection']:
                matches_topic_criteria = False
                matches_author_criteria = False
                
                # If no topics specified, automatically match topic criteria
                if not topics:
                    matches_topic_criteria = True
                else:
                    # Get searchable text for topic matching
                    searchable_text = self._extract_searchable_text(paper)
                    
                    # Check if paper matches topics based on topic_match setting
                    topics_matched = []
                    for topic in topics:
                        # Handle fuzzy matching if enabled
                        if fuzzy_match:
                            # For fuzzy matching, we'll look for each word in the topic separately
                            # and consider it a match if most words are found
                            words = topic.lower().split()
                            words_matched = 0
                            
                            # Count how many words from the topic are found in the searchable text
                            for word in words:
                                # Skip very short words (less than 3 characters)
                                if len(word) < 3:
                                    words_matched += 1
                                    continue
                                    
                                # Remove special characters for matching
                                clean_word = re.sub(r'[^\w\s]', '.', word)
                                if re.search(clean_word, searchable_text.lower()):
                                    words_matched += 1
                            
                            # Consider it a match if at least 70% of the words match
                            match_threshold = 0.7
                            if words and (words_matched / len(words) >= match_threshold):
                                topics_matched.append(topic)
                                if logger.level <= logging.DEBUG:
                                    logger.debug(f"Fuzzy matched topic '{topic}' with {words_matched}/{len(words)} words")
                        else:
                            # Standard exact matching with regex escape
                            escaped_topic = re.escape(topic)
                            if re.search(escaped_topic, searchable_text, re.IGNORECASE):
                                topics_matched.append(topic)
                    
                    if topic_match == "all" and len(topics_matched) == len(topics):
                        # Paper matches ALL topics
                        paper['matched_topics'] = topics_matched
                        matches_topic_criteria = True
                    elif topic_match == "any" and topics_matched:
                        # Paper matches ANY topic
                        paper['matched_topics'] = topics_matched
                        matches_topic_criteria = True
                
                # If no authors specified, automatically match author criteria
                if not authors:
                    matches_author_criteria = True
                else:
                    # Get author information
                    paper_authors = paper.get('authors', [])
                    author_names = []
                    
                    # Extract author names from different possible formats
                    for author in paper_authors:
                        if isinstance(author, dict):
                            author_name = author.get('name', '')
                            if author_name:
                                author_names.append(author_name.lower())
                        elif isinstance(author, str):
                            author_names.append(author.lower())
                    
                    # Check if paper matches authors based on author_match setting
                    authors_matched = []
                    for search_author in authors:
                        search_author_lower = search_author.lower()
                        for author_name in author_names:
                            if search_author_lower in author_name:
                                authors_matched.append(search_author)
                                break
                    
                    if author_match == "all" and len(authors_matched) == len(authors):
                        # Paper matches ALL authors
                        paper['matched_authors'] = authors_matched
                        matches_author_criteria = True
                    elif author_match == "any" and authors_matched:
                        # Paper matches ANY author
                        paper['matched_authors'] = authors_matched
                        matches_author_criteria = True
                
                # Add paper if it matches both topic and author criteria
                if matches_topic_criteria and matches_author_criteria:
                    matching_papers.append(paper)
            
            # Prepare message about search criteria
            matches_all = "specified criteria"
            fuzzy_info = " (with fuzzy matching)" if fuzzy_match else ""
            
            if matching_papers:
                logger.info(f"{Fore.GREEN}Found {len(matching_papers)} papers matching {matches_all}{fuzzy_info}{Style.RESET_ALL}")
                # Only show paper categories in a summary instead of for each paper
                if len(matching_papers) > 0 and not logger.isEnabledFor(logging.DEBUG):
                    categories = set(paper.get('category', '') for paper in matching_papers if paper.get('category'))
                    if categories:
                        logger.info(f"Paper categories found: {', '.join(categories)}")
            else:
                logger.warning(f"No papers found matching {matches_all}{fuzzy_info}")
            
            # Early return if no papers found
            if not matching_papers:
                return []
                
            # Fetch metrics for matching papers if needed for ranking
            if rank_by in ['downloads', 'abstract_views', 'altmetric', 'combined']:
                matching_papers = self._fetch_paper_metrics(matching_papers)
            
            # Sort papers based on ranking method
            sorted_papers = self._sort_papers(matching_papers, rank_by, rank_direction, rank_weights)
            
            # Return the top papers based on max_results
            return sorted_papers[:max_results]
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching bioRxiv: {e}")
            return []
    
    def search_multi_topic_papers(self, topics: List[str], require_all: bool = True, max_results: int = 5,
                            days_back: int = 30, rank_by: str = 'date', 
                            rank_direction: str = 'desc',
                            rank_weights: Dict[str, float] = None,
                            fuzzy_match: bool = False) -> List[Dict[str, Any]]:
        """
        Search for recent papers matching multiple topics with ranking options.
        
        Args:
            topics: List of search topics
            require_all: If True, papers must match ALL topics; if False, papers must match ANY topic
            max_results: Maximum number of papers to return
            days_back: Number of days to look back
            rank_by: How to rank papers - options: 'date', 'downloads', 'abstract_views', 
                    'altmetric', 'combined' (default: 'date')
            rank_direction: 'asc' for ascending or 'desc' for descending (default: 'desc')
            rank_weights: Dictionary of weights for combined ranking (default weights if None)
            
        Returns:
            List of paper details including metadata and metrics
        """
        topic_match = "all" if require_all else "any"
        return self.search_papers(
            topics=topics,
            topic_match=topic_match,
            max_results=max_results,
            days_back=days_back,
            rank_by=rank_by,
            rank_direction=rank_direction,
            rank_weights=rank_weights,
            fuzzy_match=fuzzy_match
        )
        
    def search_by_authors(self, authors: List[str], require_all: bool = False, max_results: int = 5,
                        days_back: int = 30, rank_by: str = 'date', rank_direction: str = 'desc',
                        rank_weights: Dict[str, float] = None,
                        fuzzy_match: bool = False) -> List[Dict[str, Any]]:
        """
        Search for recent papers by specific authors with ranking options.
        
        Args:
            authors: List of author names to search for
            require_all: If True, papers must match ALL authors; if False, papers must match ANY author
            max_results: Maximum number of papers to return
            days_back: Number of days to look back
            rank_by: How to rank papers - options: 'date', 'downloads', 'abstract_views', 
                      'altmetric', 'combined' (default: 'date')
            rank_direction: 'asc' for ascending or 'desc' for descending (default: 'desc')
            rank_weights: Dictionary of weights for combined ranking (default weights if None)
            
        Returns:
            List of paper details including metadata and metrics
        """
        author_match = "all" if require_all else "any"
        return self.search_papers(
            authors=authors,
            author_match=author_match,
            max_results=max_results,
            days_back=days_back,
            rank_by=rank_by,
            rank_direction=rank_direction,
            rank_weights=rank_weights,
            fuzzy_match=fuzzy_match
        )
    
    def search_combined(self, topics: List[str] = None, authors: List[str] = None, 
                       topic_match: str = "all", author_match: str = "any",
                       max_results: int = 5, days_back: int = 30, 
                       rank_by: str = 'date', rank_direction: str = 'desc',
                       rank_weights: Dict[str, float] = None,
                       fuzzy_match: bool = False) -> List[Dict[str, Any]]:
        """
        Search for recent papers by both topics and authors with ranking options.
        
        Args:
            topics: List of topics to search for (optional)
            authors: List of author names to search for (optional)
            topic_match: If "all", papers must match ALL topics; if "any", papers must match ANY topic
            author_match: If "all", papers must match ALL authors; if "any", papers must match ANY author
            max_results: Maximum number of papers to return
            days_back: Number of days to look back
            rank_by: How to rank papers - options: 'date', 'downloads', 'abstract_views', 
                    'altmetric', 'combined' (default: 'date')
            rank_direction: 'asc' for ascending or 'desc' for descending (default: 'desc')
            rank_weights: Dictionary of weights for combined ranking (default weights if None)
            
        Returns:
            List of paper details including metadata and metrics
        """
        return self.search_papers(
            topics=topics,
            authors=authors,
            topic_match=topic_match,
            author_match=author_match,
            max_results=max_results,
            days_back=days_back,
            rank_by=rank_by,
            rank_direction=rank_direction,
            rank_weights=rank_weights,
            fuzzy_match=fuzzy_match
        )
    
    def search_recent_papers(self, topic: str, max_results: int = 5, days_back: int = 30, 
                             rank_by: str = 'date', rank_direction: str = 'desc',
                             rank_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
        """
        Search for recent papers on a specific topic with ranking options.
        
        Args:
            topic: The search topic
            max_results: Maximum number of papers to return
            days_back: Number of days to look back
            rank_by: How to rank papers - options: 'date', 'downloads', 'abstract_views', 
                      'altmetric', 'combined' (default: 'date')
            rank_direction: 'asc' for ascending or 'desc' for descending (default: 'desc')
            rank_weights: Dictionary of weights for combined ranking (default weights if None)
            
        Returns:
            List of paper details including metadata and metrics
        """
        return self.search_papers(
            topics=[topic],
            topic_match="any",
            max_results=max_results,
            days_back=days_back,
            rank_by=rank_by,
            rank_direction=rank_direction,
            rank_weights=rank_weights
        )
    
    def _fetch_paper_metrics(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fetch metrics for a list of papers.
        
        Args:
            papers: List of paper details
            
        Returns:
            Papers with metrics added
        """
        print("Fetching metrics for papers...")
        
        for paper in papers:
            # Initialize metrics
            paper['metrics'] = {
                'abstract_views': 0,
                'full_text_views': 0,
                'pdf_downloads': 0,
                'altmetric_score': 0,
                'twitter_count': 0
            }
            
            doi = paper.get('doi')
            if not doi:
                continue
                
            # Fetch usage metrics from bioRxiv API
            try:
                usage_url = f"{self.base_api_url}/usage/doi/{doi}"
                response = requests.get(usage_url)
                if response.status_code == 200:
                    usage_data = response.json()
                    if 'usage' in usage_data and usage_data['usage']:
                        paper['metrics']['abstract_views'] = usage_data['usage'].get('abstract', 0)
                        paper['metrics']['full_text_views'] = usage_data['usage'].get('full', 0)
                        paper['metrics']['pdf_downloads'] = usage_data['usage'].get('pdf', 0)
            except Exception as e:
                print(f"Error fetching usage metrics for {doi}: {e}")
            
            # Fetch Altmetric data if API key is provided
            if self.altmetric_api_key:
                try:
                    altmetric_url = f"{self.altmetric_base_url}/doi/{doi}?key={self.altmetric_api_key}"
                    response = requests.get(altmetric_url)
                    if response.status_code == 200:
                        altmetric_data = response.json()
                        paper['metrics']['altmetric_score'] = altmetric_data.get('score', 0)
                        paper['metrics']['twitter_count'] = altmetric_data.get('cited_by_tweeters_count', 0)
                except Exception as e:
                    print(f"Error fetching Altmetric data for {doi}: {e}")
        
        return papers
    
    def _sort_papers(self, papers: List[Dict[str, Any]], rank_by: str, 
                    rank_direction: str, rank_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
        """
        Sort papers based on specified ranking method.
        
        Args:
            papers: List of paper details with metrics
            rank_by: Ranking method
            rank_direction: 'asc' or 'desc'
            rank_weights: Weights for combined ranking
            
        Returns:
            Sorted list of papers
        """
        # Default weights for combined ranking
        default_weights = {
            'pdf_downloads': 0.4,
            'abstract_views': 0.2,
            'altmetric_score': 0.3,
            'twitter_count': 0.1
        }
        
        weights = rank_weights if rank_weights else default_weights
        
        # Create a reverse flag for sorting
        reverse = (rank_direction == 'desc')
        
        if rank_by == 'date':
            # Sort by publication date
            return sorted(papers, 
                         key=lambda x: datetime.datetime.strptime(x.get('date', '1970-01-01'), "%Y-%m-%d"), 
                         reverse=reverse)
                         
        elif rank_by == 'downloads':
            # Sort by PDF downloads
            return sorted(papers, 
                         key=lambda x: x.get('metrics', {}).get('pdf_downloads', 0), 
                         reverse=reverse)
                         
        elif rank_by == 'abstract_views':
            # Sort by abstract views
            return sorted(papers, 
                         key=lambda x: x.get('metrics', {}).get('abstract_views', 0), 
                         reverse=reverse)
                         
        elif rank_by == 'altmetric':
            # Sort by Altmetric score
            return sorted(papers, 
                         key=lambda x: x.get('metrics', {}).get('altmetric_score', 0), 
                         reverse=reverse)
                         
        elif rank_by == 'combined':
            # Sort by combined weighted score
            def combined_score(paper):
                metrics = paper.get('metrics', {})
                score = 0
                for metric, weight in weights.items():
                    score += metrics.get(metric, 0) * weight
                return score
                
            return sorted(papers, key=combined_score, reverse=reverse)
            
        else:
            # Default to date if invalid ranking method
            print(f"Warning: Invalid ranking method '{rank_by}'. Using 'date' instead.")
            return sorted(papers, 
                         key=lambda x: datetime.datetime.strptime(x.get('date', '1970-01-01'), "%Y-%m-%d"), 
                         reverse=reverse)
    
    def download_paper(self, paper: Dict[str, Any], output_dir: str) -> Optional[str]:
        """
        Download a paper as PDF.
        
        Args:
            paper: Paper metadata from the API
            output_dir: Directory to save the PDF
            
        Returns:
            Path to the downloaded PDF, or None if download failed
        """
        try:
            # Ensure output directory exists and is writable
            output_dir = _ensure_output_dir(output_dir)
            
            # Extract DOI and construct PDF URL
            doi = paper.get('doi')
            if not doi:
                print(f"Missing DOI for paper: {paper.get('title', 'Unknown')}")
                return None
                
            # Get paper date in YYYY-MM-DD format
            paper_date = paper.get('date', datetime.datetime.now().strftime('%Y-%m-%d'))
            
            # Get first author
            first_author = "Unknown"
            authors = paper.get('authors', [])
            
            # Enhanced author name extraction with minimal logging
            if authors:
                # Try multiple approaches to extract author name correctly
                if isinstance(authors[0], dict):
                    author_name = authors[0].get('name', '')
                    
                    # Handle possible name formats
                    name_parts = author_name.split()
                    
                    if len(name_parts) > 1:
                        last_name = name_parts[-1]
                        first_initial = name_parts[0][0] if name_parts[0] else ''
                        first_author = f"{last_name} {first_initial}"
                    else:
                        first_author = author_name
                        
                elif isinstance(authors[0], str):
                    name_parts = authors[0].split()
                    
                    if len(name_parts) > 1:
                        last_name = name_parts[-1]
                        first_initial = name_parts[0][0] if name_parts[0] else ''
                        first_author = f"{last_name} {first_initial}"
                    else:
                        first_author = authors[0]
                        
                # Handle other possible data structures
                elif isinstance(authors[0], list):
                    if authors[0] and isinstance(authors[0][0], str):
                        name_parts = authors[0][0].split()
                        if len(name_parts) > 1:
                            last_name = name_parts[-1]
                            first_initial = name_parts[0][0] if name_parts[0] else ''
                            first_author = f"{last_name} {first_initial}"
                else:
                    # Try to convert to string and extract
                    try:
                        author_str = str(authors[0])
                        if author_str and len(author_str) > 1:
                            name_parts = author_str.split()
                            if len(name_parts) > 1:
                                last_name = name_parts[-1]
                                first_initial = name_parts[0][0] if name_parts[0] else ''
                                first_author = f"{last_name} {first_initial}"
                            else:
                                first_author = author_str
                    except Exception as e:
                        logger.error(f"Error extracting author name: {e}")
        
            # Get short title (first 10 words or less)
            title = paper.get('title', 'Unknown')
            short_title = ' '.join(title.split()[:10])
            if len(title.split()) > 10:
                short_title += "..."
            
            # Construct a sanitized filename with the requested format
            sanitized_title = re.sub(r'[^\w\s-]', '', short_title)
            sanitized_title = re.sub(r'\s+', ' ', sanitized_title).strip()
            
            # Ensure author name is properly formatted as "LastName FirstInitial"
            sanitized_author = re.sub(r'[^\w\s-]', '', first_author)
            
            # Make sure we don't have just a single letter for the author
            if len(sanitized_author.strip()) <= 1:
                # Try to extract a better author name from the raw author data
                try:
                    authors = paper.get('authors', [])
                    if authors and isinstance(authors, list) and len(authors) > 0:
                        # Try different approaches to get a better author name
                        if isinstance(authors[0], dict) and 'name' in authors[0]:
                            full_name = authors[0]['name']
                            name_parts = full_name.split()
                            if len(name_parts) > 1:
                                sanitized_author = f"{name_parts[-1]} {name_parts[0][0]}"
                except Exception as e:
                    logger.error(f"Error extracting author name: {e}")
            
            filename = f"{paper_date} - {sanitized_author} - {sanitized_title}.pdf"
            # Remove any problematic characters for filenames
            filename = re.sub(r'[<>:"/\\|?*]', '', filename)
            filepath = os.path.join(output_dir, filename)
        
            # bioRxiv PDF URL format
            pdf_url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
        
            logger.info(f"{Fore.BLUE}Downloading: {paper.get('title')}{Style.RESET_ALL}")
            logger.debug(f"PDF URL: {pdf_url}")
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
        
            try:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            
                # Verify the file was downloaded correctly
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    logger.info(f"{Fore.GREEN}Downloaded: {filepath}{Style.RESET_ALL}")
                    return filepath
                else:
                    logger.warning(f"PDF file was created but appears to be empty: {filepath}")
                    return None
            except Exception as e:
                logger.error(f"Error saving PDF file: {e}")
                logger.error(f"Attempted to save to: {filepath}")
                return None
        except Exception as e:
            logger.error(f"Error downloading paper: {e}")
            return None

def _ensure_output_dir(output_dir: str) -> str:
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

class PaperSummarizer:
    """Class to generate summaries of scientific papers."""
    
    def __init__(self, api_key: Optional[str] = None, custom_prompt_path: Optional[str] = None, temperature: float = 0.2, model: str = "gpt-3.5-turbo"):
        """
        Initialize the paper summarizer.
        
        Args:
            api_key: OpenAI API key (optional if set in environment)
            custom_prompt_path: Path to a file containing a custom prompt template (optional)
            temperature: Temperature setting for OpenAI API (0.0-1.0)
            model: OpenAI model to use for summarization (default: gpt-3.5-turbo)
        """
        # Use provided API key or get from environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set it as OPENAI_API_KEY environment variable or pass it directly.")
            
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        # Set temperature for API calls
        self.temperature = temperature
        
        # Set the model to use
        self.model = model
        
        # Load custom prompt if provided
        self.custom_prompt = None
        if custom_prompt_path:
            try:
                with open(custom_prompt_path, 'r', encoding='utf-8') as f:
                    self.custom_prompt = f.read()
                logger.info(f"Custom prompt loaded from {custom_prompt_path}")
            except Exception as e:
                logger.error(f"Error loading custom prompt: {e}")
                logger.info("Using default prompt instead.")
    
    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 30) -> str:
        """
        Extract text from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract
            
        Returns:
            Extracted text from the PDF
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                num_pages = min(len(reader.pages), max_pages)
                
                text = ""
                for i in range(num_pages):
                    page = reader.pages[i]
                    text += page.extract_text() + "\n\n"
                
                return text
                
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""
    
    def generate_summary(self, pdf_path: str, paper_metadata: Dict[str, Any]) -> str:
        """
        Generate a comprehensive summary of a scientific paper.
        
        Args:
            pdf_path: Path to the PDF file
            paper_metadata: Metadata about the paper
            
        Returns:
            Generated summary of the paper
        """
        try:
            # Extract text from PDF
            paper_text = self.extract_text_from_pdf(pdf_path)
            if not paper_text:
                return {"error": "extraction_failed", "message": "Failed to extract text from PDF"}
            
            # Prepare metadata for prompt
            title = paper_metadata.get('title', 'Unknown Title')
            
            # Extract authors with improved handling for various formats
            author_list = []
            authors_data = paper_metadata.get('authors', [])
            
            # Debug the author data structure
            logger.debug(f"Author data structure: {type(authors_data)}")
            if authors_data and len(authors_data) > 0:
                logger.debug(f"First author type: {type(authors_data[0])}")
                logger.debug(f"First author content: {authors_data[0]}")
            
            # Process authors based on their structure
            for author in authors_data:
                if isinstance(author, dict):
                    # Get the full name from the dictionary
                    author_name = author.get('name', '')
                    if author_name:
                        # Clean up any extra spaces or formatting issues
                        author_name = author_name.strip()
                        # Handle the case where the name might be a list of characters
                        if isinstance(author_name, list):
                            author_name = ''.join(str(c) for c in author_name if c)
                        author_list.append(author_name)
                elif isinstance(author, str):
                    # Clean up any extra spaces or formatting issues
                    author_name = author.strip()
                    author_list.append(author_name)
                elif isinstance(author, list):
                    # Handle the case where the author is a list of characters
                    author_name = ''.join(str(c) for c in author if c)
                    if author_name:
                        author_list.append(author_name)
            
            # If the author list is still empty or contains unusual characters,
            # try a different approach by extracting author information from the paper title
            if not author_list or all(len(a) <= 2 for a in author_list):
                logger.warning("Author list appears to be malformed, attempting alternative extraction")
                # Check if we can extract author information from the paper metadata in a different way
                # For example, some papers might include author information in a different field
                
                # Try to get author information from the 'author_corresponding' field if it exists
                corresponding_author = paper_metadata.get('author_corresponding', '')
                if corresponding_author:
                    if isinstance(corresponding_author, dict):
                        author_name = corresponding_author.get('name', '')
                        if author_name:
                            author_list = [author_name.strip()]
                    elif isinstance(corresponding_author, str):
                        author_list = [corresponding_author.strip()]
                
                # If still no valid authors, try to extract from other metadata
                if not author_list:
                    # Some papers might include a formatted citation that includes author names
                    citation = paper_metadata.get('citation', '')
                    if citation and isinstance(citation, str):
                        # Try to extract author names from the citation
                        # Citations often start with author names followed by the title
                        citation_parts = citation.split('.')
                        if len(citation_parts) > 0:
                            potential_authors = citation_parts[0].strip()
                            # If the potential authors section contains commas, it's likely a list of authors
                            if ',' in potential_authors:
                                author_list = [potential_authors]
            
            # Join authors with commas
            authors_str = ', '.join(author_list)
            
            # If no authors were found or the string is empty, provide a default value
            if not authors_str:
                authors_str = 'Unknown Authors'
                
            # Additional cleanup - remove any repeated commas, semicolons, or spaces
            authors_str = re.sub(r',\s*,', ',', authors_str)
            authors_str = re.sub(r';\s*;', ';', authors_str)
            authors_str = re.sub(r'\s+', ' ', authors_str)
            authors_str = re.sub(r',\s*$', '', authors_str)  # Remove trailing comma
            
            # Fix common formatting issues in author strings
            # Replace sequences like "L, i, ," with "Li,"
            authors_str = re.sub(r'([A-Za-z]),\s*([A-Za-z]),\s*', r'\1\2, ', authors_str)
            # Replace sequences of single letters separated by commas with concatenated text
            authors_str = re.sub(r'(?<=[A-Za-z]),\s*(?=[A-Za-z])\s*(?![A-Za-z]{2,})', '', authors_str)
            
            logger.debug(f"Processed authors: {authors_str}")
            
            abstract = paper_metadata.get('abstract', 'No abstract available')
            doi = paper_metadata.get('doi', 'Unknown')
            date = paper_metadata.get('date', 'Unknown')
            
            if self.custom_prompt:
                # Create a dictionary with all possible placeholders and their default values
                prompt_values = {
                    'title': title,
                    'authors': authors_str,
                    'abstract': abstract,
                    'doi': doi,
                    'date': date,
                    'paper_text': paper_text[:10000],
                    # Add default values for other potential placeholders in custom templates
                    'journal': 'bioRxiv (Preprint)',
                    'impact_factor': 'N/A (Preprint)',
                    'citation_count': 'N/A (Preprint)',
                    'url': f"https://www.biorxiv.org/content/{doi}",
                    'category': paper_metadata.get('category', 'Unknown Category'),
                    'version': paper_metadata.get('version', '1'),
                    'license': paper_metadata.get('license', 'Unknown License')
                }
                
                # Use custom prompt with placeholders replaced
                # Use string.format_map with a defaultdict to handle missing placeholders
                from collections import defaultdict
                class DefaultDict(defaultdict):
                    def __missing__(self, key):
                        return f"{{placeholder '{key}' not available}}"
                
                # Format the prompt with all available values, using defaults for missing ones
                prompt = self.custom_prompt.format_map(DefaultDict(lambda: "N/A", prompt_values))
            else:
                # Use default prompt
                prompt = f"""
You are a scientific expert tasked with summarizing and analyzing a research paper from bioRxiv.
Create a comprehensive summary that would be helpful for a researcher deciding whether to read the full paper.

Paper Title: {title}
Authors: {authors_str}
Date: {date}
DOI: {doi}

Abstract:
{abstract}

Paper Content (truncated for length):
{paper_text[:10000]}

Please provide a structured analysis with the following sections:

1. SUMMARY (2-3 paragraphs summarizing the key findings and significance)
2. METHODOLOGY (Brief overview of the main methods used)
3. KEY FINDINGS (Bullet points of the most important results)
4. STRENGTHS (What the paper does well)
5. LIMITATIONS (Potential weaknesses or areas for improvement)
6. SIGNIFICANCE (How this advances the field)
7. AUDIENCE (Who would benefit most from reading this paper)

Your analysis should be scholarly, balanced, and insightful. Highlight both the merits and potential shortcomings of the research.
"""
            
            # Call OpenAI API to generate summary
            logger.info(f"Generating summary using {self.model} model...")
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a scientific expert specializing in analyzing and summarizing research papers."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=4000
                )
                summary = response.choices[0].message.content
                
                # Add a header with paper info
                header = f"# Summary of: {title}\n\n"
                header += f"**Authors:** {authors_str}  \n"
                header += f"**DOI:** {doi}  \n"
                header += f"**Date:** {date}  \n\n"
                header += f"---\n\n"
                
                return header + summary
                
            except Exception as e:
                error_message = str(e)
                logger.error(f"Error calling OpenAI API: {error_message}")
                
                # Check for specific error types
                if "quota" in error_message.lower() or "rate limit" in error_message.lower():
                    return {"error": "quota_exceeded", "message": error_message}
                elif "content filter" in error_message.lower():
                    return {"error": "content_filtered", "message": error_message}
                else:
                    return {"error": "api_error", "message": error_message}
                
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {"error": "general_error", "message": str(e)}
    
class GoogleDriveUploader:
    """Class to upload files to Google Drive."""
    
    def __init__(self, credentials_path: str):
        """
        Initialize the Google Drive uploader.
        
        Args:
            credentials_path: Path to the OAuth credentials JSON file
        """
        self.credentials_path = credentials_path
        self.service = self._authenticate()
        
    def _authenticate(self):
        """
        Authenticate with Google Drive API.
        
        Returns:
            Authenticated Google Drive service
        """
        creds = None
        token_path = 'token.json'
        
        # Check if token.json exists
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
        # If no credentials or if they're invalid, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Save the credentials for next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
                
        return build('drive', 'v3', credentials=creds)
    
    def create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """
        Create a folder in Google Drive.
        
        Args:
            folder_name: Name of the folder to create
            parent_id: ID of the parent folder (optional)
            
        Returns:
            ID of the created folder
        """
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_id:
            folder_metadata['parents'] = [parent_id]
            
        folder = self.service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        
        print(f"Created folder '{folder_name}' with ID: {folder_id}")
        return folder_id
    
    def upload_file(self, file_path: str, folder_id: Optional[str] = None) -> str:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Path to the file to upload
            folder_id: ID of the folder to upload to (optional)
            
        Returns:
            ID of the uploaded file
        """
        file_name = os.path.basename(file_path)
        file_metadata = {'name': file_name}
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(
            file_path, 
            resumable=True
        )
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        print(f"Uploaded '{file_name}' with ID: {file_id}")
        return file_id
    
    def upload_text_as_file(self, text: str, filename: str, folder_id: Optional[str] = None) -> str:
        """
        Upload text content as a file to Google Drive.
        
        Args:
            text: Text content to upload
            filename: Name for the file
            folder_id: ID of the folder to upload to (optional)
            
        Returns:
            ID of the uploaded file
        """
        file_metadata = {'name': filename}
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        # Create a temporary file
        temp_path = f"temp_{int(time.time())}.txt"
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
        try:
            media = MediaFileUpload(
                temp_path,
                mimetype='text/plain',
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            print(f"Uploaded text as '{filename}' with ID: {file_id}")
            return file_id
            
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Search bioRxiv for papers, summarize them, and upload to Google Drive")
    parser.add_argument("--topic", type=str, default=None, help="Topic to search for in bioRxiv")
    # Add multi-topic search options
    parser.add_argument("--topics", type=str, nargs='+', default=None,
                      help="Multiple topics to search for (space-separated)")
    parser.add_argument("--match", type=str, default="all", choices=["all", "any"],
                      help="Match 'all' topics (AND) or 'any' topic (OR)")
    parser.add_argument("--fuzzy_match", action="store_true",
                      help="Enable fuzzy matching for topics (matches similar terms and handles special characters)")
    parser.add_argument("--topic_match", type=str, default="all", choices=["all", "any"],
                      help="Alias for --match: Match 'all' topics (AND) or 'any' topic (OR)")
    # Add author search option
    parser.add_argument("--author", type=str, default=None,
                      help="Author name to search for (can be partial name)")
    parser.add_argument("--authors", type=str, nargs='+', default=None,
                      help="Multiple author names to search for (space-separated)")
    parser.add_argument("--author_match", type=str, default="any", choices=["all", "any"],
                      help="Match 'all' authors (AND) or 'any' author (OR)")
    parser.add_argument("--max_papers", type=int, default=5, help="Maximum number of papers to process")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back")
    parser.add_argument("--credentials", type=str, default="credentials.json", help="Path to Google Drive API credentials")
    parser.add_argument("--output_dir", type=str, default="papers", help="Directory to save downloaded papers")
    parser.add_argument("--drive_folder", type=str, default=None, help="Google Drive folder ID to upload to (creates new if not specified)")
    
    # Add new ranking options
    parser.add_argument("--rank_by", type=str, default="date", 
                       choices=["date", "downloads", "abstract_views", "altmetric", "combined"],
                       help="How to rank papers: date, downloads, abstract_views, altmetric, or combined")
    parser.add_argument("--rank_direction", type=str, default="desc", choices=["asc", "desc"],
                       help="Ranking direction: asc (ascending) or desc (descending)")
    parser.add_argument("--altmetric_key", type=str, default=None, 
                       help="Altmetric API key (required for altmetric ranking)")
    
    # Add custom weight arguments for combined ranking
    parser.add_argument("--weight_downloads", type=float, default=0.4,
                       help="Weight for PDF downloads in combined ranking (default: 0.4)")
    parser.add_argument("--weight_views", type=float, default=0.2,
                       help="Weight for abstract views in combined ranking (default: 0.2)")
    parser.add_argument("--weight_altmetric", type=float, default=0.3,
                       help="Weight for Altmetric score in combined ranking (default: 0.3)")
    parser.add_argument("--weight_twitter", type=float, default=0.1,
                       help="Weight for Twitter mentions in combined ranking (default: 0.1)")
    
    # Add custom prompt option
    parser.add_argument("--custom_prompt", type=str, default=None,
                       help="Path to a file containing a custom prompt template for paper summarization")
    parser.add_argument("--prompt_string", type=str, default=None,
                       help="Custom prompt string for paper summarization (alternative to --custom_prompt)")
    
    # Add OpenAI API options
    parser.add_argument("--temperature", type=float, default=0.2,
                       help="Temperature setting for OpenAI API (0.0-1.0). Lower values make output more focused and deterministic, higher values make output more random (default: 0.2)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini",
                       choices=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"],
                       help="OpenAI model to use for summarization (default: gpt-4o-mini)")
    
    # Add logging options
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output (debug level logging)")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Minimize output (only show warnings and errors)")
    parser.add_argument("--log-file", type=str, default=None,
                       help="Save logs to the specified file")
    
    return parser.parse_args()

# Define a custom filter to exclude certain debug messages
class PaperMetadataFilter(logging.Filter):
    """Filter out paper metadata debug messages when in verbose mode."""
    def filter(self, record):
        # Filter out paper category and key messages
        if any(x in record.getMessage() for x in ["Paper category:", "Paper type:", "Paper keys:", "Author data"]):
            return False
        return True

def setup_logging(args):
    """Configure logging based on command-line arguments."""
    # Configure logging level based on command-line arguments
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        # Add filter to exclude paper metadata messages
        paper_filter = PaperMetadataFilter()
        console_handler.addFilter(paper_filter)
    elif args.quiet:
        logger.setLevel(logging.WARNING)
        console_handler.setLevel(logging.WARNING)
    
    # Add file handler if log file is specified
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        logger.addHandler(file_handler)
        logger.info(f"Logging to file: {args.log_file}")
    
    # Log the start of the program with some fancy formatting
    logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}BioRxiv Paper Summarizer v1.0{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

def initialize_components(args):
    """Initialize the main components needed for the workflow."""
    # Check for Altmetric API key if needed
    if args.rank_by in ['altmetric', 'combined'] and not args.altmetric_key:
        logger.warning("Altmetric API key is required for 'altmetric' or 'combined' ranking.")
        logger.warning("Altmetric scores will be set to 0. To use Altmetric data, provide --altmetric_key.")
    
    # Configure weights for combined ranking
    rank_weights = {
        'pdf_downloads': args.weight_downloads,
        'abstract_views': args.weight_views,
        'altmetric_score': args.weight_altmetric,
        'twitter_count': args.weight_twitter
    }
    
    # Handle prompt_string option by creating a temporary file
    temp_prompt_file = None
    custom_prompt_path = args.custom_prompt
    if args.prompt_string:
        try:
            temp_prompt_file = f"temp_prompt_{int(time.time())}.txt"
            with open(temp_prompt_file, 'w', encoding='utf-8') as f:
                f.write(args.prompt_string)
            custom_prompt_path = temp_prompt_file
            logger.info(f"Custom prompt string saved to temporary file: {temp_prompt_file}")
        except Exception as e:
            logger.error(f"Error creating temporary prompt file: {e}")
            logger.info("Using default prompt instead.")
            custom_prompt_path = None
    
    # Initialize searcher and summarizer
    searcher = BioRxivSearcher(altmetric_api_key=args.altmetric_key)
    summarizer = PaperSummarizer(custom_prompt_path=custom_prompt_path, temperature=args.temperature, model=args.model)
    
    # Ensure output directory exists and is writable
    args.output_dir = _ensure_output_dir(args.output_dir)
    
    # Initialize Google Drive components only if drive_folder is specified
    uploader = None
    drive_folder_id = None
    
    if args.drive_folder is not None:
        # Check if credentials file exists
        if not os.path.exists(args.credentials):
            logger.error(f"Google Drive credentials file '{args.credentials}' not found.")
            logger.error("Please provide a valid credentials file or use --output_dir without --drive_folder.")
        else:
            # Initialize Google Drive uploader
            uploader = GoogleDriveUploader(args.credentials)
            
            # Create main folder in Google Drive if needed
            drive_folder_id = args.drive_folder
            if not drive_folder_id:
                folder_name = f"BioRxiv Papers - {args.topic} - {datetime.datetime.now().strftime('%Y-%m-%d')}"
                drive_folder_id = uploader.create_folder(folder_name)
    
    return searcher, summarizer, uploader, drive_folder_id, rank_weights, temp_prompt_file

def search_papers_based_on_args(args, searcher, rank_weights):
    """Search for papers based on command-line arguments."""
    # Validate that at least one search parameter is provided
    if not args.topic and not args.topics and not args.author and not args.authors:
        logger.error("Error: At least one search parameter (topic, topics, author, or authors) must be provided")
        return []
    
    # Determine the search method based on provided arguments
    topics_list = args.topics if args.topics else [args.topic] if args.topic else None
    authors_list = args.authors if args.authors else [args.author] if args.author else None
    
    # Determine topic matching mode (use topic_match if provided, otherwise use match)
    topic_match_mode = args.topic_match if args.topic_match != "all" else args.match
    
    # Use the unified search method
    papers = searcher.search_papers(
        topics=topics_list,
        authors=authors_list,
        topic_match=topic_match_mode,
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
    
    for i, paper in enumerate(papers, 1):
        title = paper.get('title', 'Unknown')
        logger.info(f"\n{Fore.CYAN}Processing paper {i}/{len(papers)}: {title}{Style.RESET_ALL}")
        
        # Download paper
        searcher = BioRxivSearcher()  # Create a temporary instance just for downloading
        pdf_path = searcher.download_paper(paper, args.output_dir)
        if not pdf_path:
            logger.error(f"Failed to download paper: {title}")
            continue
        
        # Skip summarization if we've already hit quota limits
        if api_quota_exceeded:
            logger.warning("Skipping summary generation due to previously encountered API quota limits.")
            logger.info(f"Paper downloaded to: {pdf_path}")
            continue
            
        # Generate summary
        summary_result = summarizer.generate_summary(pdf_path, paper)
        
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
    setup_logging(args)
    
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