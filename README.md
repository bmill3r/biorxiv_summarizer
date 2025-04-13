# BioRxiv Paper Summarizer - Complete Guide

This tool automates the workflow for researchers to:
1. Search bioRxiv for the latest papers on chosen topics
2. Download the papers as PDFs
3. Generate comprehensive AI-powered summaries
4. Save both papers and summaries to your local directory or Google Drive

## Table of Contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Entry Points and Execution Options](#entry-points-and-execution-options)
- [Using Podman Container](#using-podman-container)
- [API Configuration](#api-configuration)
- [Basic Usage](#basic-usage)
- [Search Options](#search-options)
  - [Single Topic vs. Multiple Topics](#single-topic-vs-multiple-topics)
  - [Time Range and Result Limits](#time-range-and-result-limits)
  - [Author Search](#author-search)
    - [Basic Author Search](#basic-author-search)
    - [Multiple Authors](#multiple-authors)
    - [Combined Topic and Author Search](#combined-topic-and-author-search)
- [Ranking Options](#ranking-options)
- [Output Options](#output-options)
  - [Local Directory Storage](#local-directory-storage)
  - [Google Drive Integration](#google-drive-integration)
- [Summary Customization](#summary-customization)
  - [Using Custom Prompts](#using-custom-prompts)
  - [Available Placeholders](#available-placeholders)
  - [Example Custom Prompts](#example-custom-prompts)
- [Logging Features](#logging-features)
  - [Log Levels](#log-levels)
  - [Log to File](#log-to-file)
- [Advanced Usage Examples](#advanced-usage-examples)
- [FAQ](#faq)
  - [Topic Search Tips](#topic-search-tips)
  - [Common Issues](#common-issues)
- [Troubleshooting](#troubleshooting)

## Requirements

- Python 3.6 or higher
- OpenAI API key (for summary generation)
- Altmetric API key (optional, for social media impact ranking)
- Google Cloud account with Drive API enabled (optional, for Google Drive integration)

## Installation

You can install the package in two ways:

### Option 1: Install from source

1. Clone the repository:

```bash
git clone <repository-url>
cd biorxiv_summarizer
```

2. Install the package in development mode:

```bash
pip install -e .
```

### Option 2: Install dependencies only

If you prefer not to install the package, you can just install the dependencies:

```bash
pip install -r requirements.txt
```

The requirements include:
- requests
- google-api-python-client
- google-auth-httplib2
- google-auth-oauthlib
- openai
- python-dotenv
- PyPDF2

## Entry Points and Execution Options

There are multiple ways to run the BioRxiv Summarizer, depending on your preferences and environment:

### Option 1: Direct Script Execution
You can run the main script directly without installation:

```bash
python main.py --topic "your search topic"
```

This approach works in any environment where you have the required dependencies installed.

### Option 2: Package Installation
Install the package to get access to the command-line tool:

```bash
pip install -e .
```

After installation, you can use the command-line tool from anywhere:

```bash
biorxiv-summarizer --topic "your search topic"
```

This is the most convenient option for regular use, as it makes the tool available system-wide.

## Using Podman Container

The Podman container exists primarily to ensure environment stability and reproducibility. It's not required to use the tool, but it provides a consistent environment with all dependencies pre-installed.

### Setting Up Podman Container

1. Build a container image (create a Dockerfile first):

```bash
podman build -t biorxiv-summarizer .
```

2. Run the container with volume mounts to access your local filesystem:

```bash
podman run -it --rm \
  -v $(pwd):/app \
  -v /path/to/your/output/dir:/data \
  -v /path/to/your/credentials:/credentials \
  biorxiv-summarizer
```

This command does the following:
- Mounts the current directory to `/app` in the container (for code)
- Mounts your desired output directory to `/data` in the container
- Mounts your credentials directory to `/credentials` in the container

### Editing Code in the Container

To edit the code while the container is running:

1. Start the container in interactive mode:

```bash
podman run -it --rm \
  -v $(pwd):/app \
  -v /path/to/your/output/dir:/data \
  -v /path/to/your/credentials:/credentials \
  --entrypoint /bin/bash \
  biorxiv-summarizer
```

2. Inside the container, you can edit the files using a text editor like nano or vim:

```bash
apt-get update && apt-get install -y nano
nano /app/biorxiv_summarizer.py
```

3. Run the script with your changes:

(Not recommended)
```bash
python /app/biorxiv_summarizer.py --topic "CRISPR" --output_dir /data
```

or

(Recommended, installed with pip install -e .)
```bash
biorxiv-summarizer --topic "CRISPR" --output_dir /data
```

or

(Not installed with pip install -e .)
```bash
python main.py --topic "CRISPR" --output_dir /data
```

## API Configuration

### OpenAI API

1. Get an API key from [OpenAI](https://platform.openai.com/)
2. Create a `.env` file in the project directory with:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

Alternatively, you can pass the API key directly via environment variable:

```bash
export OPENAI_API_KEY=your_api_key_here

# Recommended (if installed with pip install -e .)
biorxiv-summarizer [options]

# Alternative (without installation)
python main.py [options]
```

### Altmetric API (Optional)

1. Request a free researcher API key from [Altmetric](https://www.altmetric.com/)
2. Add it to your `.env` file:
   ```
   ALTMETRIC_API_KEY=your_altmetric_key_here
   ```

Or pass it via command line:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --altmetric_key your_altmetric_key_here [other options]

# Alternative (without installation)
python main.py --altmetric_key your_altmetric_key_here [other options]
```

### Google Drive API (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Drive API" and enable it
4. Create OAuth credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" as the application type
   - Enter a name for your OAuth client
   - Click "Create"
5. Download the credentials JSON file
6. Rename the downloaded file to `credentials.json` and place it in the project directory

## Basic Usage

The simplest way to use the tool is:

```bash
# If installed as a package
biorxiv-summarizer --topic "your search topic"

# Or using the main.py script
python main.py --topic "your search topic"

# Or using the original script (still works but not recommended)
python biorxiv_summarizer.py --topic "your search topic"
```

This will:
1. Search for the 5 most recent papers on your topic from the last 30 days
2. Download them to a directory named "papers"
3. Generate summaries using the default prompt
4. Save summaries alongside the PDFs

## Search Options

### Single Topic vs. Multiple Topics

You can search using either a single topic or multiple topics:

**Single Topic Search:**
```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "CRISPR"

# Alternative (without installation)
python main.py --topic "CRISPR"
```

**Multiple Topics Search:**
```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "CRISPR" "gene editing" "off-target effects"

# Alternative (without installation)
python main.py --topics "CRISPR" "gene editing" "off-target effects"
```

By default, papers must match ALL specified topics. You can change this behavior:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "CRISPR" "gene editing" "off-target effects" --match any

# Alternative (without installation)
python main.py --topics "CRISPR" "gene editing" "off-target effects" --match any
```

This will return papers that match ANY of the specified topics.

### Time Range and Result Limits

Control how many papers and from what time period:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --max_papers 10 --days 60

# Alternative (without installation)
python main.py --topic "genomics" --max_papers 10 --days 60
```

This searches for papers published in the last 60 days and returns up to 10 results.

## Ranking Options

The tool provides several ways to rank the search results:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "neuroscience" --rank_by downloads

# Alternative (without installation)
python main.py --topic "neuroscience" --rank_by downloads
```

Available ranking methods:
- `date`: Sort by publication date (default)
- `downloads`: Sort by number of PDF downloads
- `abstract_views`: Sort by number of abstract views
- `altmetric`: Sort by Altmetric attention score (requires Altmetric API key)
- `combined`: Use a weighted combination of metrics

You can also specify the ranking direction:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "COVID-19" --rank_by downloads --rank_direction asc

# Alternative (without installation)
python main.py --topic "COVID-19" --rank_by downloads --rank_direction asc
```

For combined ranking, you can customize the weights:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "neuroscience" --rank_by combined \
  --weight_downloads 0.3 --weight_views 0.1 --weight_altmetric 0.5 --weight_twitter 0.1

# Alternative (without installation)
python main.py --topic "neuroscience" --rank_by combined \
  --weight_downloads 0.3 --weight_views 0.1 --weight_altmetric 0.5 --weight_twitter 0.1
```

## Output Options

### Local Directory Storage

By default, papers and summaries are saved to a directory named "papers" in the current working directory. You can specify a different directory:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "immunology" --output_dir "/path/to/your/directory"

# Alternative (without installation)
python main.py --topic "immunology" --output_dir "/path/to/your/directory"
```

Files are named with this format: `{date} - {first_author} - {short_title}.pdf` and `{date} - {first_author} - {short_title}.md` for the summary.

### Google Drive Integration

To save papers and summaries to Google Drive:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "epigenetics" --credentials "credentials.json"

# Alternative (without installation)
python main.py --topic "epigenetics" --credentials "credentials.json"
```

This will:
1. Open a browser window for Google authentication on first run
2. Create a folder named "BioRxiv Papers - {topic} - {date}"
3. Upload PDFs and summaries to this folder

You can also specify an existing Google Drive folder:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "proteomics" --credentials "credentials.json" \
  --drive_folder "your_folder_id_here"

# Alternative (without installation)
python main.py --topic "proteomics" --credentials "credentials.json" \
  --drive_folder "your_folder_id_here"
```

## Summary Customization

### Using Custom Prompts

You can customize how papers are summarized in two ways:

**1. File-based prompt:**
```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "CRISPR" --custom_prompt "scientific_paper_prompt.md"

# Alternative (without installation)
python main.py --topic "CRISPR" --custom_prompt "scientific_paper_prompt.md"
```

**2. Command-line prompt:**
```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --prompt_string "Analyze the paper {title} by {authors}. Focus on methodological strengths and weaknesses."

# Alternative (without installation)
python main.py --topic "genomics" --prompt_string "Analyze the paper {title} by {authors}. Focus on methodological strengths and weaknesses."
```

### Available Placeholders

Your custom prompts can include these placeholders:

- `{title}`: The paper's title
- `{authors}`: Comma-separated list of authors
- `{abstract}`: The paper's abstract
- `{doi}`: The paper's DOI
- `{date}`: The publication date
- `{paper_text}`: The extracted text from the paper (limited to first ~10,000 characters)

### Example Custom Prompts

#### 1. Focused Methodological Assessment

```
Please analyze the methodology of paper "{title}" by {authors}.

- What methods did they use?
- Are the methods appropriate for the research question?
- What are the strengths and weaknesses of the chosen approach?
- What alternative methods could have been used?

Paper text:
{paper_text}
```

#### 2. Educational Summary for Students

```
Create a pedagogical summary of "{title}" for undergraduate students.

Abstract: {abstract}

Paper content: {paper_text}

Your summary should:
1. Explain the key concepts in simple terms
2. Highlight the significance of the findings
3. Explain any technical terms
4. Connect the research to foundational concepts in biology
5. Suggest 3 discussion questions for a classroom setting
```

#### 3. Research Replication Assessment

```
Assess the replicability of the study "{title}" (DOI: {doi}) published on {date}.

Paper content: {paper_text}

Please analyze:
1. Are the methods described in sufficient detail to replicate?
2. Are all materials, data, and code accessible?
3. What potential barriers exist to replication?
4. Rate the overall replicability on a scale of 1-5, with justification
5. Suggest specific steps to improve replicability
```

#### 4. Cross-Paper Thematic Analysis

This prompt works well when you're processing multiple papers on the same topic:

```
Analyze paper "{title}" by {authors} as part of a thematic review of [YOUR TOPIC].

Abstract: {abstract}

Paper content: {paper_text}

Please identify:
1. How does this paper connect to the broader topic?
2. What unique perspective or data does it contribute?
3. How does it compare to other papers in this field?
4. What gaps remain to be addressed?
```

## Advanced Usage Examples

### 1. Comprehensive Literature Review Workflow

Get the most impactful papers on a topic, with custom summary format:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "single cell RNA-seq" "spatial transcriptomics" \
  --rank_by combined --max_papers 10 --days 90 \
  --custom_prompt "literature_review_template.md"

# Alternative (without installation)
python main.py --topics "single cell RNA-seq" "spatial transcriptomics" \
  --rank_by combined --max_papers 10 --days 90 \
  --custom_prompt "literature_review_template.md"
```

### 2. Educational Resource Creation

Find the most downloaded papers on a topic and generate student-friendly summaries:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genome editing" --rank_by downloads \
  --max_papers 5 --prompt_string "Create a beginner-friendly explanation of {title} for undergraduate students. Explain key concepts, significance, and implications."

# Alternative (without installation)
python main.py --topic "genome editing" --rank_by downloads \
  --max_papers 5 --prompt_string "Create a beginner-friendly explanation of {title} for undergraduate students. Explain key concepts, significance, and implications."
```

### 3. Field Monitoring with Multiple Models

For thorough analysis, you might run the tool with different models:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "protein structure prediction" --rank_by date \
  --model "gpt-4" --custom_prompt "expert_analysis.md"

# Alternative (without installation)
python main.py --topic "protein structure prediction" --rank_by date \
  --model "gpt-4" --custom_prompt "expert_analysis.md"
```

## FAQ

### Topic Search Tips

#### Why isn't my topic search returning any papers?

The topic search functionality has a few important characteristics to be aware of:

1. **Exact Matching**: By default, the tool searches for exact matches of your topics in the paper's metadata (title, abstract, category, etc.)

2. **ALL vs ANY Matching**: When using multiple topics, the default behavior requires ALL topics to be present in a paper's metadata

3. **Case Sensitivity**: Topic searches are case-insensitive, but special characters matter

If you're not getting results, try these approaches:

```bash
# Use broader or fewer terms
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "transcriptomics" --max_papers 1 --days 60
# Alternative (without installation)
python main.py --topics "transcriptomics" --max_papers 1 --days 60

# Use ANY matching instead of ALL
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "Computational Biology" "Bioinformatics" "Single-Cell Transcriptomics" --topic_match any --max_papers 1 --days 60
# Alternative (without installation)
python main.py --topics "Computational Biology" "Bioinformatics" "Single-Cell Transcriptomics" --topic_match any --max_papers 1 --days 60

# Increase the search window
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "Computational Biology" --days 90 --max_papers 5
# Alternative (without installation)
python main.py --topics "Computational Biology" --days 90 --max_papers 5

# Use fuzzy matching (matches similar terms)
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "RNA-seq" --fuzzy_match --max_papers 5
# Alternative (without installation)
python main.py --topics "RNA-seq" --fuzzy_match --max_papers 5
```

#### What text is being searched when I provide topics?

When you provide topics, the tool searches through:

1. Paper title and abstract
2. Category/subject tags (with higher weight)
3. Paper type and collection information
4. Tags or keywords
5. Author names

Sometimes the bioRxiv API might not classify papers with the exact terms you're searching for. For example, a paper might use "single cell RNA-seq" instead of "Single-Cell Transcriptomics".

### Common Issues

#### Special characters in search terms

If your search terms contain special characters like hyphens (e.g., "RNA-seq"), these might be interpreted as regex special characters. Use the `--fuzzy_match` option to handle these cases better.

#### Fuzzy matching

The `--fuzzy_match` parameter implements a more flexible topic matching system that helps find relevant papers even when the exact terms don't appear in the paper's metadata. Here's what it does:

- Word-by-word matching: Instead of requiring the entire topic phrase to match exactly, it breaks down each topic into individual words and looks for those words in the paper's metadata.
- Partial matching threshold: It considers a topic to be a match if at least 70% of the words in that topic are found in the paper's metadata.
- Special character handling: It replaces special characters (like hyphens in "RNA-seq") with a regex dot (.) which acts as a wildcard, allowing matches even when special characters are formatted differently.
- Short word skipping: Words shorter than 3 characters are automatically considered matches, as they're often not meaningful for search (like "of", "in", etc.).
For example, if you search for "Single-Cell Transcriptomics":

- Without fuzzy matching: The paper must contain this exact phrase
- With fuzzy matching: The paper only needs to contain most of the words "single", "cell", and "transcriptomics" in any form
This is particularly helpful for:

- Terms with special characters like "RNA-seq" or "single-cell"
- Variations in terminology (e.g., "transcriptomics" vs "transcriptomic analysis")
- Finding papers that use similar but not identical phrasing

#### No papers found with multiple specific topics

Requiring ALL topics to be present in a paper's metadata can be very restrictive. Try using `--topic_match any` to find papers that match at least one of your topics.

#### Getting too many irrelevant results

If you're getting too many papers that aren't relevant to your interests, try:

```bash
# Combine multiple specific topics with ALL matching
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "CRISPR" "gene therapy" "clinical trials" --topic_match all
# Alternative (without installation)
python main.py --topics "CRISPR" "gene therapy" "clinical trials" --topic_match all

# Combine topic and author search
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "CRISPR" --authors "Zhang F" --days 90
# Alternative (without installation)
python main.py --topics "CRISPR" --authors "Zhang F" --days 90
```

## Troubleshooting

### Google Drive Authentication Issues

If you encounter authentication issues with Google Drive:
1. Delete the `token.json` file
2. Run the script again to trigger a new authentication flow
3. Ensure your OAuth credentials haven't expired

### PDF Download Problems

If papers fail to download:
1. Check your internet connection
2. Verify the DOI exists by visiting `https://doi.org/{doi}`
3. Try a different search topic
4. Check if the output directory is writable

### Summary Generation Errors

If summary generation fails:
1. Verify your OpenAI API key
2. Check your OpenAI API usage limits
3. Try a different model (e.g., `--model "gpt-3.5-turbo"` instead of `gpt-4`)
4. Ensure your custom prompt has valid placeholders

### Permission Errors with Podman

If you encounter permission issues when using Podman:
1. Check the ownership of your mounted directories
2. Run Podman with user namespace remapping:
   ```bash
   podman run --userns=keep-id -it --rm -v $(pwd):/app ...
   ```
   
## Author Search

You can now search for papers by author name in addition to searching by topic:

### Basic Author Search

Search for papers by a specific author:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --author "Smith" --max_papers 3

# Alternative (without installation)
python main.py --author "Smith" --max_papers 3
``` 

### Multiple Authors

Search for papers by multiple authors:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --authors "Smith" "Johnson" "Lee" --max_papers 5

# Alternative (without installation)
python main.py --authors "Smith" "Johnson" "Lee" --max_papers 5
```

By default, papers matching ANY of the specified authors will be returned. To require ALL authors:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --authors "Smith" "Johnson" --author_match all

# Alternative (without installation)
python main.py --authors "Smith" "Johnson" --author_match all
```

### Combined Topic and Author Search

You can combine topic and author search to find papers that match both criteria:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --author "Smith"

# Alternative (without installation)
python main.py --topic "genomics" --author "Smith"
```

Or with multiple topics and authors:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topics "CRISPR" "gene editing" --authors "Zhang" "Doudna" --match any --author_match any

# Alternative (without installation)
python main.py --topics "CRISPR" "gene editing" --authors "Zhang" "Doudna" --match any --author_match any
```

In combined searches:
- `--match` controls how topics are matched (all/any)
- `--author_match` controls how authors are matched (all/any)

## Logging Features

The BioRxiv Summarizer includes enhanced logging capabilities with colored output for better readability:

### Log Levels

Control the verbosity of the output:

```bash
# Normal output (default)
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics"
# Alternative (without installation)
python main.py --topic "genomics"

# Verbose output with detailed information
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --verbose
# Alternative (without installation)
python main.py --topic "genomics" --verbose

# Quiet mode (only warnings and errors)
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --quiet
# Alternative (without installation)
python main.py --topic "genomics" --quiet
```

### Log to File

Save all logs to a file for later review:

```bash
# Recommended (if installed with pip install -e .)
biorxiv-summarizer --topic "genomics" --log-file "biorxiv_search.log"

# Alternative (without installation)
python main.py --topic "genomics" --log-file "biorxiv_search.log"
```

The log file will contain all log messages, regardless of the console verbosity level.
