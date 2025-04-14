# BioRxiv Paper Summarizer and Google Drive Uploader

This tool creates an automated workflow for researchers to:
1. Search bioRxiv for the latest papers on a chosen topic
2. Download the papers as PDFs
3. Generate comprehensive summaries including strengths, weaknesses, and field impact
4. Save both the papers and summaries to a specified Google Drive folder

## Requirements

- Python 3.6 or higher
- Google account with Google Drive
- OpenAI API key (for the summary generation)
- Google Cloud project with Drive API enabled

## Setup Instructions

### 1. Install Required Python Packages

```bash
pip install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib openai python-dotenv PyPDF2
```

### 2. Configure Google Drive API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API:
   - In the sidebar, click on "APIs & Services" > "Library"
   - Search for "Google Drive API" and enable it
4. Create OAuth credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" as the application type
   - Enter a name for your OAuth client
   - Click "Create"
5. Download the credentials JSON file
6. Rename the downloaded file to `credentials.json` and place it in the same directory as the script

### 3. Configure OpenAI API

1. Get an API key from [OpenAI](https://platform.openai.com/)
2. Create a `.env` file in the same directory as the script with the following content:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

## Usage

The script provides several command-line options for customization:

```bash
python biorxiv_summarizer.py --topic "your search topic" [options]
```

### Command-Line Options

#### Basic Options:
- `--topic`: (Required) The topic to search for in bioRxiv
- `--max_papers`: Maximum number of papers to process (default: 5)
- `--days`: Number of days to look back for papers (default: 30)
- `--credentials`: Path to Google Drive API credentials (default: "credentials.json")
- `--output_dir`: Directory to save downloaded papers locally (default: "papers")
- `--drive_folder`: Google Drive folder ID to upload to (creates new if not specified)

#### Ranking Options:
- `--rank_by`: How to rank papers (default: "date")
  - `date`: Sort by publication date
  - `downloads`: Sort by PDF download count
  - `abstract_views`: Sort by number of abstract views
  - `altmetric`: Sort by Altmetric attention score
  - `combined`: Use a weighted combination of metrics
- `--rank_direction`: Ranking direction (default: "desc")
  - `desc`: Descending order (highest first)
  - `asc`: Ascending order (lowest first)
- `--altmetric_key`: Altmetric API key (required for altmetric ranking)

#### Custom Summary Options:
- `--custom_prompt`: Path to a file containing a custom prompt template for paper summarization
- `--prompt_string`: Custom prompt string for paper summarization (alternative to --custom_prompt)

### Custom Summary Templates

The script now supports custom prompts for generating paper summaries. You can provide a custom prompt in two ways:

1. As a file path with `--custom_prompt`:
```bash
python biorxiv_summarizer.py --topic "neuroscience" --custom_prompt "my_prompt_template.txt"
```

2. Directly as a string with `--prompt_string`:
```bash
python biorxiv_summarizer.py --topic "genomics" --prompt_string "Analyze this paper {title} by {authors}..."
```

Your custom prompt can include the following placeholders that will be replaced with actual paper data:
- `{title}`: The paper's title
- `{authors}`: Comma-separated list of authors
- `{abstract}`: The paper's abstract
- `{doi}`: The paper's DOI
- `{date}`: The publication date
- `{paper_text}`: The extracted text from the paper (limited to first ~10,000 characters)

### Examples

1. Basic search by date (most recent first):
```bash
python biorxiv_summarizer.py --topic "CRISPR" --max_papers 3 --days 14
```

2. Find the most downloaded papers on a topic:
```bash
python biorxiv_summarizer.py --topic "genomics" --rank_by downloads --max_papers 3
```

3. Find papers with the highest social media impact:
```bash
python biorxiv_summarizer.py --topic "COVID-19" --rank_by altmetric --altmetric_key YOUR_API_KEY
```

4. Use a custom weighted ranking:
```bash
python biorxiv_summarizer.py --topic "neuroscience" --rank_by combined --altmetric_key YOUR_API_KEY --weight_downloads 0.3 --weight_views 0.1 --weight_altmetric 0.5 --weight_twitter 0.1
```

### Note on Altmetric API

To use the `altmetric` or `combined` ranking options effectively, you'll need an Altmetric API key. You can request a free researcher API key from Altmetric by describing your project. Without an API key, Altmetric scores will be set to 0, but the script will still function using other available metrics.

## Summary Format

Each generated summary includes:

1. Paper metadata (title, authors, DOI, publication date)
2. Original abstract
3. Key findings and contributions
4. Methodology overview
5. Main results and their implications
6. Strengths of the paper
7. Limitations and weaknesses
8. How the paper advances the field
9. Potential future research directions

## First-Time Authentication

When you run the script for the first time, it will:
1. Open a browser window asking you to sign in to your Google account
2. Ask for permission to access your Google Drive
3. After granting permission, the script will save a token file for future runs

## Customization

You can modify the `generate_summary` method in the `PaperSummarizer` class to adjust the prompt or summary format according to your needs.

## Troubleshooting

- If you encounter authentication issues with Google Drive, delete the `token.json` file and run the script again
- If the script fails to download papers, check your internet connection or try a different search topic
- If summary generation fails, check your OpenAI API key and usage limits

## Disclaimer

This tool uses the OpenAI API for generating summaries, which may incur costs based on your API usage. Please be aware of OpenAI's pricing structure.

The summaries are generated automatically and may miss nuances or misinterpret certain aspects of the papers. Always refer to the original papers for critical research work.
