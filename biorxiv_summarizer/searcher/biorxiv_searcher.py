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
import time
import json
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Any, Tuple, Optional
from colorama import Fore, Style

from ..utils.file_utils import ensure_output_dir

# Get logger
logger = logging.getLogger('biorxiv_summarizer')

class BioRxivSearcher:
    """Class to search and retrieve papers from bioRxiv."""
    
    def __init__(self, altmetric_api_key=None, verify_ssl=True, bypass_api=False):
        """
        Initialize the bioRxiv searcher.
        
        Args:
            altmetric_api_key: API key for Altmetric (optional)
            verify_ssl: Whether to verify SSL certificates (default: True)
            bypass_api: Whether to bypass the API and use web scraping directly (default: False)
        """
        self.base_api_url = "https://api.biorxiv.org"
        self.altmetric_api_key = altmetric_api_key
        self.altmetric_base_url = "https://api.altmetric.com/v1"
        self.verify_ssl = verify_ssl
        self.bypass_api = bypass_api
        
        if bypass_api:
            logger.info(f"{Fore.YELLOW}API bypass enabled. Using web scraping directly instead of the bioRxiv API.{Style.RESET_ALL}")
        
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning(f"{Fore.YELLOW}SSL verification disabled. This is not recommended for production use.{Style.RESET_ALL}")
        
        # Configure session with retry mechanism
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,  # Maximum number of retries
            backoff_factor=1,  # Time factor between retries
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
            allowed_methods=["GET"],  # HTTP methods to retry
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
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
        
        # If API bypass is enabled, go straight to the fallback method
        if self.bypass_api:
            logger.info(f"{Fore.YELLOW}API bypass enabled. Using web scraping directly.{Style.RESET_ALL}")
            return self._search_papers_fallback(topics, authors, topic_match, author_match, max_results, days_back, rank_by, rank_direction, rank_weights, fuzzy_match)
        
        # Calculate date range
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # Structure the API request URL
        details_url = f"{self.base_api_url}/details/biorxiv/{start_date}/{end_date}/0"
        
        try:
            # Fetch papers for the date range with timeout and retry
            for attempt in range(2):  # Try up to 2 times
                try:
                    logger.debug(f"API request attempt {attempt+1} to {details_url}")
                    response = self.session.get(details_url, timeout=30, verify=self.verify_ssl)  # 30 second timeout
                    response.raise_for_status()
                    data = response.json()
                    break  # Success, exit the retry loop
                except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError) as e:
                    if attempt < 1:  # If not the last attempt
                        logger.warning(f"API request attempt {attempt+1} failed: {e}. Retrying...")
                        time.sleep(2)  # Wait before retrying
                    else:
                        # Last attempt failed, try the fallback method
                        logger.warning(f"All API request attempts failed. Trying fallback method...")
                        return self._search_papers_fallback(topics, authors, topic_match, author_match, max_results, days_back, rank_by, rank_direction, rank_weights, fuzzy_match)
            
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
    
    def _search_papers_fallback(self, 
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
        Fallback method to search bioRxiv papers using the website directly instead of the API.
        This is used when the API connection fails.
        """
        logger.info(f"{Fore.YELLOW}Using fallback method to search bioRxiv website directly{Style.RESET_ALL}")
        
        # Calculate date range for filtering
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days_back)
        
        # Format dates for logging
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        logger.info(f"Date range: {start_date_str} to {end_date_str}")
        
        # Construct search query for bioRxiv website
        search_terms = []
        if topics:
            search_terms.extend(topics)
        if authors:
            search_terms.extend([f"author:{author}" for author in authors])
            
        search_query = " ".join(search_terms)
        
        # Add date filtering to the search URL if possible
        # bioRxiv website supports date filtering with format: jcode:biorxiv date_from:YYYY-MM-DD date_to:YYYY-MM-DD
        search_query += f" jcode:biorxiv date_from:{start_date_str} date_to:{end_date_str}"
        
        # Format the search URL for bioRxiv website
        search_url = f"https://www.biorxiv.org/search/{search_query}"
        
        try:
            # Fetch search results from bioRxiv website
            logger.debug(f"Fallback search URL: {search_url}")
            
            # Add user-agent header to mimic a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = self.session.get(search_url, timeout=30, verify=self.verify_ssl, headers=headers)
            response.raise_for_status()
            
            # Parse the HTML response
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract paper information from search results
            papers = []
            for result in soup.select('.highwire-article-citation'):
                try:
                    # Extract paper details
                    title_elem = result.select_one('.highwire-cite-title')
                    title = title_elem.text.strip() if title_elem else "Unknown Title"
                    
                    # Extract DOI and paper ID from the link
                    doi = None
                    paper_id = None
                    pdf_url = None
                    link_elem = title_elem.find('a') if title_elem else None
                    if link_elem and 'href' in link_elem.attrs:
                        href = link_elem['href']
                        logger.debug(f"Found paper link: {href}")
                        
                        # Store the original href for later use with PDF download
                        original_href = href
                        
                        # Try to extract paper ID and DOI using different patterns
                        # Pattern 1: Standard bioRxiv DOI format with complete identifier
                        doi_match = re.search(r'10\.1101/([\d\.]+(?:v\d+)?)', href)
                        if doi_match:
                            paper_id = doi_match.group(1)  # The complete paper identifier
                            doi = f"10.1101/{paper_id}"
                            logger.debug(f"Extracted DOI: {doi} and paper ID: {paper_id} from href: {href}")
                        else:
                            # Pattern 2: URL path format with complete identifier
                            path_match = re.search(r'/content/(?:early/)?(\d+\.\d+\.\d+\.\d+(?:v\d+)?)', href)
                            if path_match:
                                paper_id = path_match.group(1)
                                doi = f"10.1101/{paper_id}"
                                logger.debug(f"Extracted paper ID: {paper_id} from path: {href}")
                            else:
                                # Pattern 3: Try to extract from content path with year and month format
                                year_month_match = re.search(r'/content/(?:early/)?(\d{4}\.\d{2}\.\d{2}\.\d+(?:v\d+)?)', href)
                                if year_month_match:
                                    paper_id = year_month_match.group(1)
                                    doi = f"10.1101/{paper_id}"
                                    logger.debug(f"Extracted paper ID with year/month: {paper_id} from path: {href}")
                                else:
                                    # If we can't extract DOI or paper ID, log it
                                    logger.debug(f"Could not extract DOI or paper ID from href: {href}")
                        
                        # Construct direct PDF URL if we have the original href
                        if href.startswith('/'):
                            # Convert relative URL to absolute
                            href = f"https://www.biorxiv.org{href}"
                        
                        # Store the content URL for later PDF construction
                        content_url = href
                        
                        # If the URL ends with a file extension, remove it to get the base URL
                        if '.' in href.split('/')[-1]:
                            content_url = re.sub(r'\.[^.]+$', '', href)
                        
                        # For bioRxiv URLs, ensure we have the correct format for PDF download
                        if paper_id and 'biorxiv.org' in content_url:
                            # Construct PDF URL with the complete paper identifier
                            pdf_url = f"https://www.biorxiv.org/content/10.1101/{paper_id}.full.pdf"
                            logger.debug(f"Constructed bioRxiv PDF URL: {pdf_url}")
                        else:
                            # Fallback to appending .full.pdf to the content URL
                            pdf_url = f"{content_url}.full.pdf"
                            logger.debug(f"Constructed generic PDF URL: {pdf_url}")
                    
                    # Extract authors
                    author_elems = result.select('.highwire-citation-author')
                    authors = [author.text.strip() for author in author_elems]
                    
                    # Extract abstract
                    abstract_elem = result.select_one('.highwire-cite-snippet')
                    abstract = abstract_elem.text.strip() if abstract_elem else ""
                    
                    # Extract date
                    date_elem = result.select_one('.highwire-cite-metadata-date')
                    date_str = date_elem.text.strip() if date_elem else ""
                    pub_date = None
                    if date_str:
                        try:
                            # Parse date in format like "January 1, 2025"
                            pub_date = datetime.datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            try:
                                # Try alternative date formats
                                # Format like "Jan 1, 2025"
                                pub_date = datetime.datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
                            except ValueError:
                                try:
                                    # Format like "2025-01-01"
                                    pub_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
                                except ValueError:
                                    # If all parsing attempts fail, extract year and use January 1st of that year
                                    year_match = re.search(r'(\d{4})', date_str)
                                    if year_match:
                                        year = year_match.group(1)
                                        pub_date = f"{year}-01-01"
                                        logger.debug(f"Extracted year {year} from date string: {date_str}")
                                    else:
                                        # If we can't even extract a year, use current date
                                        pub_date = datetime.datetime.now().strftime("%Y-%m-%d")
                                        logger.debug(f"Could not parse date string: {date_str}, using current date")
                    
                    # Extract date from paper ID if available
                    paper_date = None
                    if paper_id:
                        paper_date = self._extract_date_from_paper_id(paper_id)
                        if paper_date:
                            logger.debug(f"Extracted date {paper_date} from paper ID: {paper_id}")
                    
                    # Create paper object
                    paper = {
                        'title': title,
                        'doi': doi,
                        'authors': [{'name': author} for author in authors],
                        'abstract': abstract,
                        'date': pub_date,
                        'source': 'fallback',
                        'pdf_url': pdf_url  # Store the PDF URL for direct access later
                    }
                    
                    # If we have a date from the paper ID but no pub_date, use it
                    if not pub_date and paper_id:
                        paper_date = self._extract_date_from_paper_id(paper_id)
                        if paper_date:
                            paper['date'] = paper_date
                            logger.debug(f"Using date {paper_date} extracted from paper ID")
                    
                    # Filter by date if we have a valid date
                    if paper_date:
                        paper_date = datetime.datetime.strptime(paper_date, "%Y-%m-%d")
                        # Strict date filtering to ensure papers are within the specified range
                        if start_date <= paper_date <= end_date:
                            papers.append(paper)
                            logger.debug(f"Paper date {paper_date} is within range {start_date_str} to {end_date_str}")
                        else:
                            logger.debug(f"Paper date {paper_date} is outside range {start_date_str} to {end_date_str}, skipping")
                    else:
                        # If we can't determine date, include it anyway but log a warning
                        logger.warning(f"Could not determine date for paper: {title}. Including it anyway.")
                        papers.append(paper)
                        
                except Exception as e:
                    logger.error(f"Error parsing paper from fallback search: {e}")
            
            # Sort papers by date if we have dates
            if papers:
                # Sort papers by date (most recent first)
                papers_with_dates = [p for p in papers if p.get('date')]
                papers_without_dates = [p for p in papers if not p.get('date')]
                
                if papers_with_dates:
                    papers_with_dates.sort(key=lambda p: datetime.datetime.strptime(p.get('date', ''), "%Y-%m-%d"), reverse=True)
                
                # Combine sorted papers with those without dates
                papers = papers_with_dates + papers_without_dates
            
            logger.info(f"{Fore.GREEN}Found {len(papers)} papers using fallback search method{Style.RESET_ALL}")
            
            # Return the top papers based on max_results
            return papers[:max_results]
            
        except Exception as e:
            logger.error(f"Fallback search method failed: {e}")
            return []
    
    def _extract_date_from_paper_id(self, paper_id: str) -> Optional[str]:
        """
        Extract and format date from a bioRxiv paper ID.
        
        Args:
            paper_id: The paper ID, e.g., '2025.04.01.646202v1'
            
        Returns:
            Formatted date string (YYYY-MM-DD) or None if no date could be extracted
        """
        if not paper_id:
            return None
            
        # Try to extract date in format YYYY.MM.DD from paper ID
        date_match = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})\.', paper_id)
        if date_match:
            year, month, day = date_match.groups()
            try:
                # Validate the date
                datetime.date(int(year), int(month), int(day))
                return f"{year}-{month}-{day}"
            except ValueError:
                logger.debug(f"Invalid date components in paper ID: {paper_id}")
                return None
                
        return None
    
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
            rank_by: How to rank papers ('date', 'downloads', 'abstract_views', 
                    'altmetric', 'combined') (default: 'date')
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
        # Determine sort direction
        reverse = rank_direction.lower() == 'desc'
        
        # Default weights for combined ranking
        if rank_by == 'combined' and not rank_weights:
            rank_weights = {
                'pdf_downloads': 0.4,
                'abstract_views': 0.3,
                'altmetric_score': 0.2,
                'twitter_count': 0.1
            }
            
        if rank_by == 'date':
            # Sort by publication date with safe handling of missing or invalid dates
            def safe_date_key(paper):
                date_str = paper.get('date')
                if not date_str:
                    # Use a very old date for missing dates when sorting in descending order (newest first)
                    # or a future date when sorting in ascending order (oldest first)
                    return datetime.datetime(1970, 1, 1) if reverse else datetime.datetime(2100, 1, 1)
                try:
                    return datetime.datetime.strptime(date_str, "%Y-%m-%d")
                except (ValueError, TypeError):
                    # If date string is invalid, use a default date
                    logger.warning(f"Invalid date format: {date_str}, using default date for sorting")
                    return datetime.datetime(1970, 1, 1) if reverse else datetime.datetime(2100, 1, 1)
            
            return sorted(papers, key=safe_date_key, reverse=reverse)
                         
        elif rank_by == 'downloads':
            # Sort by download count
            return sorted(papers, 
                         key=lambda x: int(x.get('downloads', 0)), 
                         reverse=reverse)
                         
        elif rank_by == 'abstract_views':
            # Sort by abstract views
            return sorted(papers, 
                         key=lambda x: int(x.get('abstract_views', 0)), 
                         reverse=reverse)
                         
        elif rank_by == 'altmetric':
            # Sort by Altmetric score
            return sorted(papers, 
                         key=lambda x: int(x.get('altmetric_score', 0)), 
                         reverse=reverse)
                         
        elif rank_by == 'combined':
            # Sort by combined weighted score
            def combined_score(paper):
                metrics = paper.get('metrics', {})
                score = 0
                for metric, weight in rank_weights.items():
                    score += metrics.get(metric, 0) * weight
                return score
                
            return sorted(papers, key=combined_score, reverse=reverse)
            
        else:
            # Default to date if invalid ranking method
            logger.warning(f"Invalid ranking method '{rank_by}'. Using 'date' instead.")
            
            # Sort by publication date with safe handling of missing or invalid dates
            def safe_date_key(paper):
                date_str = paper.get('date')
                if not date_str:
                    # Use a very old date for missing dates when sorting in descending order (newest first)
                    # or a future date when sorting in ascending order (oldest first)
                    return datetime.datetime(1970, 1, 1) if reverse else datetime.datetime(2100, 1, 1)
                try:
                    return datetime.datetime.strptime(date_str, "%Y-%m-%d")
                except (ValueError, TypeError):
                    # If date string is invalid, use a default date
                    logger.warning(f"Invalid date format: {date_str}, using default date for sorting")
                    return datetime.datetime(1970, 1, 1) if reverse else datetime.datetime(2100, 1, 1)
            
            return sorted(papers, key=safe_date_key, reverse=reverse)
    
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
            # Ensure output directory exists
            output_dir = ensure_output_dir(output_dir)
            
            # Extract paper ID from DOI if available
            paper_id = None
            doi = paper.get('doi')
            if doi:
                # Use a more comprehensive regex to extract the complete paper identifier
                doi_match = re.search(r'10\.1101/([\d\.]+(?:v\d+)?)', doi)
                if doi_match:
                    paper_id = doi_match.group(1)
                    logger.debug(f"Extracted paper ID from DOI: {paper_id}")
            
            # Simplified URL construction - just use the direct URL or construct one standard URL
            direct_pdf_url = paper.get('pdf_url')
            pdf_url = None
            
            if direct_pdf_url:
                pdf_url = direct_pdf_url
                logger.debug(f"Using direct PDF URL from fallback search: {pdf_url}")
            elif paper_id:
                pdf_url = f"https://www.biorxiv.org/content/10.1101/{paper_id}.full.pdf"
                logger.debug(f"Using standard bioRxiv PDF URL: {pdf_url}")
            else:
                logger.error("No valid PDF URL could be constructed")
                return None
            
            logger.info(f"{Fore.BLUE}Downloading: {paper.get('title')}{Style.RESET_ALL}")
            
            # Add user-agent header to mimic a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.biorxiv.org/',
                'Accept': 'application/pdf, text/html, */*'
            }
            
            # Try to download the PDF
            try:
                logger.debug(f"Downloading from {pdf_url}")
                response = self.session.get(pdf_url, stream=True, headers=headers, verify=self.verify_ssl, timeout=30)
                response.raise_for_status()
                
                # Check if the response is actually a PDF
                content_type = response.headers.get('Content-Type', '')
                if 'application/pdf' not in content_type and 'pdf' not in content_type.lower():
                    logger.warning(f"Response is not a PDF (Content-Type: {content_type})")
                    if len(response.content) < 1000:  # Small response is likely an error page
                        logger.error(f"Response content too small, likely an error page")
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
                            sanitized_author = f"{name_parts[-1]} {name_parts[0][0]}"
                        else:
                            sanitized_author = author_name
                        
                    elif isinstance(authors[0], str):
                        name_parts = authors[0].split()
                        
                        if len(name_parts) > 1:
                            sanitized_author = f"{name_parts[-1]} {name_parts[0][0]}"
                        else:
                            sanitized_author = authors[0]
                        
                    # Handle other possible data structures
                    elif isinstance(authors[0], list):
                        if authors[0] and isinstance(authors[0][0], str):
                            name_parts = authors[0][0].split()
                            if len(name_parts) > 1:
                                sanitized_author = f"{name_parts[-1]} {name_parts[0][0]}"
                    else:
                        # Try to convert to string and extract
                        try:
                            author_str = str(authors[0])
                            if author_str and len(author_str) > 1:
                                name_parts = author_str.split()
                                if len(name_parts) > 1:
                                    sanitized_author = f"{name_parts[-1]} {name_parts[0][0]}"
                                else:
                                    sanitized_author = author_str
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
                sanitized_author = re.sub(r'[^\w\s-]', '', sanitized_author)
                
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
                
                # Save the PDF
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Verify the file was downloaded correctly
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    logger.info(f"{Fore.GREEN}Downloaded paper to: {filepath}{Style.RESET_ALL}")
                    return filepath
                else:
                    logger.warning(f"PDF file was created but appears to be empty: {filepath}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download from {pdf_url}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading paper: {e}")
            return None
