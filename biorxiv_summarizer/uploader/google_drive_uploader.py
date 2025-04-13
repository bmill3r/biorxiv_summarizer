#!/usr/bin/env python3
"""
Google Drive Uploader Module

This module provides functionality to upload files to Google Drive.
"""

import os
import io
import json
import logging
from typing import Optional
from colorama import Fore, Style

# Google Drive API libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

# Get logger
logger = logging.getLogger('biorxiv_summarizer')

# Define scopes for Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

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
        
        # Check if token.json exists (stored credentials)
        token_path = os.path.join(os.path.dirname(self.credentials_path), 'token.json')
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_info(
                    json.loads(open(token_path).read()), SCOPES)
            except Exception as e:
                logger.warning(f"Error loading stored credentials: {e}")
        
        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Error refreshing credentials: {e}")
                    creds = None
            
            # If still no valid credentials, run the OAuth flow
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                    
                    # Save credentials for future use
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                    logger.info(f"Credentials saved to {token_path}")
                except Exception as e:
                    logger.error(f"Error during authentication: {e}")
                    raise ValueError(f"Failed to authenticate with Google Drive: {e}")
        
        # Build the Drive service
        try:
            service = build('drive', 'v3', credentials=creds)
            logger.info(f"{Fore.GREEN}Successfully authenticated with Google Drive{Style.RESET_ALL}")
            return service
        except Exception as e:
            logger.error(f"Error building Drive service: {e}")
            raise ValueError(f"Failed to build Drive service: {e}")
    
    def create_folder(self, folder_name: str, parent_id: Optional[str] = None):
        """
        Create a folder in Google Drive.
        
        Args:
            folder_name: Name of the folder to create
            parent_id: ID of the parent folder (optional)
            
        Returns:
            ID of the created folder
        """
        try:
            # Check if folder already exists
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"
                
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            # If folder exists, return its ID
            if items:
                logger.info(f"Folder '{folder_name}' already exists")
                return items[0]['id']
            
            # Otherwise, create a new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            # Add parent folder if specified
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"{Fore.GREEN}Created folder: {folder_name} (ID: {folder_id}){Style.RESET_ALL}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Error creating folder: {e}")
            return None
    
    def upload_file(self, file_path: str, folder_id: Optional[str] = None):
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Path to the file to upload
            folder_id: ID of the folder to upload to (optional)
            
        Returns:
            ID of the uploaded file
        """
        try:
            # Get file name from path
            file_name = os.path.basename(file_path)
            
            # Create file metadata
            file_metadata = {'name': file_name}
            
            # Add parent folder if specified
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Create media
            media = MediaFileUpload(
                file_path,
                resumable=True
            )
            
            # Upload file
            logger.info(f"Uploading {file_name} to Google Drive...")
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            logger.info(f"{Fore.GREEN}Uploaded file: {file_name} (ID: {file_id}){Style.RESET_ALL}")
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None
    
    def upload_text_as_file(self, text: str, filename: str, folder_id: Optional[str] = None):
        """
        Upload text content as a file to Google Drive.
        
        Args:
            text: Text content to upload
            filename: Name for the file
            folder_id: ID of the folder to upload to (optional)
            
        Returns:
            ID of the uploaded file
        """
        try:
            # Create file metadata
            file_metadata = {'name': filename}
            
            # Add parent folder if specified
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Create media from text content
            media = MediaIoBaseUpload(
                io.BytesIO(text.encode('utf-8')),
                mimetype='text/plain',
                resumable=True
            )
            
            # Upload file
            logger.info(f"Uploading {filename} to Google Drive...")
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            logger.info(f"{Fore.GREEN}Uploaded file: {filename} (ID: {file_id}){Style.RESET_ALL}")
            
            return file_id
            
        except Exception as e:
            logger.error(f"Error uploading text file: {e}")
            return None
