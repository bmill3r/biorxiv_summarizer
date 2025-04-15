# PDF Processor

A Python package for extracting text from PDF files and generating AI-powered summaries.

## Overview

PDF Processor is a companion package to the BioRxiv Summarizer that provides functionality to:

1. Extract text from PDF files and save it as markdown
2. Generate comprehensive summaries of the extracted text using OpenAI API
3. Save both the extracted text and summaries to files

The package is designed to be memory-efficient, handling large PDFs by processing them page by page and chunking text for summarization when necessary.

## Installation

The PDF Processor is included as part of the BioRxiv Summarizer repository. All dependencies are already included in the main `requirements.txt` file.

```bash
pip install -r requirements.txt
```

## Configuration

### OpenAI API Key

To use the summarization functionality, you need an OpenAI API key. You can provide it in one of these ways:

1. Set it as an environment variable:
   ```bash
   export OPENAI_API_KEY=your-api-key
   ```

2. Add it to a `.env` file in the project root:
   ```
   OPENAI_API_KEY=your-api-key
   ```

3. Pass it directly when using the package:
   ```python
   processor = PDFProcessor(api_key="your-api-key")
   ```

## Usage

### Command Line Interface

The simplest way to use the PDF Processor is through its command-line interface. Here are examples for each processing mode:

#### Extract Mode (Text Extraction Only)

Use this mode when you only want to extract text from a PDF without generating a summary:

```bash
python pdf_processor_cli.py --pdf path/to/your/paper.pdf --mode extract --output-dir ./extracted_texts
```

This will extract the text from the PDF and save it as a markdown file in the specified output directory.

#### Summarize Mode (Summarization Only)

Use this mode when you already have extracted text and only want to generate a summary:

```bash
python pdf_processor_cli.py --pdf path/to/your/paper.pdf --mode summarize --output-dir ./summaries --model gpt-4o
```

This will extract text from the PDF (if needed) and then generate a summary using the specified OpenAI model.

#### Full Mode (Extract and Summarize)

Use this mode to perform both text extraction and summarization in one step:

```bash
python pdf_processor_cli.py --pdf path/to/your/paper.pdf --mode full --output-dir ./results
```

#### Adding Metadata

You can provide paper metadata to improve the summarization:

```bash
python pdf_processor_cli.py \
  --pdf path/to/your/paper.pdf \
  --mode full \
  --title "Important Research Paper" \
  --authors "Smith, J., Johnson, A." \
  --abstract "This paper explores..." \
  --journal "Journal of Example Research" \
  --date "2025-04-14" \
  --doi "10.1234/example.5678" \
  --output-dir ./results
```

#### Using a Custom Prompt

You can provide a custom prompt template for summarization:

```bash
python pdf_processor_cli.py \
  --pdf path/to/your/paper.pdf \
  --mode full \
  --prompt ./prompts/my_custom_prompt.md \
  --output-dir ./results
```

#### Command Line Options

- `--pdf`: Path to the PDF file (required)
- `--mode`: Processing mode (`extract`, `summarize`, or `full`)
- `--output-dir`: Directory to save output files (default: ./output)
- `--openai-key`: OpenAI API key (can also be set in .env)
- `--model`: OpenAI model to use (default: gpt-4o-mini)
- `--temperature`: Temperature for OpenAI API (0.0-1.0, default: 0.2)
- `--prompt`: Path to custom prompt template
- `--title`: Title of the paper (optional)
- `--authors`: Authors of the paper (optional)
- `--abstract`: Abstract of the paper (optional)
- `--journal`: Journal name (optional)
- `--date`: Publication date (optional)
- `--doi`: DOI of the paper (optional)
- `--verbose`: Enable verbose logging

### Python API

You can also use the PDF Processor programmatically in your Python code:

#### Example 1: Extract Text Only

```python
from pdf_processor import PDFProcessor

# Initialize the processor
processor = PDFProcessor(output_dir="./output")

# Extract text from a PDF
results = processor.process_pdf(
    pdf_path="path/to/paper.pdf",
    mode="extract"
)

# Print the path to the extracted text file
print(f"Extracted text saved to: {results['text_path']}")
```

#### Example 2: Generate Summary Only

```python
from pdf_processor import PDFProcessor
import os
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()

# Initialize the processor with custom settings
processor = PDFProcessor(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o",
    temperature=0.3,
    output_dir="./summaries"
)

# Add metadata about the paper
metadata = {
    "title": "Example Research Paper",
    "authors": "Smith, J., Johnson, A.",
    "abstract": "This paper explores...",
    "journal": "Journal of Example Research",
    "date": "2025-04-14",
    "doi": "10.1234/example.5678"
}

# Process a PDF that has already had its text extracted
with open("path/to/extracted_text.md", "r") as f:
    extracted_text = f.read()

# Generate summary
summary = processor.generate_summary(extracted_text, metadata)

# Save summary to file
output_path = os.path.join("./summaries", "example_summary.md")
processor.save_text_to_markdown(summary, output_path)
```

#### Example 3: Full Processing with Custom Prompt

```python
from pdf_processor import PDFProcessor

# Initialize the processor with a custom prompt
processor = PDFProcessor(
    custom_prompt_path="path/to/custom_prompt.md",
    model="gpt-4o-mini",
    output_dir="./results"
)

# Process PDF with full extraction and summarization
results = processor.process_pdf(
    pdf_path="path/to/paper.pdf",
    mode="full",
    metadata={
        "title": "Research on Topic X",
        "authors": "Various Authors"
    }
)

# Check for errors
if results.get("error"):
    print(f"Error: {results['error']}")
else:
    print(f"Extracted text: {results['text_path']}")
    print(f"Summary: {results['summary_path']}")
```

## Processing Modes

The PDF Processor supports three processing modes:

1. **Extract mode**: Only extracts text from PDFs and saves it as markdown
2. **Summarize mode**: Takes extracted text and submits it to OpenAI API with your prompt
3. **Full mode**: Does both extraction and summarization in one step

## Custom Prompts

You can provide a custom prompt template for the summarization. The template can include placeholders that will be replaced with the paper's metadata:

- `{title}` or `{TITLE}`: Paper title
- `{authors}` or `{AUTHORS}`: Paper authors
- `{abstract}` or `{ABSTRACT}`: Paper abstract
- `{date}` or `{DATE}`: Publication date
- `{doi}` or `{DOI}`: Paper DOI
- `{journal}` or `{JOURNAL}`: Journal name
- `{paper_text}`: The extracted text from the PDF

If no custom prompt is provided, a default scientific paper analysis prompt will be used.

## Error Handling

The PDF Processor includes robust error handling for common issues:

- PDF extraction failures
- API rate limiting and quota issues
- Memory constraints with large documents
- Path and file permission issues

All errors are logged and returned in the results dictionary.

## Memory Efficiency

The package is designed to be memory-efficient:

- PDFs are processed page by page
- Large texts are chunked for summarization
- Garbage collection is performed regularly
- Temporary files are used for very large documents

This allows processing of large scientific papers even on systems with limited memory.

## Integration with BioRxiv Summarizer

This package is designed to work alongside the BioRxiv Summarizer, sharing many of the same utilities and approaches. While the BioRxiv Summarizer focuses on searching, downloading, and processing papers from bioRxiv, the PDF Processor provides focused functionality for working with existing PDF files from any source.
