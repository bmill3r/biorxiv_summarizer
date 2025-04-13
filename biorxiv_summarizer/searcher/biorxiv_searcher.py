#!/usr/bin/env python3
"""
BioRxiv Searcher Module

This module provides functionality to search and retrieve papers from bioRxiv.
"""

import os
import re
import requests
import datetime
import logging
from typing import List, Dict, Any, Tuple, Optional
from colorama import Fore, Style

from ..utils.file_utils import ensure_output_dir

# Get logger
logger = logging.getLogger('biorxiv_summarizer')

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
            output_dir = ensure_output_dir(output_dir)
            
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
