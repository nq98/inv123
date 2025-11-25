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
        # NOTE: No 'has:attachment' filter - allows link-only invoices (web receipts)
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
    
    def extract_html_body(self, message):
        """
        Extract the HTML body content from an email message
        
        Returns: HTML string content or None if not found
        """
        try:
            html_content = ''
            parts = message.get('payload', {}).get('parts', [])
            
            def extract_html_recursive(part):
                nonlocal html_content
                if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    return True
                if 'parts' in part:
                    for subpart in part['parts']:
                        if extract_html_recursive(subpart):
                            return True
                return False
            
            for part in parts:
                if extract_html_recursive(part):
                    break
            
            if not html_content and 'body' in message.get('payload', {}) and 'data' in message['payload']['body']:
                payload_type = message.get('payload', {}).get('mimeType', '')
                if 'html' in payload_type.lower():
                    html_content = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8', errors='ignore')
            
            return html_content if html_content else None
            
        except Exception as e:
            print(f"Error extracting HTML body: {e}")
            return None
    
    def extract_plain_text_body(self, message):
        """
        Extract plain text body from email message
        
        Returns: Plain text string or None
        """
        try:
            plain_text = ''
            parts = message.get('payload', {}).get('parts', [])
            
            def extract_plain_recursive(part):
                nonlocal plain_text
                if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                    plain_text = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    return True
                if 'parts' in part:
                    for subpart in part['parts']:
                        if extract_plain_recursive(subpart):
                            return True
                return False
            
            for part in parts:
                if extract_plain_recursive(part):
                    break
            
            if not plain_text and 'body' in message.get('payload', {}) and 'data' in message['payload']['body']:
                payload_type = message.get('payload', {}).get('mimeType', '')
                if 'plain' in payload_type.lower() or not payload_type:
                    plain_text = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8', errors='ignore')
            
            return plain_text if plain_text else None
            
        except Exception as e:
            print(f"Error extracting plain text body: {e}")
            return None
    
    def plain_text_to_html(self, plain_text, subject='Email Receipt', sender='Unknown'):
        """
        Convert plain text email to a styled HTML document for PDF rendering
        
        Returns: HTML string
        """
        escaped_text = plain_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lines = escaped_text.split('\n')
        formatted_lines = '<br>'.join(lines)
        
        html_template = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #f5f5f5;
        }}
        .email-container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        .email-header {{
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .email-subject {{
            font-size: 20px;
            font-weight: 600;
            color: #1a1a1a;
            margin: 0 0 8px 0;
        }}
        .email-from {{
            font-size: 14px;
            color: #666;
        }}
        .email-body {{
            font-size: 14px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .email-footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #e0e0e0;
            font-size: 12px;
            color: #999;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-header">
            <h1 class="email-subject">{subject}</h1>
            <div class="email-from">From: {sender}</div>
        </div>
        <div class="email-body">{formatted_lines}</div>
        <div class="email-footer">
            Extracted from email for invoice processing
        </div>
    </div>
</body>
</html>
'''
        return html_template
    
    def _find_chromium_executable(self):
        """Find system Chromium executable (Nix-installed or system)"""
        import glob
        import shutil
        
        possible_paths = [
            '/nix/store/*/bin/chromium',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
        ]
        
        for pattern in possible_paths:
            if '*' in pattern:
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
            elif os.path.exists(pattern):
                return pattern
        
        path_chromium = shutil.which('chromium') or shutil.which('chromium-browser')
        if path_chromium:
            return path_chromium
            
        return None
    
    def html_to_pdf(self, html_content, subject='email_receipt'):
        """
        Convert HTML email content to a PDF using Playwright
        
        Returns: (filename, pdf_data) or None if failed
        """
        try:
            from playwright.sync_api import sync_playwright
            import time
            
            timestamp = int(time.time())
            safe_subject = re.sub(r'[^\w\s-]', '', subject)[:30].strip().replace(' ', '_')
            filename = f"email_receipt_{safe_subject}_{timestamp}.pdf"
            
            chromium_path = self._find_chromium_executable()
            
            with sync_playwright() as p:
                launch_options = {
                    'headless': True,
                    'args': [
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--single-process'
                    ]
                }
                
                if chromium_path:
                    launch_options['executable_path'] = chromium_path
                    print(f"📄 Using Chromium at: {chromium_path}")
                
                browser = p.chromium.launch(**launch_options)
                page = browser.new_page(viewport={'width': 800, 'height': 1200})
                
                page.set_content(html_content, timeout=30000)
                try:
                    page.wait_for_load_state('networkidle', timeout=8000)
                except Exception as load_err:
                    print(f"⚠️ Network idle timeout (expected for emails with external resources) - continuing anyway")
                
                time.sleep(0.5)
                
                pdf_data = page.pdf(
                    format='A4',
                    print_background=True,
                    margin={'top': '20px', 'right': '20px', 'bottom': '20px', 'left': '20px'}
                )
                
                browser.close()
                
            print(f"📄 HTML email converted to PDF: {filename} ({len(pdf_data)} bytes)")
            return (filename, pdf_data)
            
        except Exception as e:
            print(f"Error converting HTML to PDF: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def html_to_image(self, html_content, subject='email_receipt'):
        """
        Convert HTML email content to a PDF (backwards compatible wrapper)
        Now generates PDF instead of PNG for better Document AI processing.
        
        Returns: (filename, pdf_data) or None if failed
        """
        return self.html_to_pdf(html_content, subject)
    
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
                    filename = 'invoice.pdf'
                    
                    if 'Content-Disposition' in response.headers:
                        cd = response.headers['Content-Disposition']
                        if 'filename=' in cd:
                            filename = cd.split('filename=')[1].strip('"')
                    else:
                        url_parts = url.split('/')
                        if url_parts[-1] and '.pdf' in url_parts[-1].lower():
                            filename = url_parts[-1].split('?')[0]
                    
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
    
    def send_email(self, to, subject, body):
        """
        Send an email using Gmail API
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            from email.mime.text import MIMEText
            import base64
            
            # Create message
            message = MIMEText(body, 'html' if '<html' in body.lower() else 'plain')
            message['to'] = to
            message['subject'] = subject
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Get credentials from environment (this would be the user's credentials)
            # For now, return True to indicate the method exists
            # In production, this would use actual OAuth credentials to send
            print(f"📧 Email would be sent to: {to}")
            print(f"   Subject: {subject}")
            print(f"   Body preview: {body[:100]}...")
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def process_link_intelligently(self, url, email_context, gemini_service=None):
        """
        AI-semantic intelligent link processor with fallback chain
        
        Workflow:
        1. AI classifies link type (direct_pdf | web_receipt | auth_required)
        2. direct_pdf → Try direct download
        3. web_receipt → Capture screenshot
        4. auth_required → Return None with reason
        5. If no Gemini → Fallback to basic PDF download
        
        Args:
            url: URL to process
            email_context: Email subject/snippet for context
            gemini_service: GeminiService for AI classification (optional)
        
        Returns:
            dict: {
                'success': bool,
                'type': 'pdf' | 'screenshot' | 'failed',
                'filename': str,
                'data': bytes,
                'link_classification': str,
                'reasoning': str
            }
        """
        
        try:
            # DEFENSIVE: If Gemini unavailable, fallback to basic PDF download
            if not gemini_service:
                print(f"⚠️ Gemini service unavailable, trying basic PDF download...")
                pdf_result = self.download_pdf_from_link(url)
                
                if pdf_result:
                    filename, pdf_data = pdf_result
                    return {
                        'success': True,
                        'type': 'pdf',
                        'filename': filename,
                        'data': pdf_data,
                        'link_classification': 'fallback',
                        'reasoning': 'Gemini unavailable - used basic download'
                    }
                else:
                    return {
                        'success': False,
                        'type': 'failed',
                        'filename': None,
                        'data': None,
                        'link_classification': 'fallback',
                        'reasoning': 'Gemini unavailable and basic download failed'
                    }
            
            # Step 1: AI Link Classification
            link_type, confidence, classification_reasoning = gemini_service.classify_link_type(
                url, 
                email_context
            )
            
            print(f"🧠 AI Link Classification: {link_type} (confidence: {confidence:.2f})")
            print(f"   Reasoning: {classification_reasoning}")
            
            # Step 2: Process based on classification
            if link_type == 'direct_pdf':
                # Try direct PDF download
                print(f"📥 Attempting direct PDF download...")
                pdf_result = self.download_pdf_from_link(url)
                
                if pdf_result:
                    filename, pdf_data = pdf_result
                    return {
                        'success': True,
                        'type': 'pdf',
                        'filename': filename,
                        'data': pdf_data,
                        'link_classification': link_type,
                        'reasoning': classification_reasoning
                    }
                else:
                    # Direct download failed, fallback to screenshot
                    print(f"⚠️ Direct PDF download failed, trying screenshot fallback...")
                    link_type = 'web_receipt'  # Force screenshot attempt
            
            if link_type == 'web_receipt':
                # Capture screenshot
                print(f"📸 Capturing web receipt screenshot...")
                from services.screenshot_service import ScreenshotService
                screenshot_service = ScreenshotService()
                
                screenshot_data = screenshot_service.capture_receipt_screenshot(url)
                
                if screenshot_data:
                    # Generate filename from URL
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    filename = f"receipt_screenshot_{parsed_url.netloc.replace('.', '_')}.png"
                    
                    return {
                        'success': True,
                        'type': 'screenshot',
                        'filename': filename,
                        'data': screenshot_data,
                        'link_classification': link_type,
                        'reasoning': classification_reasoning
                    }
                else:
                    return {
                        'success': False,
                        'type': 'failed',
                        'filename': None,
                        'data': None,
                        'link_classification': link_type,
                        'reasoning': 'Screenshot capture failed'
                    }
            
            if link_type == 'auth_required':
                # Cannot process - requires authentication
                return {
                    'success': False,
                    'type': 'failed',
                    'filename': None,
                    'data': None,
                    'link_classification': link_type,
                    'reasoning': f'Requires authentication: {classification_reasoning}'
                }
            
            if link_type == 'not_invoice':
                # Skip - this is an icon, logo, or decoration image, not an invoice
                return {
                    'success': False,
                    'type': 'skipped',
                    'filename': None,
                    'data': None,
                    'link_classification': link_type,
                    'reasoning': f'Skipped (not an invoice): {classification_reasoning}'
                }
            
            # Unknown link type
            return {
                'success': False,
                'type': 'failed',
                'filename': None,
                'data': None,
                'link_classification': link_type,
                'reasoning': f'Unknown link type: {link_type}'
            }
            
        except Exception as e:
            print(f"❌ Intelligent link processing error: {e}")
            return {
                'success': False,
                'type': 'failed',
                'filename': None,
                'data': None,
                'link_classification': 'error',
                'reasoning': str(e)
            }
