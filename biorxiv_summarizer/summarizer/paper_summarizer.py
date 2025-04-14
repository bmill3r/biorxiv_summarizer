#!/usr/bin/env python3
"""
Paper Summarizer Module

This module provides functionality to generate summaries of scientific papers.
"""

import os
import logging
import re
import math
import gc
import tempfile
from typing import Dict, Any, Optional, List, Union, Tuple
import PyPDF2
from openai import OpenAI
from colorama import Fore, Style
import tiktoken
import psutil

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
            Extracted text from the PDF or path to temporary file containing the text
        """
        logger.info(f"Extracting text from PDF: {pdf_path}")
        self.log_memory_usage("before PDF extraction")
        
        # Create a temporary directory for extracted text
        temp_dir = tempfile.mkdtemp(prefix="biorxiv_pdf_text_")
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
            
            # Instead of returning the entire text in memory, read it from the file
            # in the generate_summary method as needed
            self.log_memory_usage("after PDF extraction")
            
            # Read the entire file back into memory
            # We'll use a more memory-efficient approach in the future if needed
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
        chunk_dir = tempfile.mkdtemp(prefix="biorxiv_text_chunks_")
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
        
        # Format authors list with improved handling
        author_names = []
        
        # First try to extract from the authors list
        if isinstance(authors, list):
            for author in authors:
                if isinstance(author, dict):
                    # Try to get the name from the dictionary
                    author_name = author.get('name', '')
                    if author_name:
                        author_names.append(author_name)
                elif isinstance(author, str):
                    # If it's already a string, use it directly
                    if len(author.strip()) > 0:
                        author_names.append(author)
        elif isinstance(authors, str):
            # If authors is already a string, use it directly
            authors_text = authors
        
        # If we have author names from the list, join them
        if author_names:
            authors_text = ", ".join(author_names)
        elif not 'authors_text' in locals():
            # Fallback: try to extract from other metadata fields
            authors_text = paper_metadata.get('author', '')
            if not authors_text and 'authors_string' in paper_metadata:
                authors_text = paper_metadata.get('authors_string', '')
            if not authors_text:
                authors_text = "Unknown Authors"
        
        # Clean up common formatting issues
        # Fix individual characters separated by commas (e.g., "D, e, K, o, k, e, r")
        if re.search(r'\b[A-Za-z](,\s*[A-Za-z])+\b', authors_text):
            logger.warning("Detected possible character-by-character author formatting, attempting to fix")
            # Remove commas between single characters
            authors_text = re.sub(r'([A-Za-z]),\s*([A-Za-z])', r'\1\2', authors_text)
            # Clean up any remaining odd patterns
            authors_text = re.sub(r'\s*,\s*,\s*', ', ', authors_text)
            authors_text = re.sub(r'\s{2,}', ' ', authors_text)
        
        # Log the author formatting for debugging
        logger.info(f"Formatted authors: {authors_text}")
        
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
            # Default prompt based on scientific_paper_prompt.md
            prompt = """
            # Expert Analysis: {TITLE}

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
        prompt = prompt.replace("{AUTHORS}", authors_text).replace("{authors}", authors_text)
        prompt = prompt.replace("{ABSTRACT}", abstract).replace("{abstract}", abstract)
        prompt = prompt.replace("{DATE}", pub_date).replace("{date}", pub_date)
        prompt = prompt.replace("{DOI}", doi).replace("{doi}", doi)
        
        # Add additional placeholders that might be in the scientific_paper_prompt.md
        journal = paper_metadata.get('journal', 'bioRxiv (Preprint)')
        prompt = prompt.replace("{JOURNAL}", journal).replace("{journal}", journal)
        
        # Handle paper_text placeholder
        if "{paper_text}" in prompt:
            logger.info("Found {paper_text} placeholder in prompt, will replace with actual paper text")
        
        # Log that the prompt has been prepared
        logger.info(f"Prompt prepared with paper metadata (title, authors, etc.)")
        
        # System prompt for all API calls
        system_prompt = "You are a scientific research assistant tasked with summarizing bioRxiv preprints. Provide clear, concise, and accurate summaries that highlight the key findings, methods, strengths, limitations, and implications of the research."
        
        # User prompt prefix (metadata and instructions)
        user_prompt_prefix = f"{prompt}\n\nPaper Metadata:\nTitle: {title}\nAuthors: {authors_text}\nDate: {pub_date}\nDOI: {doi}\n\nAbstract:\n{abstract}"
        
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
        estimated_tokens = len(paper_text) / 4  # Rough estimate: ~4 chars per token
        logger.info(f"Estimated paper text tokens: ~{estimated_tokens:.0f} (based on character count)")
        
        # Log the API call
        logger.info(f"{Fore.BLUE}Generating summary using {self.model}{Style.RESET_ALL}")
        
        try:
            # Always calculate exact token count before deciding to chunk
            paper_tokens = self.num_tokens_from_string(paper_text, self.model)
            logger.info(f"Actual paper text tokens: {paper_tokens}")
            
            if paper_tokens <= max_chunk_tokens:
                # Process normally - paper fits within token limits
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
                logger.info(f"Paper exceeds token limits ({paper_tokens} tokens > {max_chunk_tokens} max). Processing in chunks.")
                self.log_memory_usage("before chunk processing")
                
                # Split the paper into chunks
                try:
                    chunks = self.chunk_text(paper_text, max_chunk_tokens, overlap_tokens=200)
                    logger.info(f"Split paper into {len(chunks)} chunks")
                    
                    # Free up the original paper text to save memory
                    del paper_text
                    gc.collect()
                    
                    # Check if we got any chunks
                    if not chunks:
                        # If chunking failed, fall back to a simple approach
                        logger.warning("Chunking failed or returned no chunks. Falling back to simplified summary.")
                        # Create a simple summary with just metadata
                        return self._create_fallback_summary(title, authors_text, abstract, pub_date, doi)
                except Exception as e:
                    logger.error(f"Error during chunking: {e}")
                    # Fall back to a simple summary with just metadata
                    return self._create_fallback_summary(title, authors_text, abstract, pub_date, doi)
                
                # Create a temporary directory for chunk summaries
                temp_dir = tempfile.mkdtemp(prefix="biorxiv_summary_")
                logger.info(f"Created temporary directory for chunk summaries: {temp_dir}")
                
                # Process each chunk and save to temporary files
                chunk_summary_files = []
                
                # Process chunks in smaller batches to reduce memory pressure
                batch_size = 3  # Process 3 chunks at a time
                for batch_start in range(0, len(chunks), batch_size):
                    batch_end = min(batch_start + batch_size, len(chunks))
                    # Silently process chunks without logging
                    
                    # Process each chunk in this batch
                    for i in range(batch_start, batch_end):
                        # Process each chunk silently
                        self.log_memory_usage(f"before processing chunk {i+1}")
                        
                        # Get the current chunk and immediately clear other chunks in memory
                        current_chunk = chunks[i]
                        
                        # Set all other chunks in this batch to None to free memory
                        for j in range(batch_start, batch_end):
                            if j != i:
                                chunks[j] = None
                        
                        # Force garbage collection
                        gc.collect()
                        
                        # Prepare chunk-specific prompt
                        if "{paper_text}" in user_prompt_prefix:
                            # If the prompt has a {paper_text} placeholder, use that
                            chunk_prompt = user_prompt_prefix.replace("{paper_text}", f"[PART {i+1} OF {len(chunks)}]\n{current_chunk}")
                        else:
                            # Otherwise append the chunk to the end
                            chunk_prompt = f"{user_prompt_prefix}\n\nNote: This is part {i+1} of {len(chunks)} of the paper.\n\nFull Text:\n{current_chunk}"
                        
                        try:
                            chunk_summary = self.generate_summary_for_chunk(
                                current_chunk, 
                                system_prompt, 
                                chunk_prompt,
                                max_tokens=1000
                            )
                            
                            # Write chunk summary to temporary file immediately
                            temp_file = os.path.join(temp_dir, f"chunk_{i+1}.txt")
                            with open(temp_file, 'w', encoding='utf-8') as f:
                                f.write(chunk_summary)
                            chunk_summary_files.append(temp_file)
                            logger.info(f"Saved chunk {i+1} summary to {temp_file}")
                            
                            # Free up memory immediately
                            del chunk_summary
                            del chunk_prompt
                            del current_chunk
                            gc.collect()
                            
                        except Exception as e:
                            logger.error(f"Error processing chunk {i+1}: {e}")
                            # Continue with other chunks
                        
                        self.log_memory_usage(f"after processing chunk {i+1}")
                    
                    # After processing this batch, force garbage collection again
                    gc.collect()
                    self.log_memory_usage(f"after batch {batch_start+1}-{batch_end}")
                
                # Free up chunks list completely
                del chunks
                gc.collect()
                self.log_memory_usage("after all chunks processed")
                
                # Combine chunk summaries into a final summary, but process in batches
                combined_summaries = ""
                batch_size = 5  # Process 5 files at a time
                
                for batch_start in range(0, len(chunk_summary_files), batch_size):
                    batch_end = min(batch_start + batch_size, len(chunk_summary_files))
                    logger.info(f"Combining summaries from files {batch_start+1}-{batch_end} of {len(chunk_summary_files)}")
                    
                    batch_summaries = ""
                    for i in range(batch_start, batch_end):
                        file_path = chunk_summary_files[i]
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                # Read in smaller segments to reduce memory pressure
                                file_content = ""
                                while True:
                                    segment = f.read(5000)  # Read 5KB at a time (reduced from 10KB)
                                    if not segment:
                                        break
                                    file_content += segment
                                batch_summaries += file_content + "\n\n"
                                
                                # Free memory
                                del file_content
                        except Exception as e:
                            logger.error(f"Error reading chunk summary file {file_path}: {e}")
                    
                    # Append batch summaries to combined summaries
                    combined_summaries += batch_summaries
                    
                    # Free memory
                    del batch_summaries
                    gc.collect()
                    self.log_memory_usage(f"after combining batch {batch_start+1}-{batch_end}")
                
                self.log_memory_usage("after combining summaries")
                
                # Clean up temporary files as soon as we're done with them
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Removed temporary directory: {temp_dir}")
                except Exception as e:
                    logger.error(f"Error removing temporary directory: {e}")
                
                # Generate a final consolidated summary
                self.log_memory_usage("before final consolidation")
                
                # Check if combined summaries is too large using character count as a rough estimate first
                # This avoids encoding the entire text at once which can use a lot of memory
                # Calculate estimated tokens without logging
                estimated_tokens = len(combined_summaries) / 4  # Rough estimate: ~4 chars per token
                
                # If it's likely to be too large based on the estimate, truncate it
                max_combined_tokens = 12000  # Maximum tokens for combined summaries
                max_combined_chars = max_combined_tokens * 4  # Rough estimate in characters
                
                if len(combined_summaries) > max_combined_chars:
                    logger.warning(f"Combined summaries likely too large (~{estimated_tokens:.0f} estimated tokens), truncating")
                    
                    # Truncate by preserving beginning and end based on character count first
                    # This is more memory efficient than encoding the entire text
                    first_part_size = int(max_combined_chars * 0.6)
                    last_part_size = max_combined_chars - first_part_size
                    
                    first_part = combined_summaries[:first_part_size]
                    last_part = combined_summaries[-last_part_size:]
                    
                    combined_summaries = first_part + "\n\n[...additional content omitted for length...]\n\n" + last_part
                    
                    # Free memory
                    del first_part, last_part
                    gc.collect()
                    
                    # Calculate actual token count without logging
                    actual_tokens = self.num_tokens_from_string(combined_summaries, self.model)
                    
                    # If it's still too large, do a more precise truncation with tokens
                    if actual_tokens > max_combined_tokens:
                        logger.warning(f"Still too large after character truncation ({actual_tokens} tokens), performing token-based truncation")
                        encoding = tiktoken.encoding_for_model(self.model)
                        tokens = encoding.encode(combined_summaries)
                        
                        # Take first 60% and last 40% of tokens
                        first_part_size = int(max_combined_tokens * 0.6)
                        last_part_size = max_combined_tokens - first_part_size
                        
                        first_part = encoding.decode(tokens[:first_part_size])
                        last_part = encoding.decode(tokens[-last_part_size:])
                        
                        combined_summaries = first_part + "\n\n[...additional content omitted for length...]\n\n" + last_part
                        
                        # Free memory
                        del tokens, first_part, last_part
                        gc.collect()
                else:
                    # If it's likely small enough, verify with actual token count
                    actual_tokens = self.num_tokens_from_string(combined_summaries, self.model)
                    logger.info(f"Actual combined summaries tokens: {actual_tokens}")
                
                # Use a consolidation prompt that preserves the original custom prompt structure
                if self.custom_prompt:
                    # If using a custom prompt, create a consolidation prompt that maintains its structure
                    consolidation_prompt = f"""You are provided with multiple summaries of different parts of the same scientific paper.
                    Your task is to combine these summaries into a single coherent analysis following EXACTLY the structure and format of the template below.
                    
                    Paper Information:
                    - Title: {title}
                    - Authors: {authors_text}
                    - DOI: {doi}
                    - Publication Date: {pub_date}
                    - Abstract: {abstract}
                    
                    Part Summaries (to be integrated):
                    {combined_summaries}
                    
                    OUTPUT TEMPLATE (follow this EXACT structure):
                    {prompt}
                    """
                else:
                    # Default consolidation prompt
                    consolidation_prompt = f"""You are provided with multiple summaries of different parts of the same scientific paper. 
                    Combine these summaries into a single coherent summary that covers all the key aspects of the paper.
                    Remove any redundancies and ensure the final summary is well-structured.
                    
                    Paper Title: {title}
                    Authors: {authors_text}
                    Abstract: {abstract}
                    
                    Part Summaries:
                    {combined_summaries}
                    """
                
                # Free memory before API call
                del combined_summaries
                gc.collect()
                self.log_memory_usage("before final API call")
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a scientific research assistant tasked with creating a comprehensive analysis of a scientific paper by combining multiple partial summaries. Follow the structure and format specified in the template EXACTLY."},
                            {"role": "user", "content": consolidation_prompt}
                        ],
                        temperature=self.temperature,
                        max_tokens=3000,
                    )
                    
                    # Free memory
                    del consolidation_prompt
                    gc.collect()
                    
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
    
    def _create_fallback_summary(self, title, authors, abstract, pub_date, doi):
        """Create a fallback summary when chunking or processing fails."""
        try:
            # Create a simple summary with just the metadata and abstract
            logger.info("Creating fallback summary with metadata and abstract")
            
            fallback_summary = f"# {title}\n\n"
            fallback_summary += f"**Authors:** {authors}\n\n"
            fallback_summary += f"**Publication Date:** {pub_date}\n\n"
            fallback_summary += f"**DOI:** {doi}\n\n"
            fallback_summary += f"**Abstract:** {abstract}\n\n"
            fallback_summary += "---\n\n"
            fallback_summary += "## Summary\n\n"
            fallback_summary += "*Note: This is a simplified summary based on the paper's abstract due to processing limitations.*\n\n"
            
            # Try to generate a brief summary from the abstract if possible
            try:
                system_prompt = "You are a scientific research assistant tasked with summarizing bioRxiv preprints based on their abstracts."
                user_prompt = f"Please provide a brief summary of the following scientific paper based on its abstract:\n\nTitle: {title}\nAuthors: {authors}\nAbstract: {abstract}"
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=1000,
                )
                
                abstract_summary = response.choices[0].message.content
                fallback_summary += abstract_summary
            except Exception as e:
                logger.error(f"Error generating abstract summary: {e}")
                fallback_summary += "Unable to generate a summary from the abstract due to an error.\n\n"
                fallback_summary += f"Please refer to the abstract above for information about this paper."
            
            return fallback_summary
            
        except Exception as e:
            logger.error(f"Error creating fallback summary: {e}")
            return f"# {title}\n\nUnable to generate summary due to processing errors."
    
    def __missing__(self, key):
        """Handle missing keys in prompt template."""
        return f"{{{key}}}"
