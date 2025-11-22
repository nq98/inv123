import os
import json
import base64
import re
import requests
from datetime import datetime, timedelta
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
    
    def __init__(self):
        self.client_id = os.getenv('GMAIL_CLIENT_ID')
        self.client_secret = os.getenv('GMAIL_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required")
    
    def _get_redirect_uri(self):
        """Get dynamic redirect URI based on environment (dev vs production)"""
        base_url = os.getenv('REDIRECT_BASE_URL')
        if base_url:
            return f"{base_url}/api/ap-automation/gmail/callback"
        
        dev_domain = os.getenv('REPLIT_DEV_DOMAIN')
        if dev_domain:
            return f"https://{dev_domain}/api/ap-automation/gmail/callback"
        
        return 'https://75bd8e64-74c3-4cba-a6bc-f00d155715e0-00-286n65r8swcy1.janeway.replit.dev/api/ap-automation/gmail/callback'
    
    def get_authorization_url(self, redirect_uri=None):
        """Generate Gmail OAuth authorization URL"""
        if redirect_uri is None:
            redirect_uri = self._get_redirect_uri()
        
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return auth_url, state
    
    def exchange_code_for_token(self, code, redirect_uri=None):
        """Exchange authorization code for access token"""
        if redirect_uri is None:
            redirect_uri = self._get_redirect_uri()
        
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
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
    
    def search_invoice_emails(self, service, max_results=20, days=30):
        """
        Search for emails containing invoices using "Broad Net" AI-first query
        Casts wide net with multi-language support, lets AI do semantic filtering
        
        Args:
            service: Gmail API service
            max_results: Maximum number of emails to return
            days: Number of days to look back (default: 30)
        
        Returns list of message IDs that likely contain invoices
        """
        after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
        
        # BROAD NET: Multi-language financial document query
        # Supports: English, Hebrew, French, German, Spanish
        # NOTE: No 'has:attachment' filter - allows link-only invoices (Stripe, AWS, etc.)
        # AI Gatekeeper will filter out junk emails in Stage 2
        query = (
            f'after:{after_date} '
            '('
            'subject:invoice OR subject:bill OR subject:receipt OR subject:statement OR '
            'subject:payment OR subject:order OR subject:subscription OR '
            'subject:חשבונית OR subject:קבלה OR subject:תשלום OR '
            'subject:facture OR subject:rechnung OR subject:recibo'
            ') '
            '-subject:"invitation" -subject:"newsletter" -subject:"webinar" -subject:"verify"'
        )
        
        try:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            return messages
            
        except Exception as e:
            print(f"Error searching Gmail: {e}")
            return []
    
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
        """Extract metadata from Gmail message including attachment filenames"""
        headers = message['payload'].get('headers', [])
        
        metadata = {
            'id': message['id'],
            'threadId': message.get('threadId'),
            'snippet': message.get('snippet', ''),
            'date': None,
            'from': None,
            'subject': None,
            'attachments': []
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
        
        # Extract attachment filenames for AI gatekeeper
        parts = message.get('payload', {}).get('parts', [])
        
        def extract_attachment_names(part):
            if part.get('filename'):
                metadata['attachments'].append(part['filename'])
            if 'parts' in part:
                for subpart in part['parts']:
                    extract_attachment_names(subpart)
        
        for part in parts:
            extract_attachment_names(part)
        
        # Check main payload for direct attachment
        if not parts and message.get('payload', {}).get('filename'):
            metadata['attachments'].append(message['payload']['filename'])
        
        return metadata
    
    def extract_links_from_body(self, message):
        """
        Extract PDF download links from email body
        
        Returns list of URLs that might contain invoice PDFs
        """
        links = []
        
        try:
            # Get email body
            body_data = ''
            parts = message.get('payload', {}).get('parts', [])
            
            def extract_body_recursive(part):
                nonlocal body_data
                if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    body_data += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                elif part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                    body_data += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                if 'parts' in part:
                    for subpart in part['parts']:
                        extract_body_recursive(subpart)
            
            for part in parts:
                extract_body_recursive(part)
            
            # If no parts, try payload body directly
            if not body_data and 'body' in message.get('payload', {}) and 'data' in message['payload']['body']:
                body_data = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8', errors='ignore')
            
            # Find URLs that likely contain PDFs
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            urls = re.findall(url_pattern, body_data)
            
            for url in urls:
                # Look for invoice/receipt/billing URLs
                url_lower = url.lower()
                if any(keyword in url_lower for keyword in ['invoice', 'receipt', 'bill', 'download', 'pdf', 'document']):
                    links.append(url)
            
        except Exception as e:
            print(f"Error extracting links from body: {e}")
        
        return links
    
    def download_pdf_from_link(self, url, timeout=30):
        """
        Download PDF from a URL
        
        Returns: (filename, pdf_data) or None if failed
        """
        try:
            response = requests.get(url, timeout=timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                
                if 'pdf' in content_type.lower() or url.lower().endswith('.pdf'):
                    # Extract filename from URL or Content-Disposition header
                    filename = 'invoice.pdf'
                    
                    if 'Content-Disposition' in response.headers:
                        cd = response.headers['Content-Disposition']
                        if 'filename=' in cd:
                            filename = cd.split('filename=')[1].strip('"')
                    else:
                        # Extract from URL
                        url_parts = url.split('/')
                        if url_parts[-1] and '.pdf' in url_parts[-1].lower():
                            filename = url_parts[-1].split('?')[0]  # Remove query params
                    
                    return (filename, response.content)
        
        except Exception as e:
            print(f"Error downloading PDF from {url}: {e}")
        
        return None
    
    def classify_invoice_email(self, metadata, gemini_service=None):
        """
        Use AI-powered Elite Gatekeeper to determine if email contains financial document
        
        Args:
            metadata: Email metadata dict with subject, from, snippet, attachments
            gemini_service: GeminiService instance for AI filtering
        
        Returns: (is_invoice: bool, confidence: float, reasoning: str)
        """
        subject = metadata.get('subject', '')
        sender = metadata.get('from', '')
        snippet = metadata.get('snippet', '')
        attachments = metadata.get('attachments', [])
        
        # Get first attachment filename (or "no_attachment" if none)
        attachment_filename = attachments[0] if attachments else "no_attachment"
        
        # Use AI Gatekeeper if available
        if gemini_service:
            result = gemini_service.gatekeeper_email_filter(
                sender_email=sender,
                email_subject=subject,
                email_body_snippet=snippet,
                attachment_filename=attachment_filename
            )
            
            is_invoice = result["is_financial_document"]
            confidence = result["confidence"]
            reasoning = f"[AI Gatekeeper] {result['document_category']} - {result['reasoning']}"
            
            return is_invoice, confidence, reasoning
        
        # Fallback to basic heuristics if Gemini unavailable (should rarely happen)
        subject_lower = subject.lower()
        snippet_lower = snippet.lower()
        
        invoice_keywords = ['invoice', 'receipt', 'bill', 'payment', 'statement', 'order', 
                           'חשבונית', 'קבלה', 'תשלום']
        spam_keywords = ['unsubscribe', 'marketing', 'newsletter', 'promotion', 'offer']
        
        invoice_score = sum(1 for kw in invoice_keywords if kw in subject_lower or kw in snippet_lower)
        spam_score = sum(1 for kw in spam_keywords if kw in subject_lower or kw in snippet_lower)
        
        confidence = min(1.0, invoice_score * 0.25)
        is_invoice = invoice_score > 0 and spam_score == 0
        
        reasoning = f"[Fallback Heuristics] Found {invoice_score} invoice keywords, {spam_score} spam keywords"
        
        return is_invoice, confidence, reasoning
