#!/usr/bin/env python3
"""
Setup script for the BioRxiv Summarizer package.
"""

from setuptools import setup, find_packages

setup(
    name="biorxiv_summarizer",
    version="1.0.0",
    description="Search bioRxiv for papers, download them, generate summaries, and upload to Google Drive",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "requests",
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        "openai",
        "python-dotenv",
        "PyPDF2",
        "colorama",
    ],
    entry_points={
        "console_scripts": [
            "biorxiv-summarizer=biorxiv_summarizer.cli:main",
        ],
    },
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering",
    ],
)
