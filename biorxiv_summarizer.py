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
    
    def search_multi_topic_papers(self, topics: List[str], require_all: bool = True, max_results: int = 5,
                            days_back: int = 30, rank_by: str = 'date', 
                            rank_direction: str = 'desc',
                            rank_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
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
        logger.info(f"{Fore.CYAN}Searching for recent papers on topics: {', '.join(topics)} (Match {'ALL' if require_all else 'ANY'}){Style.RESET_ALL}")
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
                
            # Filter papers based on topics
            matching_papers = []
            for paper in data['collection']:
                # Search in title, abstract, and authors
                searchable_text = paper.get('title', '') + ' ' + paper.get('abstract', '')
                
                # Handle authors which could be in different formats
                authors = paper.get('authors', [])
                if authors:
                    author_text = ''
                    for author in authors:
                        if isinstance(author, dict):
                            author_text += ' ' + author.get('name', '')
                        elif isinstance(author, str):
                            author_text += ' ' + author
                    searchable_text += author_text
                
                # Check if paper matches topics based on require_all setting
                topics_matched = []
                for topic in topics:
                    if re.search(topic, searchable_text, re.IGNORECASE):
                        topics_matched.append(topic)
                
                if require_all and len(topics_matched) == len(topics):
                    # Paper matches ALL topics
                    paper['matched_topics'] = topics_matched
                    matching_papers.append(paper)
                elif not require_all and topics_matched:
                    # Paper matches ANY topic
                    paper['matched_topics'] = topics_matched
                    matching_papers.append(paper)
            
            matches_all = "all required topics" if require_all else "at least one topic"
            if matching_papers:
                logger.info(f"{Fore.GREEN}Found {len(matching_papers)} papers matching {matches_all}{Style.RESET_ALL}")
            else:
                logger.warning(f"No papers found matching {matches_all}")
            
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
        
    def search_by_authors(self, authors: List[str], require_all: bool = False, max_results: int = 5,
                       days_back: int = 30, rank_by: str = 'date', rank_direction: str = 'desc',
                       rank_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
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
        print(f"Searching for recent papers by authors: {', '.join(authors)} (Match {'ALL' if require_all else 'ANY'})")
        
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
                
            # Filter papers based on authors
            matching_papers = []
            for paper in data['collection']:
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
                
                # Check if paper matches authors based on require_all setting
                authors_matched = []
                for search_author in authors:
                    search_author_lower = search_author.lower()
                    for author_name in author_names:
                        if search_author_lower in author_name:
                            authors_matched.append(search_author)
                            break
                
                if require_all and len(authors_matched) == len(authors):
                    # Paper matches ALL authors
                    paper['matched_authors'] = authors_matched
                    matching_papers.append(paper)
                elif not require_all and authors_matched:
                    # Paper matches ANY author
                    paper['matched_authors'] = authors_matched
                    matching_papers.append(paper)
            
            matches_all = "all specified authors" if require_all else "at least one author"
            print(f"Found {len(matching_papers)} papers matching {matches_all}")
            
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
    
    def search_combined(self, topics: List[str] = None, authors: List[str] = None, 
                      topic_match: str = "all", author_match: str = "any",
                      max_results: int = 5, days_back: int = 30, 
                      rank_by: str = 'date', rank_direction: str = 'desc',
                      rank_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
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
        # Validate that at least one of topics or authors is provided
        if not topics and not authors:
            print("Error: At least one topic or author must be provided")
            return []
            
        search_criteria = []
        if topics:
            search_criteria.append(f"topics: {', '.join(topics)} (Match {topic_match.upper()})")
        if authors:
            search_criteria.append(f"authors: {', '.join(authors)} (Match {author_match.upper()})")
            
        print(f"Searching for recent papers matching {' AND '.join(search_criteria)}")
        
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
                    # Search in title, abstract, and authors for topics
                    searchable_text = paper.get('title', '') + ' ' + paper.get('abstract', '')
                    
                    # Add author text to searchable text
                    authors_list = paper.get('authors', [])
                    if authors_list:
                        author_text = ''
                        for author in authors_list:
                            if isinstance(author, dict):
                                author_text += ' ' + author.get('name', '')
                            elif isinstance(author, str):
                                author_text += ' ' + author
                        searchable_text += author_text
                    
                    # Check if paper matches topics based on topic_match setting
                    topics_matched = []
                    for topic in topics:
                        if re.search(topic, searchable_text, re.IGNORECASE):
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
            
            print(f"Found {len(matching_papers)} papers matching the combined criteria")
            
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
        print(f"Searching for recent papers on '{topic}'...")
        
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
                
            # Filter papers based on topic
            matching_papers = []
            for paper in data['collection']:
                # Search in title, abstract, and authors
                searchable_text = paper.get('title', '') + ' ' + paper.get('abstract', '')
                
                # Handle authors which could be in different formats
                authors = paper.get('authors', [])
                if authors:
                    author_text = ''
                    for author in authors:
                        if isinstance(author, dict):
                            author_text += ' ' + author.get('name', '')
                        elif isinstance(author, str):
                            author_text += ' ' + author
                    searchable_text += author_text
                
                if re.search(topic, searchable_text, re.IGNORECASE):
                    matching_papers.append(paper)
            
            print(f"Found {len(matching_papers)} papers matching topic '{topic}'")
            
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
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
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
            if authors:
                if isinstance(authors[0], dict):
                    first_author = authors[0].get('name', '').split()[-1]  # Get last name
                elif isinstance(authors[0], str):
                    first_author = authors[0].split()[-1]  # Get last name
            
            # Get short title (first 10 words or less)
            title = paper.get('title', 'Unknown')
            short_title = ' '.join(title.split()[:10])
            if len(title.split()) > 10:
                short_title += "..."
                
            # Construct a sanitized filename with the requested format
            sanitized_title = re.sub(r'[^\w\s-]', '', short_title)
            sanitized_title = re.sub(r'\s+', ' ', sanitized_title).strip()
            sanitized_author = re.sub(r'[^\w\s-]', '', first_author)
            
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
                logger.info("Attempting to save to fallback location...")
                # Try saving to current directory as fallback
                fallback_path = os.path.join(os.path.abspath('.'), filename)
                try:
                    with open(fallback_path, 'wb') as f:
                        response = requests.get(pdf_url, stream=True)  # Get the content again
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logger.info(f"{Fore.GREEN}Downloaded to fallback location: {fallback_path}{Style.RESET_ALL}")
                    return fallback_path
                except Exception as e2:
                    logger.error(f"Failed to download even to fallback location: {e2}")
                    return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading paper: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading paper: {e}")
            return None

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
        logger.info(f"{Fore.BLUE}Generating summary for: {paper_metadata.get('title', 'Unknown paper')}{Style.RESET_ALL}")
        
        # Extract text from PDF
        paper_text = self.extract_text_from_pdf(pdf_path)
        if not paper_text:
            logger.error("Failed to extract text from the PDF.")
            return "Failed to extract text from the PDF."
            
        # Prepare the prompt for the AI
        title = paper_metadata.get('title', 'Unknown')
        
        # Handle authors which could be in different formats
        author_list = []
        for author in paper_metadata.get('authors', []):
            if isinstance(author, dict):
                author_name = author.get('name', '')
                if author_name:
                    author_list.append(author_name)
            elif isinstance(author, str):
                author_list.append(author)
        authors = ', '.join(author_list)
        
        abstract = paper_metadata.get('abstract', 'No abstract available')
        doi = paper_metadata.get('doi', 'Unknown')
        date = paper_metadata.get('date', 'Unknown')
        
        if self.custom_prompt:
            # Use custom prompt with placeholders replaced
            prompt = self.custom_prompt.format(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                date=date,
                paper_text=paper_text[:10000]
            )
        else:
            # Use default prompt
            prompt = f"""
            Create a comprehensive summary of the following scientific paper aimed at a first-year PhD student:
            
            Title: {title}
            Authors: {authors}
            Abstract: {abstract}
            
            Here's the paper text (truncated for length): 
            {paper_text[:10000]}
            
            Please provide a structured summary with the following sections:
            1. Key findings and contributions
            2. Methodology overview
            3. Main results and their implications
            4. Strengths of the paper
            5. Limitations and weaknesses
            6. How this advances the field
            7. Potential future research directions
            
            The summary should be informative, clear, and help a PhD student quickly understand the paper's value.
            """
        
        try:
            # Call the API for summarization using the new OpenAI client format
            response = self.client.chat.completions.create(
                model=self.model,  # Use the model specified during initialization
                messages=[
                    {"role": "system", "content": "You are a helpful scientific assistant skilled at summarizing academic papers for PhD students."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=self.temperature
            )
            
            # Access the content using the new response structure
            summary = response.choices[0].message.content
            
            # Format the summary with metadata if custom prompt wasn't used
            # (assumes custom prompt handles its own formatting if used)
            if not self.custom_prompt:
                formatted_summary = f"""
                # Summary of "{title}"
                
                **Authors:** {authors}
                **DOI:** {paper_metadata.get('doi', 'Unknown')}
                **Publication Date:** {paper_metadata.get('date', 'Unknown')}
                
                ## Original Abstract
                {abstract}
                
                {summary}
                
                ---
                *This summary was generated automatically and may miss nuances of the paper.*
                """
            else:
                formatted_summary = summary
            
            return formatted_summary
            
        except openai.RateLimitError as e:
            error_msg = f"OpenAI API rate limit exceeded: {e}"
            logger.error(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            return {"error": "rate_limit", "message": error_msg}
            
        except openai.InsufficientQuotaError as e:
            error_msg = f"OpenAI API quota exceeded: {e}. Please check your billing details at https://platform.openai.com/account/billing."
            logger.error(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            return {"error": "quota_exceeded", "message": error_msg}
            
        except openai.APIError as e:
            error_msg = f"OpenAI API error: {e}"
            logger.error(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            return {"error": "api_error", "message": error_msg}
            
        except Exception as e:
            error_msg = f"Error generating summary: {e}"
            logger.error(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            return {"error": "general", "message": error_msg}

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


def main():
    """Main function to run the workflow."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Search bioRxiv for papers, summarize them, and upload to Google Drive")
    parser.add_argument("--topic", type=str, default=None, help="Topic to search for in bioRxiv")
    # Add multi-topic search options
    parser.add_argument("--topics", type=str, nargs='+', default=None,
                      help="Multiple topics to search for (space-separated)")
    parser.add_argument("--match", type=str, default="all", choices=["all", "any"],
                      help="Match 'all' topics (AND) or 'any' topic (OR)")
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
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo",
                       choices=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"],
                       help="OpenAI model to use for summarization (default: gpt-3.5-turbo)")
    
    # Add logging options
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output (debug level logging)")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Minimize output (only show warnings and errors)")
    parser.add_argument("--log-file", type=str, default=None,
                       help="Save logs to the specified file")
    
    args = parser.parse_args()
    
    # Configure logging based on command-line arguments
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
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
            print(f"Custom prompt string saved to temporary file: {temp_prompt_file}")
        except Exception as e:
            print(f"Error creating temporary prompt file: {e}")
            print("Using default prompt instead.")
            custom_prompt_path = None
    
    try:
        # Step 1: Initialize components
        searcher = BioRxivSearcher(altmetric_api_key=args.altmetric_key)
        summarizer = PaperSummarizer(custom_prompt_path=custom_prompt_path, temperature=args.temperature, model=args.model)
        
        # Create output directory if it doesn't exist (with support for nested directories)
        try:
            if not os.path.exists(args.output_dir):
                os.makedirs(args.output_dir, exist_ok=True)
                print(f"Created output directory: {args.output_dir}")
            
            # Verify the directory is writable
            test_file = os.path.join(args.output_dir, '.write_test')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except Exception as e:
                print(f"Warning: Output directory may not be writable: {e}")
                print("Please check permissions or choose a different output directory.")
        except Exception as e:
            print(f"Error creating output directory: {e}")
            print("Using current directory as fallback.")
            args.output_dir = os.path.abspath('.')
        
        # Initialize Google Drive components only if drive_folder is specified
        uploader = None
        drive_folder_id = None
        
        if args.drive_folder is not None:
            # Check if credentials file exists
            if not os.path.exists(args.credentials):
                print(f"Error: Google Drive credentials file '{args.credentials}' not found.")
                print("Please provide a valid credentials file or use --output_dir without --drive_folder.")
                return
                
            # Initialize Google Drive uploader
            uploader = GoogleDriveUploader(args.credentials)
            
            # Create main folder in Google Drive if needed
            drive_folder_id = args.drive_folder
            if not drive_folder_id:
                folder_name = f"BioRxiv Papers - {args.topic} - {datetime.datetime.now().strftime('%Y-%m-%d')}"
                drive_folder_id = uploader.create_folder(folder_name)
        
        # Step 3: Search for papers with ranking
        print(f"Searching and ranking papers by '{args.rank_by}' ({args.rank_direction}ending)...")
        
        # Validate that at least one search parameter is provided
        if not args.topic and not args.topics and not args.author and not args.authors:
            logger.error("Error: At least one search parameter (topic, topics, author, or authors) must be provided")
            return
        
        # Determine the search method based on provided arguments
        if (args.topics or args.topic) and (args.authors or args.author):
            # Combined search with both topics and authors
            topics_list = args.topics if args.topics else [args.topic] if args.topic else None
            authors_list = args.authors if args.authors else [args.author] if args.author else None
            
            papers = searcher.search_combined(
                topics=topics_list,
                authors=authors_list,
                topic_match=args.match,
                author_match=args.author_match,
                max_results=args.max_papers,
                days_back=args.days,
                rank_by=args.rank_by,
                rank_direction=args.rank_direction,
                rank_weights=rank_weights
            )
        elif args.authors or args.author:
            # Author-only search
            authors_list = args.authors if args.authors else [args.author]
            require_all = args.author_match == "all"
            
            papers = searcher.search_by_authors(
                authors=authors_list,
                require_all=require_all,
                max_results=args.max_papers,
                days_back=args.days,
                rank_by=args.rank_by,
                rank_direction=args.rank_direction,
                rank_weights=rank_weights
            )
        elif args.topics:
            # Multi-topic search
            require_all = args.match == "all"
            papers = searcher.search_multi_topic_papers(
                topics=args.topics,
                require_all=require_all,
                max_results=args.max_papers,
                days_back=args.days,
                rank_by=args.rank_by,
                rank_direction=args.rank_direction,
                rank_weights=rank_weights
            )
        else:
            # Single topic search
            papers = searcher.search_recent_papers(
                topic=args.topic,
                max_results=args.max_papers,
                days_back=args.days,
                rank_by=args.rank_by,
                rank_direction=args.rank_direction,
                rank_weights=rank_weights
            )
        
        if not papers:
            logger.warning("No papers found matching the criteria.")
            return
        
        # Step 4: Process each paper
        logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}Starting to process {len(papers)} papers{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        api_quota_exceeded = False  # Flag to track if we've hit API quota limits
        
        for i, paper in enumerate(papers, 1):
            title = paper.get('title', 'Unknown')
            logger.info(f"\n{Fore.CYAN}Processing paper {i}/{len(papers)}: {title}{Style.RESET_ALL}")
            
            # Download paper
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
        
        logger.info(f"\n{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}Workflow complete!{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
    
    finally:
        # Clean up temporary prompt file if created
        if temp_prompt_file and os.path.exists(temp_prompt_file):
            try:
                os.remove(temp_prompt_file)
                print(f"Temporary prompt file removed: {temp_prompt_file}")
            except Exception as e:
                print(f"Warning: Could not remove temporary prompt file {temp_prompt_file}: {e}")

if __name__ == "__main__":
    main()
    