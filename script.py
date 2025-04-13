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
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import argparse

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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
                print(f"No papers found for the date range {start_date} to {end_date}")
                return []
                
            # Filter papers based on topic
            matching_papers = []
            for paper in data['collection']:
                # Search in title, abstract, and authors
                searchable_text = (paper.get('title', '') + ' ' + 
                                  paper.get('abstract', '') + ' ' + 
                                  ' '.join(author.get('name', '') for author in paper.get('authors', [])))
                
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
            print(f"Error searching bioRxiv: {e}")
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
                
            # Construct a sanitized filename
            sanitized_title = re.sub(r'[^\w\s-]', '', paper.get('title', 'Unknown'))
            sanitized_title = re.sub(r'\s+', '_', sanitized_title)
            filename = f"{sanitized_title}.pdf"
            filepath = os.path.join(output_dir, filename)
            
            # bioRxiv PDF URL format
            pdf_url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
            
            print(f"Downloading: {paper.get('title')}")
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            print(f"Downloaded: {filepath}")
            return filepath
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading paper: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error downloading paper: {e}")
            return None

class PaperSummarizer:
    """Class to generate summaries of scientific papers."""
    
    def __init__(self, api_key: Optional[str] = None, custom_prompt_path: Optional[str] = None):
        """
        Initialize the paper summarizer.
        
        Args:
            api_key: OpenAI API key (optional if set in environment)
            custom_prompt_path: Path to a file containing a custom prompt template (optional)
        """
        # Use provided API key or get from environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set it as OPENAI_API_KEY environment variable or pass it directly.")
            
        openai.api_key = self.api_key
        
        # Load custom prompt if provided
        self.custom_prompt = None
        if custom_prompt_path:
            try:
                with open(custom_prompt_path, 'r', encoding='utf-8') as f:
                    self.custom_prompt = f.read()
                print(f"Custom prompt loaded from {custom_prompt_path}")
            except Exception as e:
                print(f"Error loading custom prompt: {e}")
                print("Using default prompt instead.")
    
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
            print(f"Error extracting text from PDF: {e}")
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
        print(f"Generating summary for: {paper_metadata.get('title', 'Unknown paper')}")
        
        # Extract text from PDF
        paper_text = self.extract_text_from_pdf(pdf_path)
        if not paper_text:
            return "Failed to extract text from the PDF."
            
        # Prepare the prompt for the AI
        title = paper_metadata.get('title', 'Unknown')
        authors = ', '.join([author.get('name', '') for author in paper_metadata.get('authors', [])])
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
            # Call the API for summarization
            response = openai.ChatCompletion.create(
                model="gpt-4",  # Use appropriate model
                messages=[
                    {"role": "system", "content": "You are a helpful scientific assistant skilled at summarizing academic papers for PhD students."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.2
            )
            
            summary = response['choices'][0]['message']['content']
            
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
            
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Failed to generate summary: {str(e)}"

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
    parser.add_argument("--topic", type=str, required=True, help="Topic to search for in bioRxiv")
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
    
    args = parser.parse_args()
    
    # Check for Altmetric API key if needed
    if args.rank_by in ['altmetric', 'combined'] and not args.altmetric_key:
        print("Warning: Altmetric API key is required for 'altmetric' or 'combined' ranking.")
        print("Altmetric scores will be set to 0. To use Altmetric data, provide --altmetric_key.")
    
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
        summarizer = PaperSummarizer(custom_prompt_path=custom_prompt_path)
        uploader = GoogleDriveUploader(args.credentials)
        
        # Step 2: Create main folder in Google Drive if needed
        drive_folder_id = args.drive_folder
        if not drive_folder_id:
            folder_name = f"BioRxiv Papers - {args.topic} - {datetime.datetime.now().strftime('%Y-%m-%d')}"
            drive_folder_id = uploader.create_folder(folder_name)
        
        # Step 3: Search for papers with ranking
        print(f"Searching and ranking papers by '{args.rank_by}' ({args.rank_direction}ending)...")
        papers = searcher.search_recent_papers(
            topic=args.topic,
            max_results=args.max_papers,
            days_back=args.days,
            rank_by=args.rank_by,
            rank_direction=args.rank_direction,
            rank_weights=rank_weights
        )
        
        if not papers:
            print("No papers found matching the criteria.")
            return
        
        # Step 4: Process each paper
        for paper in papers:
            title = paper.get('title', 'Unknown')
            print(f"\nProcessing paper: {title}")
            
            # Download paper
            pdf_path = searcher.download_paper(paper, args.output_dir)
            if not pdf_path:
                print(f"Failed to download paper: {title}")
                continue
            
            # Generate summary
            summary = summarizer.generate_summary(pdf_path, paper)
            
            # Save summary to a file
            sanitized_title = re.sub(r'[^\w\s-]', '', title)
            sanitized_title = re.sub(r'\s+', '_', sanitized_title)
            summary_filename = f"{sanitized_title}_summary.md"
            summary_path = os.path.join(args.output_dir, summary_filename)
            
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            print(f"Saved summary to: {summary_path}")
            
            # Upload the paper and its summary to Google Drive
            uploader.upload_file(pdf_path, drive_folder_id)
            uploader.upload_file(summary_path, drive_folder_id)
        
        print("\nWorkflow complete!")
    
    finally:
        # Clean up temporary prompt file if created
        if temp_prompt_file and os.path.exists(temp_prompt_file):
            try:
                os.remove(temp_prompt_file)
                print(f"Temporary prompt file removed: {temp_prompt_file}")
            except Exception as e:
                print(f"Warning: Could not remove temporary prompt file {temp_prompt_file}: {e}")

    
    if not papers:
        print("No papers found matching the criteria.")
        return
    
    # Step 4: Process each paper
    for paper in papers:
        title = paper.get('title', 'Unknown')
        print(f"\nProcessing paper: {title}")
        
        # Download paper
        pdf_path = searcher.download_paper(paper, args.output_dir)
        if not pdf_path:
            print(f"Failed to download paper: {title}")
            continue
        
        # Generate summary
        summary = summarizer.generate_summary(pdf_path, paper)
        
        # Save summary to a file
        sanitized_title = re.sub(r'[^\w\s-]', '', title)
        sanitized_title = re.sub(r'\s+', '_', sanitized_title)
        summary_filename = f"{sanitized_title}_summary.md"
        summary_path = os.path.join(args.output_dir, summary_filename)
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Saved summary to: {summary_path}")
        
        # Upload the paper and its summary to Google Drive
        uploader.upload_file(pdf_path, drive_folder_id)
        uploader.upload_file(summary_path, drive_folder_id)
    
    print("\nWorkflow complete!")

if __name__ == "__main__":
    main()
    