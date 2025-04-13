"""
BioRxiv Paper Summarizer and Google Drive Uploader

This package:
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
"""

__version__ = "1.0.0"
