"""
User Integrations Service
Handles per-user OAuth tokens and API credentials storage in BigQuery
for multi-tenant SaaS architecture
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from google.cloud import bigquery
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from config import config

logger = logging.getLogger(__name__)

PROJECT_ID = "invoicereader-477008"
DATASET_ID = "vendors_ai"
TABLE_ID = "user_integrations"
FULL_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"


class UserIntegrationsService:
    """
    Service for managing per-user integration credentials in BigQuery
    Supports Gmail OAuth tokens and NetSuite OAuth 1.0a credentials
    """
    
    def __init__(self):
        """Initialize BigQuery client"""
        credentials = None
        
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        
        if not credentials:
            raise ValueError("BigQuery service account credentials not found")
        
        self.client = bigquery.Client(
            credentials=credentials,
            project=PROJECT_ID
        )
        
        logger.info("UserIntegrationsService initialized")
    
    def _ensure_table_exists(self):
        """Ensure the user_integrations table exists"""
        try:
            self.client.get_table(FULL_TABLE_ID)
            return True
        except Exception as e:
            if "Not found" in str(e):
                logger.warning(f"Table {FULL_TABLE_ID} not found. Creating...")
                schema = [
                    bigquery.SchemaField("integration_id", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("owner_email", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("integration_type", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("credentials", "JSON", mode="NULLABLE"),
                    bigquery.SchemaField("access_token", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("refresh_token", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("token_expiry", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("is_connected", "BOOLEAN", mode="NULLABLE"),
                    bigquery.SchemaField("last_used", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
                ]
                table = bigquery.Table(FULL_TABLE_ID, schema=schema)
                table = self.client.create_table(table)
                logger.info(f"Created table {FULL_TABLE_ID}")
                return True
            raise
    
    def store_gmail_credentials(self, owner_email: str, credentials: Dict) -> bool:
        """
        Store Gmail OAuth credentials for a user
        
        Args:
            owner_email: User's email address
            credentials: Dict with token, refresh_token, token_uri, client_id, client_secret, scopes
            
        Returns:
            True if successful
        """
        try:
            self._ensure_table_exists()
            
            integration_id = f"gmail_{owner_email}"
            now = datetime.utcnow().isoformat()
            
            token_expiry = None
            if credentials.get('expiry'):
                try:
                    if isinstance(credentials['expiry'], str):
                        token_expiry = credentials['expiry']
                    else:
                        token_expiry = credentials['expiry'].isoformat()
                except:
                    pass
            
            credentials_json = {
                'token_uri': credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
                'client_id': credentials.get('client_id'),
                'client_secret': credentials.get('client_secret'),
                'scopes': credentials.get('scopes', [])
            }
            
            query = f"""
            MERGE `{FULL_TABLE_ID}` T
            USING (SELECT @integration_id as integration_id) S
            ON T.integration_id = S.integration_id
            WHEN MATCHED THEN
                UPDATE SET
                    access_token = @access_token,
                    refresh_token = COALESCE(@refresh_token, T.refresh_token),
                    token_expiry = @token_expiry,
                    credentials = PARSE_JSON(@credentials_json),
                    is_connected = TRUE,
                    updated_at = CURRENT_TIMESTAMP(),
                    last_used = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
                INSERT (integration_id, owner_email, integration_type, credentials, 
                        access_token, refresh_token, token_expiry, is_connected, 
                        created_at, updated_at, last_used)
                VALUES (@integration_id, @owner_email, 'gmail', 
                        PARSE_JSON(@credentials_json), @access_token, @refresh_token, 
                        @token_expiry, TRUE, 
                        CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                    bigquery.ScalarQueryParameter("owner_email", "STRING", owner_email),
                    bigquery.ScalarQueryParameter("access_token", "STRING", credentials.get('token')),
                    bigquery.ScalarQueryParameter("refresh_token", "STRING", credentials.get('refresh_token')),
                    bigquery.ScalarQueryParameter("token_expiry", "TIMESTAMP", token_expiry),
                    bigquery.ScalarQueryParameter("credentials_json", "STRING", json.dumps(credentials_json)),
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
            logger.info(f"✓ Stored Gmail credentials for {owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing Gmail credentials: {e}")
            return False
    
    def get_gmail_credentials(self, owner_email: str) -> Optional[Dict]:
        """
        Get Gmail OAuth credentials for a user
        
        Args:
            owner_email: User's email address
            
        Returns:
            Dict with credentials or None if not found
        """
        try:
            integration_id = f"gmail_{owner_email}"
            
            query = f"""
            SELECT 
                access_token,
                refresh_token,
                token_expiry,
                credentials,
                is_connected,
                updated_at
            FROM `{FULL_TABLE_ID}`
            WHERE integration_id = @integration_id
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                ]
            )
            
            results = self.client.query(query, job_config=job_config).result()
            
            for row in results:
                if not row.is_connected:
                    logger.warning(f"Gmail integration for {owner_email} is not connected")
                    return None
                
                credentials_data = row.credentials
                if isinstance(credentials_data, str):
                    credentials_data = json.loads(credentials_data)
                elif credentials_data is None:
                    credentials_data = {}
                
                result = {
                    'token': row.access_token,
                    'refresh_token': row.refresh_token,
                    'token_uri': credentials_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials_data.get('client_id') or os.getenv('GMAIL_CLIENT_ID'),
                    'client_secret': credentials_data.get('client_secret') or os.getenv('GMAIL_CLIENT_SECRET'),
                    'scopes': credentials_data.get('scopes', [
                        'https://www.googleapis.com/auth/gmail.readonly',
                        'https://www.googleapis.com/auth/gmail.modify',
                        'https://www.googleapis.com/auth/userinfo.email',
                        'openid'
                    ])
                }
                
                if row.token_expiry:
                    result['expiry'] = row.token_expiry.isoformat()
                
                self._update_last_used(integration_id)
                
                return result
            
            logger.debug(f"No Gmail credentials found for {owner_email}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Gmail credentials: {e}")
            return None
    
    def refresh_gmail_token(self, owner_email: str) -> Optional[Dict]:
        """
        Refresh Gmail access token using stored refresh token
        
        Args:
            owner_email: User's email address
            
        Returns:
            Updated credentials dict or None if refresh failed
        """
        try:
            existing = self.get_gmail_credentials(owner_email)
            if not existing or not existing.get('refresh_token'):
                logger.error(f"No refresh token available for {owner_email}")
                return None
            
            creds = Credentials(
                token=existing['token'],
                refresh_token=existing['refresh_token'],
                token_uri=existing['token_uri'],
                client_id=existing['client_id'],
                client_secret=existing['client_secret'],
                scopes=existing['scopes']
            )
            
            if creds.expired or not creds.valid:
                creds.refresh(Request())
                
                updated_creds = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token or existing['refresh_token'],
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': list(creds.scopes) if creds.scopes else existing['scopes'],
                    'expiry': creds.expiry.isoformat() if creds.expiry else None
                }
                
                self.store_gmail_credentials(owner_email, updated_creds)
                logger.info(f"✓ Refreshed Gmail token for {owner_email}")
                return updated_creds
            
            return existing
            
        except Exception as e:
            logger.error(f"Error refreshing Gmail token for {owner_email}: {e}")
            return None
    
    def store_netsuite_credentials(self, owner_email: str, credentials: Dict) -> bool:
        """
        Store NetSuite OAuth 1.0a credentials for a user
        
        Args:
            owner_email: User's email address
            credentials: Dict with account_id, consumer_key, consumer_secret, 
                        token_id, token_secret
            
        Returns:
            True if successful
        """
        try:
            self._ensure_table_exists()
            
            integration_id = f"netsuite_{owner_email}"
            
            credentials_json = {
                'account_id': credentials.get('account_id'),
                'consumer_key': credentials.get('consumer_key'),
                'consumer_secret': credentials.get('consumer_secret'),
                'token_id': credentials.get('token_id'),
                'token_secret': credentials.get('token_secret'),
            }
            
            metadata_json = {
                'subsidiary_id': credentials.get('subsidiary_id'),
                'tax_code_id': credentials.get('tax_code_id'),
                'expense_account_id': credentials.get('expense_account_id'),
            }
            
            query = f"""
            MERGE `{FULL_TABLE_ID}` T
            USING (SELECT @integration_id as integration_id) S
            ON T.integration_id = S.integration_id
            WHEN MATCHED THEN
                UPDATE SET
                    credentials = PARSE_JSON(@credentials_json),
                    metadata = PARSE_JSON(@metadata_json),
                    is_connected = TRUE,
                    updated_at = CURRENT_TIMESTAMP(),
                    last_used = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
                INSERT (integration_id, owner_email, integration_type, credentials, 
                        metadata, is_connected, created_at, updated_at, last_used)
                VALUES (@integration_id, @owner_email, 'netsuite', 
                        PARSE_JSON(@credentials_json), PARSE_JSON(@metadata_json), TRUE, 
                        CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                    bigquery.ScalarQueryParameter("owner_email", "STRING", owner_email),
                    bigquery.ScalarQueryParameter("credentials_json", "STRING", json.dumps(credentials_json)),
                    bigquery.ScalarQueryParameter("metadata_json", "STRING", json.dumps(metadata_json)),
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
            logger.info(f"✓ Stored NetSuite credentials for {owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing NetSuite credentials: {e}")
            return False
    
    def get_netsuite_credentials(self, owner_email: str) -> Optional[Dict]:
        """
        Get NetSuite OAuth 1.0a credentials for a user
        
        Args:
            owner_email: User's email address
            
        Returns:
            Dict with credentials or None if not found
        """
        try:
            integration_id = f"netsuite_{owner_email}"
            
            query = f"""
            SELECT 
                credentials,
                metadata,
                is_connected,
                updated_at
            FROM `{FULL_TABLE_ID}`
            WHERE integration_id = @integration_id
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                ]
            )
            
            results = self.client.query(query, job_config=job_config).result()
            
            for row in results:
                if not row.is_connected:
                    logger.warning(f"NetSuite integration for {owner_email} is not connected")
                    return None
                
                credentials_data = row.credentials
                if isinstance(credentials_data, str):
                    credentials_data = json.loads(credentials_data)
                elif credentials_data is None:
                    credentials_data = {}
                
                metadata = row.metadata
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                elif metadata is None:
                    metadata = {}
                
                result = {
                    'account_id': credentials_data.get('account_id'),
                    'consumer_key': credentials_data.get('consumer_key'),
                    'consumer_secret': credentials_data.get('consumer_secret'),
                    'token_id': credentials_data.get('token_id'),
                    'token_secret': credentials_data.get('token_secret'),
                    'subsidiary_id': metadata.get('subsidiary_id'),
                    'tax_code_id': metadata.get('tax_code_id'),
                    'expense_account_id': metadata.get('expense_account_id'),
                }
                
                self._update_last_used(integration_id)
                
                return result
            
            logger.debug(f"No NetSuite credentials found for {owner_email}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting NetSuite credentials: {e}")
            return None
    
    def disconnect_integration(self, owner_email: str, integration_type: str) -> bool:
        """
        Disconnect an integration for a user (mark as not connected)
        
        Args:
            owner_email: User's email address
            integration_type: 'gmail' or 'netsuite'
            
        Returns:
            True if successful
        """
        try:
            integration_id = f"{integration_type}_{owner_email}"
            
            query = f"""
            UPDATE `{FULL_TABLE_ID}`
            SET is_connected = FALSE,
                updated_at = CURRENT_TIMESTAMP()
            WHERE integration_id = @integration_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
            logger.info(f"✓ Disconnected {integration_type} for {owner_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting integration: {e}")
            return False
    
    def get_user_integrations(self, owner_email: str) -> Dict[str, bool]:
        """
        Get all integration connection status for a user
        
        Args:
            owner_email: User's email address
            
        Returns:
            Dict mapping integration_type to is_connected status
        """
        try:
            query = f"""
            SELECT 
                integration_type,
                is_connected
            FROM `{FULL_TABLE_ID}`
            WHERE owner_email = @owner_email
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("owner_email", "STRING", owner_email),
                ]
            )
            
            results = self.client.query(query, job_config=job_config).result()
            
            integrations = {}
            for row in results:
                integrations[row.integration_type] = row.is_connected or False
            
            return integrations
            
        except Exception as e:
            logger.error(f"Error getting user integrations: {e}")
            return {}
    
    def _update_last_used(self, integration_id: str):
        """Update last_used timestamp for an integration"""
        try:
            query = f"""
            UPDATE `{FULL_TABLE_ID}`
            SET last_used = CURRENT_TIMESTAMP()
            WHERE integration_id = @integration_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("integration_id", "STRING", integration_id),
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
        except Exception as e:
            logger.debug(f"Could not update last_used: {e}")
    
    def is_gmail_connected(self, owner_email: str) -> bool:
        """Check if Gmail is connected for a user"""
        creds = self.get_gmail_credentials(owner_email)
        return creds is not None and creds.get('token') is not None
    
    def is_netsuite_connected(self, owner_email: str) -> bool:
        """Check if NetSuite is connected for a user"""
        creds = self.get_netsuite_credentials(owner_email)
        return (creds is not None and 
                creds.get('account_id') is not None and 
                creds.get('token_id') is not None)
