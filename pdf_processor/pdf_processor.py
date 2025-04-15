#!/usr/bin/env python3
"""
PDF Processor Module

This module provides functionality to:
1. Extract text from PDF files
2. Generate summaries of the extracted text using OpenAI API
3. Save both the extracted text and summaries to files
"""

import os
import logging
import re
import math
import gc
import tempfile
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
import PyPDF2
from openai import OpenAI
from colorama import Fore, Style
import tiktoken
import psutil

# Get logger
logger = logging.getLogger('pdf_processor')

class PDFProcessor:
    """Class to extract text from PDFs and generate summaries."""
    
    def __init__(self, api_key: Optional[str] = None, custom_prompt_path: Optional[str] = None, 
                 temperature: float = 0.2, model: str = "gpt-4o-mini", output_dir: str = "./output"):
        """
        Initialize the PDF processor.
        
        Args:
            api_key: OpenAI API key (optional if set in environment)
            custom_prompt_path: Path to a file containing a custom prompt template (optional)
            temperature: Temperature setting for OpenAI API (0.0-1.0)
            model: OpenAI model to use for summarization (default: gpt-4o-mini)
            output_dir: Directory to save extracted text and summaries
        """
        # Use provided API key or get from environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        # Initialize OpenAI client if API key is provided
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        
        # Set temperature for API calls
        self.temperature = temperature
        
        # Set the model to use
        self.model = model
        
        # Set output directory
        self.output_dir = output_dir
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Load custom prompt if provided
        self.custom_prompt = None
        if custom_prompt_path:
            try:
                with open(custom_prompt_path, 'r', encoding='utf-8') as f:
                    self.custom_prompt = f.read()
                logger.info(f"Custom prompt loaded from {custom_prompt_path}")
                # Log the first 100 characters of the prompt to verify content
                preview = self.custom_prompt[:100] + "..." if len(self.custom_prompt) > 100 else self.custom_prompt
                logger.info(f"Custom prompt preview: {preview}")
            except Exception as e:
                logger.error(f"Error loading custom prompt: {e}")
                logger.info("Using default prompt instead.")
    
    def log_memory_usage(self, label: str = ""):
        """Calculate current memory usage of the process without logging to stdout."""
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        # Memory usage is now only returned, not logged
        return memory_mb
        
    def num_tokens_from_string(self, string: str, model: str = "gpt-3.5-turbo") -> int:
        """Returns the number of tokens in a text string."""
        encoding = tiktoken.encoding_for_model(model)
        num_tokens = len(encoding.encode(string))
        return num_tokens

    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 30) -> str:
        """
        Extract text from a PDF file using a file-based approach to minimize memory usage.
        
        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract
            
        Returns:
            Extracted text from the PDF
        """
        logger.info(f"Extracting text from PDF: {pdf_path}")
        self.log_memory_usage("before PDF extraction")
        
        # Create a temporary directory for extracted text
        temp_dir = tempfile.mkdtemp(prefix="pdf_text_")
        output_file = os.path.join(temp_dir, "extracted_text.txt")
        
        try:
            # Open the output file for writing
            with open(output_file, 'w', encoding='utf-8') as out_file:
                # Open the PDF file
                with open(pdf_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    num_pages = len(reader.pages)
                    
                    # Limit the number of pages to process
                    pages_to_process = min(num_pages, max_pages)
                    logger.info(f"Processing {pages_to_process} pages out of {num_pages} total")
                    
                    # Extract text from each page individually to minimize memory usage
                    batch_size = 1  # Process 1 page at a time for minimum memory usage
                    
                    for i in range(0, pages_to_process):
                        try:
                            logger.info(f"Processing page {i+1} of {pages_to_process}")
                            
                            # Extract text from this page
                            page = reader.pages[i]
                            page_text = page.extract_text()
                            
                            # Write directly to file
                            if page_text:
                                out_file.write(page_text)
                                out_file.write("\n\n")
                            
                            # Free memory immediately
                            del page
                            del page_text
                            
                            # Force garbage collection every few pages
                            if i % 3 == 0:
                                gc.collect()
                                
                        except Exception as e:
                            logger.warning(f"Error extracting text from page {i+1}: {e}")
            
            # Now read the file back in small chunks to check if we got any text
            with open(output_file, 'r', encoding='utf-8') as f:
                # Just check the first few bytes to see if there's any content
                sample = f.read(1000)
                if not sample.strip():
                    logger.warning("No text could be extracted from the PDF")
                    return ""
            
            # Read the entire file back into memory
            with open(output_file, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Clean up temporary files
            try:
                os.unlink(output_file)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")
                
            return text
                
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            
            # Clean up temporary files
            try:
                if os.path.exists(output_file):
                    os.unlink(output_file)
                os.rmdir(temp_dir)
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up temporary files: {cleanup_error}")
                
            return ""
    
    def save_text_to_markdown(self, text: str, output_path: str) -> bool:
        """
        Save extracted text to a markdown file.
        
        Args:
            text: The extracted text to save
            output_path: Path to save the markdown file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Write the text to the file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)
                
            logger.info(f"Saved extracted text to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving text to file: {e}")
            return False
            
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
        self.log_memory_usage("before chunking")
        
        # Use an extremely small segment size to minimize memory usage
        segment_size = 2000  # characters per segment (extremely small to prevent memory spikes)
        
        # If max_chunk_tokens is negative, set a reasonable default
        if max_chunk_tokens <= 0:
            logger.warning(f"Invalid max_chunk_tokens: {max_chunk_tokens}, setting to 2000")
            max_chunk_tokens = 2000
        
        # Estimate total tokens based on character count
        estimated_tokens = len(text) / 4  # Rough estimate: ~4 chars per token
        logger.info(f"Estimated tokens in text: ~{estimated_tokens:.0f} (based on character count)")
        
        # Check if we need to chunk at all
        if len(text) < max_chunk_tokens * 3:  # Using a conservative estimate
            # Create a temporary file to store the text
            temp_fd, temp_file = tempfile.mkstemp(suffix='.txt')
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                # Free the original text from memory
                del text
                gc.collect()
                
                # Now read the file in small chunks to check token count
                with open(temp_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Initialize encoding only when needed
                encoding = tiktoken.encoding_for_model(self.model)
                actual_tokens = len(encoding.encode(content))
                
                if actual_tokens <= max_chunk_tokens:
                    logger.info(f"Text fits in one chunk ({actual_tokens} tokens)")
                    return [content]  # No chunking needed
                    
                # If we get here, we need to chunk after all
                del content
                gc.collect()
                
            except Exception as e:
                logger.error(f"Error checking if chunking is needed: {e}")
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(temp_file)
                except Exception as e:
                    logger.error(f"Error removing temporary file: {e}")
        
        # If we get here, we need to chunk the text
        logger.info("Proceeding with text chunking")
        
        # Create a temporary directory to store chunks
        chunk_dir = tempfile.mkdtemp(prefix="pdf_text_chunks_")
        logger.info(f"Created temporary directory for text chunks: {chunk_dir}")
        
        # Process text in tiny segments to minimize memory usage
        chunk_files = []
        current_chunk = ""
        current_chunk_size = 0
        chunk_count = 0
        
        try:
            # Initialize encoding
            encoding = tiktoken.encoding_for_model(self.model)
            
            # Process text in very small segments
            for i in range(0, len(text), segment_size):
                # Log progress periodically
                if i % (segment_size * 10) == 0:
                    logger.info(f"Chunking progress: {i}/{len(text)} characters processed ({i/len(text)*100:.1f}%)")
                    self.log_memory_usage(f"during chunking at position {i}")
                
                # Get the current segment
                segment = text[i:i+segment_size]
                
                # Encode this segment to get token count
                segment_tokens = encoding.encode(segment)
                
                # Check if adding this segment would exceed the chunk size
                if current_chunk_size + len(segment_tokens) > max_chunk_tokens:
                    # Save the current chunk to a file
                    if current_chunk:
                        chunk_count += 1
                        chunk_file = os.path.join(chunk_dir, f"chunk_{chunk_count}.txt")
                        with open(chunk_file, 'w', encoding='utf-8') as f:
                            f.write(current_chunk)
                        chunk_files.append(chunk_file)
                        
                        # Reset current chunk
                        del current_chunk
                        current_chunk = ""
                        current_chunk_size = 0
                        gc.collect()
                
                # Add this segment to the current chunk
                current_chunk += segment
                current_chunk_size += len(segment_tokens)
                
                # Free memory
                del segment
                del segment_tokens
                gc.collect()
            
            # Save the last chunk if there's anything left
            if current_chunk:
                chunk_count += 1
                chunk_file = os.path.join(chunk_dir, f"chunk_{chunk_count}.txt")
                with open(chunk_file, 'w', encoding='utf-8') as f:
                    f.write(current_chunk)
                chunk_files.append(chunk_file)
            
            # Free the original text from memory completely
            del text
            del current_chunk
            gc.collect()
            
            # Now read the chunks back from files
            chunks = []
            for file_path in chunk_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        chunk_content = f.read()
                        chunks.append(chunk_content)
                except Exception as e:
                    logger.error(f"Error reading chunk file {file_path}: {e}")
            
            logger.info(f"Split text into {len(chunks)} chunks")
            self.log_memory_usage("after chunking")
            
            # Clean up temporary files
            for file_path in chunk_files:
                try:
                    os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Error removing chunk file {file_path}: {e}")
            
            try:
                os.rmdir(chunk_dir)
                logger.info(f"Removed temporary chunk directory: {chunk_dir}")
            except Exception as e:
                logger.error(f"Error removing temporary chunk directory: {e}")
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error during chunking: {e}")
            # Return an empty list in case of error
            return []

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
        if not self.client:
            raise ValueError("OpenAI API key is required for summarization. Set it as OPENAI_API_KEY environment variable or pass it directly.")
            
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt_prefix.replace("{paper_text}", chunk) if "{paper_text}" in user_prompt_prefix else f"{user_prompt_prefix}\n\nFull Text:\n{chunk}"}
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating chunk summary: {e}")
            raise e
    
    def _create_fallback_summary(self, title: str, metadata: Dict[str, Any]) -> str:
        """
        Create a fallback summary when chunking or processing fails.
        
        Args:
            title: Title of the paper
            metadata: Metadata about the paper
            
        Returns:
            A simple summary based on available metadata
        """
        fallback = f"# Summary of: {title}\n\n"
        fallback += "## Note\n\nThis is a simplified summary as the full text processing was not possible.\n\n"
        
        # Add metadata if available
        if metadata.get('authors'):
            fallback += f"**Authors:** {metadata.get('authors', 'Unknown')}\n\n"
        
        if metadata.get('abstract'):
            fallback += f"## Abstract\n\n{metadata.get('abstract', 'No abstract available')}\n\n"
        
        fallback += "## Processing Error\n\nThe full text could not be processed due to technical limitations. "
        fallback += "This summary contains only the metadata that was available.\n"
        
        return fallback
    
    def generate_summary(self, text: str, metadata: Dict[str, Any] = None) -> str:
        """
        Generate a comprehensive summary of a scientific paper text.
        
        Args:
            text: The extracted text from the PDF
            metadata: Optional metadata about the paper
            
        Returns:
            Generated summary of the paper
        """
        if not self.client:
            raise ValueError("OpenAI API key is required for summarization. Set it as OPENAI_API_KEY environment variable or pass it directly.")
        
        # Initialize metadata if not provided
        if metadata is None:
            metadata = {}
        
        # Extract title from metadata or use a default
        title = metadata.get('title', 'Unknown Title')
        
        # Prepare paper metadata for the prompt
        authors = metadata.get('authors', 'Unknown Authors')
        abstract = metadata.get('abstract', 'No abstract available')
        journal = metadata.get('journal', 'Unknown Journal')
        pub_date = metadata.get('date', 'Unknown Date')
        doi = metadata.get('doi', 'No DOI available')
        
        # Construct the prompt
        if self.custom_prompt:
            # Use custom prompt if provided
            prompt = self.custom_prompt
        else:
            # Default prompt based on scientific_paper_prompt.md
            prompt = """
            # Expert Analysis: {title}

            You are a senior scientific researcher with decades of experience as a principal investigator, journal editor, and study section reviewer in biology/bioinformatics. Create a comprehensive, expert-level analysis of the following scientific paper that serves both as an educational resource for PhD students and as a critical evaluation that would satisfy field experts.

            ## 1. Paper Context and Significance
            - **Research Domain:** [Identify the precise subfield classification]
            - **Scientific Question:** [Identify the specific scientific gap or question being addressed]
            - **Background Context:** [Provide brief historical context of this research question]
            - **Key Technologies/Methods:** [Describe core methodological approaches with technical specificity]

            ## 2. Accessible Summary for Early-Career Researchers
            [Provide a 3-4 paragraph explanation of the core research, written for a first-year PhD student. Balance accessibility with scientific precision. Define specialized terminology when first used. Highlight what makes this work novel or important in the broader context of the field.]

            ## 3. Key Findings and Contributions
            - **Primary Findings:** [List the most important results with quantitative details where relevant]
            - **Methodological Innovations:** [Describe any novel methods or techniques introduced]
            - **Conceptual Advances:** [Explain theoretical or conceptual contributions]
            - **Resource Generation:** [Note any datasets, tools, or resources produced]

            ## 4. Critical Analysis
            - **Strengths:** [Identify the major strengths of the paper]
            - **Limitations:** [Discuss methodological limitations, interpretative issues, or gaps]
            - **Alternative Interpretations:** [Consider alternative explanations for the findings]
            - **Unanswered Questions:** [Identify important questions left unaddressed]

            ## 5. Impact and Future Directions
            - **Field Impact:** [Assess how this work advances the field]
            - **Broader Implications:** [Consider implications beyond the immediate research area]
            - **Follow-up Studies:** [Suggest logical next steps for this research]
            - **Technical Improvements:** [Recommend methodological refinements]

            Format your analysis in Markdown with clear headings and bullet points where appropriate.
            """
        
        # Replace placeholders in the prompt - handle both formats {TITLE} and {title}
        prompt = prompt.replace("{TITLE}", title).replace("{title}", title)
        prompt = prompt.replace("{AUTHORS}", authors).replace("{authors}", authors)
        prompt = prompt.replace("{ABSTRACT}", abstract).replace("{abstract}", abstract)
        prompt = prompt.replace("{DATE}", pub_date).replace("{date}", pub_date)
        prompt = prompt.replace("{DOI}", doi).replace("{doi}", doi)
        prompt = prompt.replace("{JOURNAL}", journal).replace("{journal}", journal)
        
        # Handle paper_text placeholder
        if "{paper_text}" in prompt:
            logger.info("Found {paper_text} placeholder in prompt, will replace with actual paper text")
        
        # System prompt for all API calls
        system_prompt = "You are a scientific research assistant tasked with summarizing scientific papers. Provide clear, concise, and accurate summaries that highlight the key findings, methods, strengths, limitations, and implications of the research."
        
        # User prompt prefix (metadata and instructions)
        user_prompt_prefix = f"{prompt}\n\nPaper Metadata:\nTitle: {title}\nAuthors: {authors}\nDate: {pub_date}\nDOI: {doi}\n\nAbstract:\n{abstract}"
        
        # Calculate token counts
        system_tokens = self.num_tokens_from_string(system_prompt, self.model)
        prefix_tokens = self.num_tokens_from_string(user_prompt_prefix, self.model)
        
        # Reserve tokens for the response and some overhead
        reserved_tokens = 3000  # for the model's response
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
        
        # Estimate token count based on character count first to avoid memory spike
        estimated_tokens = len(text) / 4  # Rough estimate: ~4 chars per token
        logger.info(f"Estimated paper text tokens: ~{estimated_tokens:.0f} (based on character count)")
        
        # Log the API call
        logger.info(f"{Fore.BLUE}Generating summary using {self.model}{Style.RESET_ALL}")
        
        try:
            # Always calculate exact token count before deciding to chunk
            paper_tokens = self.num_tokens_from_string(text, self.model)
            logger.info(f"Actual paper text tokens: {paper_tokens}")
            
            if paper_tokens <= max_chunk_tokens:
                # Process normally - paper fits within token limits
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{user_prompt_prefix}\n\nFull Text:\n{text}"}
                    ],
                    temperature=self.temperature,
                    max_tokens=reserved_tokens,
                )
                
                summary = response.choices[0].message.content
            else:
                # Paper exceeds token limits - process in chunks
                logger.info(f"Paper exceeds token limits ({paper_tokens} tokens > {max_chunk_tokens} max). Processing in chunks.")
                self.log_memory_usage("before chunk processing")
                
                # Split the paper into chunks
                try:
                    chunks = self.chunk_text(text, max_chunk_tokens, overlap_tokens=200)
                    logger.info(f"Split paper into {len(chunks)} chunks")
                    
                    # Free up the original paper text to save memory
                    del text
                    gc.collect()
                    
                    # Check if we got any chunks
                    if not chunks:
                        # If chunking failed, fall back to a simple approach
                        logger.warning("Chunking failed or returned no chunks. Falling back to simplified summary.")
                        # Create a simple summary with just metadata
                        return self._create_fallback_summary(title, metadata)
                except Exception as e:
                    logger.error(f"Error during chunking: {e}")
                    # Fall back to a simple summary with just metadata
                    return self._create_fallback_summary(title, metadata)
                
                # Create a temporary directory for chunk summaries
                temp_dir = tempfile.mkdtemp(prefix="pdf_summary_")
                logger.info(f"Created temporary directory for chunk summaries: {temp_dir}")
                
                # Process each chunk and save to temporary files
                chunk_summary_files = []
                
                # Process chunks in smaller batches to reduce memory pressure
                batch_size = 3  # Process 3 chunks at a time
                for batch_start in range(0, len(chunks), batch_size):
                    batch_end = min(batch_start + batch_size, len(chunks))
                    
                    # Process each chunk in this batch
                    for i in range(batch_start, batch_end):
                        self.log_memory_usage(f"before processing chunk {i+1}")
                        
                        # Get the current chunk and immediately clear other chunks in memory
                        current_chunk = chunks[i]
                        
                        try:
                            # Generate summary for this chunk
                            chunk_summary = self.generate_summary_for_chunk(
                                current_chunk,
                                system_prompt,
                                user_prompt_prefix,
                                max_tokens=reserved_tokens
                            )
                            
                            # Save this chunk summary to a file
                            chunk_summary_file = os.path.join(temp_dir, f"summary_chunk_{i+1}.txt")
                            with open(chunk_summary_file, 'w', encoding='utf-8') as f:
                                f.write(chunk_summary)
                            chunk_summary_files.append(chunk_summary_file)
                            
                            # Free memory
                            del chunk_summary
                            gc.collect()
                            
                        except Exception as e:
                            logger.error(f"Error processing chunk {i+1}: {e}")
                        
                        # Free memory
                        del current_chunk
                        gc.collect()
                
                # Free chunks from memory
                del chunks
                gc.collect()
                
                # Combine the chunk summaries
                combined_summary = f"# Summary of: {title}\n\n"
                
                # Add metadata
                combined_summary += f"**Authors:** {authors}\n\n"
                if abstract:
                    combined_summary += f"**Abstract:** {abstract}\n\n"
                
                combined_summary += "## Combined Summary\n\n"
                combined_summary += "*This paper was processed in multiple chunks due to its length. The following is a combined summary of all chunks.*\n\n"
                
                # Read and combine all chunk summaries
                for i, file_path in enumerate(chunk_summary_files):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            chunk_content = f.read()
                        
                        # Add a section header for each chunk
                        combined_summary += f"### Chunk {i+1} Summary\n\n"
                        combined_summary += chunk_content
                        combined_summary += "\n\n---\n\n"
                        
                    except Exception as e:
                        logger.error(f"Error reading chunk summary file {file_path}: {e}")
                
                # Clean up temporary files
                for file_path in chunk_summary_files:
                    try:
                        os.unlink(file_path)
                    except Exception as e:
                        logger.error(f"Error removing chunk summary file {file_path}: {e}")
                
                try:
                    os.rmdir(temp_dir)
                    logger.info(f"Removed temporary summary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error removing temporary summary directory: {e}")
                
                summary = combined_summary
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return self._create_fallback_summary(title, metadata)
    
    def process_pdf(self, pdf_path: str, mode: str = "full", metadata: Dict[str, Any] = None, output_dir: str = None) -> Dict[str, str]:
        """
        Process a PDF file: extract text and/or generate summary.
        
        Args:
            pdf_path: Path to the PDF file
            mode: Processing mode ('extract', 'summarize', or 'full')
            metadata: Optional metadata about the paper
            output_dir: Directory to save output files (overrides self.output_dir if provided)
            
        Returns:
            Dictionary with paths to the extracted text and/or summary files
        """
        # Validate mode
        valid_modes = ['extract', 'summarize', 'full']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
        
        # Use provided output directory or default
        output_directory = output_dir or self.output_dir
        os.makedirs(output_directory, exist_ok=True)
        
        # Initialize results dictionary
        results = {
            'text_path': None,
            'summary_path': None,
            'error': None
        }
        
        # Get the base filename without extension
        base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Extract text if mode is 'extract' or 'full'
        extracted_text = None
        if mode in ['extract', 'full']:
            try:
                extracted_text = self.extract_text_from_pdf(pdf_path)
                
                if not extracted_text:
                    results['error'] = "Failed to extract text from PDF"
                    return results
                
                # Save extracted text to file
                text_path = os.path.join(output_directory, f"{base_filename}_text.md")
                if self.save_text_to_markdown(extracted_text, text_path):
                    results['text_path'] = text_path
                else:
                    results['error'] = "Failed to save extracted text to file"
                    return results
                    
            except Exception as e:
                results['error'] = f"Error extracting text: {str(e)}"
                return results
        
        # Generate summary if mode is 'summarize' or 'full'
        if mode in ['summarize', 'full']:
            try:
                # If we're in 'summarize' mode but don't have text yet, extract it
                if mode == 'summarize' and not extracted_text:
                    extracted_text = self.extract_text_from_pdf(pdf_path)
                    
                    if not extracted_text:
                        results['error'] = "Failed to extract text from PDF for summarization"
                        return results
                
                # Generate summary
                summary = self.generate_summary(extracted_text, metadata)
                
                # Save summary to file
                summary_path = os.path.join(output_directory, f"{base_filename}_summary.md")
                if self.save_text_to_markdown(summary, summary_path):
                    results['summary_path'] = summary_path
                else:
                    results['error'] = "Failed to save summary to file"
                    
            except Exception as e:
                results['error'] = f"Error generating summary: {str(e)}"
        
        return results
