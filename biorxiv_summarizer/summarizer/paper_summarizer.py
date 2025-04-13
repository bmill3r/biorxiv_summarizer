#!/usr/bin/env python3
"""
Paper Summarizer Module

This module provides functionality to generate summaries of scientific papers.
"""

import os
import logging
import re
import math
from typing import Dict, Any, Optional, List, Union, Tuple
import PyPDF2
from openai import OpenAI
from colorama import Fore, Style
import tiktoken

# Get logger
logger = logging.getLogger('biorxiv_summarizer')

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
    
    def num_tokens_from_string(self, string: str, model: str = "gpt-3.5-turbo") -> int:
        """Returns the number of tokens in a text string."""
        encoding = tiktoken.encoding_for_model(model)
        num_tokens = len(encoding.encode(string))
        return num_tokens

    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 30) -> str:
        """
        Extract text from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract
            
        Returns:
            Extracted text from the PDF
        """
        logger.info(f"Extracting text from PDF: {pdf_path}")
        
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                num_pages = len(reader.pages)
                
                # Limit the number of pages to process
                pages_to_process = min(num_pages, max_pages)
                logger.info(f"Processing {pages_to_process} pages out of {num_pages} total")
                
                # Extract text from each page
                text = ""
                for i in range(pages_to_process):
                    try:
                        page = reader.pages[i]
                        text += page.extract_text() + "\n\n"
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {i}: {e}")
                
                # Check if we got any meaningful text
                if not text.strip():
                    logger.warning("No text could be extracted from the PDF")
                    return ""
                
                # We don't truncate here anymore - we'll handle token limits in the generate_summary method
                return text
                
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return ""
    
    def chunk_text(self, text: str, max_chunk_tokens: int, overlap_tokens: int = 100) -> List[str]:
        """
        Split text into chunks that fit within token limits.
        
        Args:
            text: The text to split into chunks
            max_chunk_tokens: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
            
        Returns:
            List of text chunks
        """
        # Estimate tokens (approximate - actual tokenization may vary)
        encoding = tiktoken.encoding_for_model(self.model)
        tokens = encoding.encode(text)
        total_tokens = len(tokens)
        
        logger.info(f"Total tokens in text: {total_tokens}")
        
        if total_tokens <= max_chunk_tokens:
            return [text]  # No chunking needed
        
        chunks = []
        start_idx = 0
        
        while start_idx < total_tokens:
            # Calculate end index for this chunk
            end_idx = min(start_idx + max_chunk_tokens, total_tokens)
            
            # Decode the chunk back to text
            chunk_tokens = tokens[start_idx:end_idx]
            chunk = encoding.decode(chunk_tokens)
            chunks.append(chunk)
            
            # Move start index for next chunk, with overlap
            start_idx = end_idx - overlap_tokens
            if start_idx >= total_tokens:
                break
        
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

    def generate_summary_for_chunk(self, chunk: str, system_prompt: str, user_prompt_prefix: str, max_tokens: int = 1000) -> str:
        """
        Generate a summary for a single chunk of text.
        
        Args:
            chunk: Text chunk to summarize
            system_prompt: System prompt for the API call
            user_prompt_prefix: Prefix for the user prompt (metadata, etc.)
            max_tokens: Maximum tokens for the response
            
        Returns:
            Summary of the chunk
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{user_prompt_prefix}\n\nFull Text:\n{chunk}"}
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating chunk summary: {e}")
            raise e

    def generate_summary(self, pdf_path: str, paper_metadata: Dict[str, Any]) -> Union[str, Dict[str, str]]:
        """
        Generate a comprehensive summary of a scientific paper.
        
        Args:
            pdf_path: Path to the PDF file
            paper_metadata: Metadata about the paper
            
        Returns:
            Generated summary of the paper or error information
        """
        # Extract text from PDF
        paper_text = self.extract_text_from_pdf(pdf_path)
        
        if not paper_text:
            logger.error("Failed to extract text from PDF")
            return {"error": "extraction_failed", "message": "Failed to extract text from PDF"}
        
        # Prepare paper metadata for the prompt
        title = paper_metadata.get('title', 'Unknown Title')
        authors = paper_metadata.get('authors', [])
        
        # Format authors list
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                author_name = author.get('name', '')
                if author_name:
                    author_names.append(author_name)
            elif isinstance(author, str):
                author_names.append(author)
        
        authors_text = ", ".join(author_names) if author_names else "Unknown Authors"
        
        # Get abstract
        abstract = paper_metadata.get('abstract', 'No abstract available')
        
        # Get publication date
        pub_date = paper_metadata.get('date', 'Unknown Date')
        
        # Get DOI
        doi = paper_metadata.get('doi', 'No DOI available')
        
        # Construct the prompt
        if self.custom_prompt:
            # Use custom prompt if provided
            prompt = self.custom_prompt
        else:
            # Default prompt
            prompt = """
            # Scientific Paper Summary

            Please provide a comprehensive summary of the following scientific paper. Include:

            1. **Key Findings**: What are the main results and conclusions?
            2. **Methodology**: What methods did the authors use?
            3. **Strengths**: What are the strengths of this paper?
            4. **Limitations**: What are the limitations or weaknesses?
            5. **Implications**: How might this research impact the field?
            6. **Future Directions**: What future research does this paper suggest?

            Format the summary in Markdown with clear headings and bullet points where appropriate.
            """
        
        # Replace placeholders in the prompt
        prompt = prompt.replace("{TITLE}", title)
        prompt = prompt.replace("{AUTHORS}", authors_text)
        prompt = prompt.replace("{ABSTRACT}", abstract)
        prompt = prompt.replace("{DATE}", pub_date)
        prompt = prompt.replace("{DOI}", doi)
        
        # System prompt for all API calls
        system_prompt = "You are a scientific research assistant tasked with summarizing bioRxiv preprints. Provide clear, concise, and accurate summaries that highlight the key findings, methods, strengths, limitations, and implications of the research."
        
        # User prompt prefix (metadata and instructions)
        user_prompt_prefix = f"{prompt}\n\nPaper Metadata:\nTitle: {title}\nAuthors: {authors_text}\nDate: {pub_date}\nDOI: {doi}\n\nAbstract:\n{abstract}"
        
        # Calculate token counts
        system_tokens = self.num_tokens_from_string(system_prompt, self.model)
        prefix_tokens = self.num_tokens_from_string(user_prompt_prefix, self.model)
        
        # Reserve tokens for the response and some overhead
        reserved_tokens = 4000  # for the model's response
        overhead_tokens = 100   # for formatting, etc.
        
        # Calculate maximum tokens available for the paper text
        model_max_tokens = 16000 if "gpt-4" in self.model else 4000  # Adjust based on the model
        if "32k" in self.model:
            model_max_tokens = 32000
        elif "16k" in self.model:
            model_max_tokens = 16000
        
        max_chunk_tokens = model_max_tokens - system_tokens - prefix_tokens - reserved_tokens - overhead_tokens
        
        logger.info(f"Model max tokens: {model_max_tokens}")
        logger.info(f"System prompt tokens: {system_tokens}")
        logger.info(f"User prefix tokens: {prefix_tokens}")
        logger.info(f"Available tokens for paper text: {max_chunk_tokens}")
        
        # Check if we need to chunk the text
        paper_tokens = self.num_tokens_from_string(paper_text, self.model)
        logger.info(f"Paper text tokens: {paper_tokens}")
        
        # Log the API call
        logger.info(f"{Fore.BLUE}Generating summary using {self.model}{Style.RESET_ALL}")
        
        try:
            if paper_tokens <= max_chunk_tokens:
                # Paper fits within token limits - process normally
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{user_prompt_prefix}\n\nFull Text:\n{paper_text}"}
                    ],
                    temperature=self.temperature,
                    max_tokens=reserved_tokens,
                )
                
                summary = response.choices[0].message.content
            else:
                # Paper exceeds token limits - process in chunks
                logger.info(f"Paper exceeds token limits. Processing in chunks.")
                
                # Split the paper into chunks
                chunks = self.chunk_text(paper_text, max_chunk_tokens, overlap_tokens=200)
                logger.info(f"Split paper into {len(chunks)} chunks")
                
                # Process each chunk
                chunk_summaries = []
                for i, chunk in enumerate(chunks):
                    logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                    chunk_prompt = f"{user_prompt_prefix}\n\nNote: This is part {i+1} of {len(chunks)} of the paper."
                    
                    try:
                        chunk_summary = self.generate_summary_for_chunk(
                            chunk, 
                            system_prompt, 
                            chunk_prompt,
                            max_tokens=1000
                        )
                        chunk_summaries.append(chunk_summary)
                    except Exception as e:
                        logger.error(f"Error processing chunk {i+1}: {e}")
                        # Continue with other chunks
                
                # Combine chunk summaries into a final summary
                combined_summaries = "\n\n".join(chunk_summaries)
                
                # Generate a final consolidated summary
                consolidation_prompt = f"""You are provided with multiple summaries of different parts of the same scientific paper. 
                Combine these summaries into a single coherent summary that covers all the key aspects of the paper.
                Remove any redundancies and ensure the final summary is well-structured.
                
                Paper Title: {title}
                Authors: {authors_text}
                Abstract: {abstract}
                
                Part Summaries:
                {combined_summaries}
                """
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a scientific research assistant tasked with creating a coherent summary from multiple partial summaries of a scientific paper."},
                            {"role": "user", "content": consolidation_prompt}
                        ],
                        temperature=self.temperature,
                        max_tokens=3000,
                    )
                    
                    summary = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"Error consolidating summaries: {e}")
                    # Fall back to just concatenating the summaries
                    summary = "# Combined Summary from Multiple Parts\n\n" + combined_summaries
            
            # Add paper metadata as a header
            final_summary = f"# {title}\n\n"
            final_summary += f"**Authors:** {authors_text}\n\n"
            final_summary += f"**Publication Date:** {pub_date}\n\n"
            final_summary += f"**DOI:** {doi}\n\n"
            final_summary += f"**Abstract:** {abstract}\n\n"
            final_summary += "---\n\n"
            final_summary += summary
            
            logger.info(f"{Fore.GREEN}Summary generated successfully{Style.RESET_ALL}")
            
            return final_summary
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error generating summary: {error_message}")
            
            # Check for specific error types
            if "quota" in error_message.lower() or "limit" in error_message.lower():
                return {"error": "quota_exceeded", "message": error_message}
            elif "rate" in error_message.lower():
                return {"error": "rate_limit", "message": error_message}
            else:
                return {"error": "api_error", "message": error_message}
    
    def __missing__(self, key):
        """Handle missing keys in prompt template."""
        return f"{{{key}}}"
