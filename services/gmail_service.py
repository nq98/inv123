import os
import json
import base64
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from config import config

class GmailService:
    """Service for Gmail OAuth and invoice email extraction"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/userinfo.email',
        'openid'
    ]
    
    REDIRECT_URI = 'https://75bd8e64-74c3-4cba-a6bc-f00d155715e0-00-286n65r8swcy1.janeway.replit.dev/api/ap-automation/gmail/callback'
    
    def __init__(self):
        self.client_id = os.getenv('GMAIL_CLIENT_ID')
        self.client_secret = os.getenv('GMAIL_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required")
    
    def get_authorization_url(self):
        """Generate Gmail OAuth authorization URL"""
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.REDIRECT_URI]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.REDIRECT_URI
        )
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return auth_url, state
    
    def exchange_code_for_token(self, code):
        """Exchange authorization code for access token"""
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.REDIRECT_URI]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.REDIRECT_URI
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
    
    def build_service(self, credentials_dict):
        """Build Gmail API service from credentials dictionary"""
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        return build('gmail', 'v1', credentials=credentials)
    
    def search_invoice_emails(self, service, max_results=20):
        """
        Search for emails containing invoices using semantic queries
        
        Returns list of message IDs that likely contain invoices
        """
        invoice_queries = [
            'subject:(invoice OR receipt OR billing OR payment) has:attachment',
            'from:(noreply OR billing OR invoices OR payments) has:attachment',
            'filename:pdf (invoice OR receipt OR statement)',
            'subject:(order confirmation OR purchase receipt) has:attachment'
        ]
        
        all_messages = []
        seen_ids = set()
        
        for query in invoice_queries:
            try:
                results = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=max_results
                ).execute()
                
                messages = results.get('messages', [])
                
                for msg in messages:
                    if msg['id'] not in seen_ids:
                        all_messages.append(msg)
                        seen_ids.add(msg['id'])
                        
                if len(all_messages) >= max_results:
                    break
                    
            except Exception as e:
                print(f"Error searching with query '{query}': {e}")
                continue
        
        return all_messages[:max_results]
    
    def get_message_details(self, service, message_id):
        """Get full details of a Gmail message"""
        try:
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            return message
        except Exception as e:
            print(f"Error getting message {message_id}: {e}")
            return None
    
    def extract_attachments(self, service, message):
        """
        Extract PDF attachments from a Gmail message
        
        Returns list of (filename, data) tuples
        """
        attachments = []
        
        if 'payload' not in message:
            return attachments
        
        parts = message['payload'].get('parts', [])
        
        def process_part(part):
            if part.get('filename') and part.get('filename').lower().endswith('.pdf'):
                if 'body' in part and 'attachmentId' in part['body']:
                    attachment_id = part['body']['attachmentId']
                    
                    try:
                        attachment = service.users().messages().attachments().get(
                            userId='me',
                            messageId=message['id'],
                            id=attachment_id
                        ).execute()
                        
                        file_data = base64.urlsafe_b64decode(attachment['data'])
                        attachments.append((part['filename'], file_data))
                        
                    except Exception as e:
                        print(f"Error downloading attachment: {e}")
            
            if 'parts' in part:
                for subpart in part['parts']:
                    process_part(subpart)
        
        for part in parts:
            process_part(part)
        
        if not parts and 'body' in message['payload'] and 'attachmentId' in message['payload']['body']:
            filename = message['payload'].get('filename', 'invoice.pdf')
            if filename.lower().endswith('.pdf'):
                try:
                    attachment_id = message['payload']['body']['attachmentId']
                    attachment = service.users().messages().attachments().get(
                        userId='me',
                        messageId=message['id'],
                        id=attachment_id
                    ).execute()
                    
                    file_data = base64.urlsafe_b64decode(attachment['data'])
                    attachments.append((filename, file_data))
                except Exception as e:
                    print(f"Error downloading main attachment: {e}")
        
        return attachments
    
    def get_email_metadata(self, message):
        """Extract metadata from Gmail message"""
        headers = message['payload'].get('headers', [])
        
        metadata = {
            'id': message['id'],
            'threadId': message.get('threadId'),
            'snippet': message.get('snippet', ''),
            'date': None,
            'from': None,
            'subject': None
        }
        
        for header in headers:
            name = header['name'].lower()
            value = header['value']
            
            if name == 'date':
                metadata['date'] = value
            elif name == 'from':
                metadata['from'] = value
            elif name == 'subject':
                metadata['subject'] = value
        
        return metadata
    
    def classify_invoice_email(self, metadata, gemini_service=None):
        """
        Use semantic analysis to determine if email truly contains an invoice
        
        Returns: (is_invoice: bool, confidence: float, reasoning: str)
        """
        subject = metadata.get('subject', '').lower()
        sender = metadata.get('from', '').lower()
        snippet = metadata.get('snippet', '').lower()
        
        invoice_keywords = ['invoice', 'receipt', 'bill', 'payment', 'statement', 'order']
        spam_keywords = ['unsubscribe', 'marketing', 'newsletter', 'promotion', 'offer']
        
        invoice_score = sum(1 for kw in invoice_keywords if kw in subject or kw in snippet or kw in sender)
        spam_score = sum(1 for kw in spam_keywords if kw in subject or kw in snippet)
        
        confidence = min(1.0, invoice_score * 0.2)
        is_invoice = invoice_score > 0 and spam_score == 0
        
        reasoning = f"Found {invoice_score} invoice keywords, {spam_score} spam keywords"
        
        if gemini_service and confidence < 0.8:
            reasoning += " (Using basic heuristics, Gemini classification not implemented yet)"
        
        return is_invoice, confidence, reasoning
