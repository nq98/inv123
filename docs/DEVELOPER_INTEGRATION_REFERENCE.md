# Developer Integration Reference
## AP Automation System - Migration Guide

**Version:** 1.0  
**Date:** November 2025  
**Author:** Payouts.com Engineering

---

## Table of Contents
1. [Invoice Parsing Engine](#1-invoice-parsing-engine)
2. [The Supreme Judge Vendor Matcher](#2-the-supreme-judge-vendor-matcher)
3. [Gmail Integration (Scan & Fetch)](#3-gmail-integration-scan--fetch)
4. [NetSuite Sync & Events](#4-netsuite-sync--events)
5. [Vendor CSV Import (AI Mapper)](#5-vendor-csv-import-ai-mapper)
6. [The Super Agent (LangGraph)](#6-the-super-agent-langgraph)

---

## 1. Invoice Parsing Engine

**Source File:** `services/document_ai_service.py`

### Required Secrets (.env)

```bash
# Google Cloud Project
GOOGLE_CLOUD_PROJECT_NUMBER=123456789012

# Document AI Processor
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_LOCATION=us  # or "eu"

# Service Account (JSON string or file path)
GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
# OR
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Core Class Code

```python
import os
import json
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account

class DocumentAIService:
    """Service for extracting structured data from invoices using Document AI"""
    
    def __init__(self):
        credentials = None
        
        # Load credentials from environment JSON or file
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
            except json.JSONDecodeError:
                print("Warning: Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists('/path/to/service-account.json'):
            credentials = service_account.Credentials.from_service_account_file(
                '/path/to/service-account.json'
            )
        
        if credentials:
            self.client = documentai.DocumentProcessorServiceClient(credentials=credentials)
        else:
            self.client = documentai.DocumentProcessorServiceClient()
    
    def process_document(self, gcs_uri, mime_type='application/pdf'):
        """
        Process an invoice document using Document AI
        
        Args:
            gcs_uri: GCS URI of the document (e.g., gs://bucket/file.pdf)
            mime_type: MIME type of the document
            
        Returns:
            Processed document with extracted entities
        """
        # Build processor name from config
        project_number = os.getenv('GOOGLE_CLOUD_PROJECT_NUMBER')
        location = os.getenv('DOCAI_LOCATION', 'us')
        processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        
        processor_name = f"projects/{project_number}/locations/{location}/processors/{processor_id}"
        
        try:
            gcs_document = documentai.GcsDocument(
                gcs_uri=gcs_uri,
                mime_type=mime_type
            )
            
            request = documentai.ProcessRequest(
                name=processor_name,
                gcs_document=gcs_document
            )
            
            result = self.client.process_document(request=request)
            return result.document
        except Exception as e:
            raise RuntimeError(f"Document AI processing failed: {str(e)}") from e
    
    def extract_entities(self, document):
        """
        Extract structured entities from Document AI result
        
        Returns:
            Dictionary of extracted entities
        """
        entities = {}
        for entity in document.entities:
            entity_type = entity.type_
            entity_value = entity.mention_text if hasattr(entity, 'mention_text') else entity.text_anchor.content
            
            if entity_type not in entities:
                entities[entity_type] = []
            
            entities[entity_type].append({
                'value': entity_value,
                'confidence': entity.confidence if hasattr(entity, 'confidence') else 1.0,
                'normalized_value': entity.normalized_value.text if hasattr(entity, 'normalized_value') else None
            })
        
        return entities
    
    def get_raw_text(self, document):
        """Extract raw OCR text from document"""
        return document.text
```

### Usage Example

```python
from services.document_ai_service import DocumentAIService

# Initialize service
doc_ai = DocumentAIService()

# Process invoice from GCS
gcs_uri = "gs://payouts-invoices/invoices/invoice_123.pdf"
document = doc_ai.process_document(gcs_uri, mime_type='application/pdf')

# Extract entities
entities = doc_ai.extract_entities(document)
print(f"Vendor Name: {entities.get('vendor_name', [{}])[0].get('value')}")
print(f"Total Amount: {entities.get('total_amount', [{}])[0].get('value')}")

# Get raw OCR text
raw_text = doc_ai.get_raw_text(document)
print(f"Raw text (first 500 chars): {raw_text[:500]}")
```

---

## 2. The Supreme Judge Vendor Matcher

**Source Files:** 
- `services/vendor_matcher.py`
- `services/vertex_search_service.py`
- `services/gemini_service.py`

### Required Secrets (.env)

```bash
# Vertex AI Search (RAG)
VERTEX_AI_SEARCH_DATA_STORE_ID=your-data-store-id
GOOGLE_CLOUD_PROJECT_NUMBER=123456789012

# OpenRouter (Gemini 3 Pro - Primary)
OPENROUTERA=sk-or-v1-xxxxxxxxxxxxxxxxxxxx

# Google AI Studio (Fallback)
GOOGLE_GEMINI_API_KEY=<SET_IN_REPLIT_SECRETS>

# BigQuery
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account",...}'
```

### Core Class Code

```python
import json
from google.genai import types

class VendorMatcher:
    """
    3-Step Vendor Matching Engine with Supreme Judge Semantic Reasoning
    
    Pipeline:
        Step 0: Hard Match (Fast SQL) - Tax ID exact match in BigQuery → 100% confidence
        Step 1: Semantic Retrieval (Vertex AI Search RAG) - Find Top 5 similar vendors
        Step 2: The Supreme Judge (Gemini 1.5 Pro) - Semantic reasoning: MATCH | NEW_VENDOR | AMBIGUOUS
    """
    
    def __init__(self, bigquery_service, vertex_search_service, gemini_service):
        self.bigquery = bigquery_service
        self.vertex_search = vertex_search_service
        self.gemini = gemini_service
    
    def match_vendor(self, invoice_data, classifier_verdict=None):
        """
        3-step vendor matching pipeline
        
        Args:
            invoice_data: dict with vendor_name, tax_id, address, email_domain, phone, country
            classifier_verdict: Optional dict with semantic entity classification result
        
        Returns:
            dict: {
                "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS" | "INVALID_VENDOR",
                "vendor_id": str or None,
                "confidence": float (0.0-1.0),
                "reasoning": str,
                "method": str (TAX_ID_HARD_MATCH, SEMANTIC_MATCH, NEW_VENDOR)
            }
        """
        vendor_name = invoice_data.get('vendor_name', 'Unknown')
        
        # STEP 0: Hard Match by Tax ID (100% confidence if found)
        tax_id = invoice_data.get('tax_id', '')
        if tax_id and tax_id != 'Unknown':
            hard_match = self._hard_match_by_tax_id(tax_id)
            if hard_match:
                return {
                    "verdict": "MATCH",
                    "vendor_id": hard_match['vendor_id'],
                    "confidence": 1.0,
                    "reasoning": f"Exact Tax ID match: {tax_id}",
                    "method": "TAX_ID_HARD_MATCH"
                }
        
        # STEP 1: Semantic Candidate Retrieval (Vertex AI Search RAG)
        candidates = self._get_semantic_candidates(vendor_name, invoice_data.get('country'), top_k=5)
        
        if not candidates:
            return {
                "verdict": "NEW_VENDOR",
                "vendor_id": None,
                "confidence": 0.0,
                "reasoning": f"No similar vendors found for '{vendor_name}'",
                "method": "NEW_VENDOR"
            }
        
        # STEP 2: Supreme Judge Decision (Gemini)
        judge_decision = self._supreme_judge_decision(invoice_data, candidates, classifier_verdict)
        
        return judge_decision
    
    def _hard_match_by_tax_id(self, tax_id):
        """Step 0: Query BigQuery for exact Tax ID match"""
        clean_tax_id = tax_id.replace(" ", "").replace("-", "").upper()
        
        query = f"""
        SELECT vendor_id, global_name
        FROM `{self.bigquery.full_table_id}`
        WHERE REPLACE(REPLACE(UPPER(JSON_VALUE(custom_attributes, '$.tax_id')), ' ', ''), '-', '') = @clean_tax_id
        LIMIT 1
        """
        
        results = list(self.bigquery.client.query(query, job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("clean_tax_id", "STRING", clean_tax_id)]
        )).result())
        
        if results:
            return {"vendor_id": results[0].vendor_id, "vendor_name": results[0].global_name}
        return None
    
    def _get_semantic_candidates(self, vendor_name, country=None, top_k=5):
        """Step 1: Use Vertex AI Search to find semantically similar vendors"""
        search_query = f"Find vendor: {vendor_name}"
        if country:
            search_query += f" in {country}"
        
        search_results = self.vertex_search.search_vendor(
            vendor_query=search_query,
            max_results=top_k
        )
        
        # Format candidates
        candidates = []
        for result in search_results:
            data = result.get('data', {})
            candidates.append({
                "candidate_id": data.get('vendor_id'),
                "global_name": data.get('global_name'),
                "tax_ids": [data.get('custom_attributes', {}).get('tax_id')] if data.get('custom_attributes', {}).get('tax_id') else [],
                "domains": data.get('domains', []),
                "countries": data.get('countries', [])
            })
        
        return candidates
    
    def _supreme_judge_decision(self, invoice_data, candidates, classifier_verdict=None):
        """Step 2: Supreme Judge AI decision using Gemini"""
        # See SUPREME_JUDGE_PROMPT below
        pass
```

### The Supreme Judge Prompt (Sent to Gemini)

```python
SUPREME_JUDGE_PROMPT = """
### SYSTEM IDENTITY
You are the **Global Entity Resolution Engine** — The Supreme Judge of Vendor Master Data.

Your mission: Determine if the **INVOICE VENDOR** and a **DATABASE CANDIDATE** represent the same real-world business entity.

### ⚖️ THE EVIDENCE HIERARCHY (HOW TO JUDGE)

**🥇 GOLD TIER EVIDENCE (Definitive Proof → Confidence 0.95-1.0)**
1. **Tax ID Match:** VAT, EIN, GSTIN, or CNPJ matches exactly
2. **IBAN/Bank Account Match:** Bank account numbers are identical
3. **Corporate Domain Match:** Invoice email domain matches vendor name

**🥈 SILVER TIER EVIDENCE (Strong Evidence → Confidence 0.75-0.90)**
1. **Semantic Name Match:** "Global Tech Services" == "GTS" == "Global Tech Inc."
2. **Address Proximity:** Same street address despite formatting differences
3. **Phone Number Match:** Same primary phone number

**🥉 BRONZE TIER EVIDENCE (Circumstantial → Confidence 0.50-0.70)**
1. **Generic Business Match:** "Consulting Services Inc" vs "Consulting Services Ltd"
2. **Partial Name Match:** "John Smith" vs "John Smith Design"

### 🧠 SEMANTIC REASONING RULES

**1. CORPORATE HIERARCHY & ACQUISITIONS**
- "SubCo" and "ParentCorp" → MATCH (parent/child relationship)

**2. BRAND vs. LEGAL ENTITY**
- Invoice: "Brand Name" → DB: "Legal Entity Corp" → MATCH

**3. GEOGRAPHIC SUBSIDIARIES**
- "VendorCo BV" (Netherlands) == "VendorCo Inc" (USA) → MATCH

**4. TYPOS & OCR ERRORS**
- "Tech C0rp" == "Tech Corp" (OCR misread O as 0)

### 📝 THE VERDICT SCHEMA (JSON ONLY)
{
    "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS",
    "match_details": {
        "selected_vendor_id": "string or null",
        "confidence_score": 0.0-1.0,
        "match_reasoning": "Explain your decision"
    },
    "database_updates": {
        "add_new_alias": "string or null",
        "add_new_address": "string or null"
    }
}
"""
```

### Usage Example

```python
from services.bigquery_service import BigQueryService
from services.vertex_search_service import VertexSearchService
from services.gemini_service import GeminiService
from services.vendor_matcher import VendorMatcher

# Initialize services
bigquery_service = BigQueryService()
vertex_search_service = VertexSearchService()
gemini_service = GeminiService()

# Create matcher
matcher = VendorMatcher(bigquery_service, vertex_search_service, gemini_service)

# Match an invoice vendor
invoice_data = {
    "vendor_name": "Amazon AWS",
    "tax_id": "US123456789",
    "address": "410 Terry Ave N, Seattle, WA",
    "email_domain": "@aws.com",
    "country": "US"
}

result = matcher.match_vendor(invoice_data)

print(f"Verdict: {result['verdict']}")
print(f"Vendor ID: {result.get('vendor_id')}")
print(f"Confidence: {result['confidence']}")
print(f"Reasoning: {result['reasoning']}")
```

---

## 3. Gmail Integration (Scan & Fetch)

**Source File:** `services/gmail_service.py`

### Required Secrets (.env)

```bash
# Gmail OAuth Credentials (from Google Cloud Console)
GMAIL_CLIENT_ID=123456789-xxxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx

# Redirect URL (for OAuth callback)
REDIRECT_BASE_URL=https://your-domain.com
# OR for Replit dev:
REPLIT_DEV_DOMAIN=your-repl.replit.dev
```

### Core Class Code

```python
import os
import base64
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

class GmailService:
    """Service for Gmail OAuth and invoice email extraction"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/userinfo.email',
        'openid'
    ]
    
    def __init__(self, owner_email: str = None):
        self.client_id = os.getenv('GMAIL_CLIENT_ID')
        self.client_secret = os.getenv('GMAIL_CLIENT_SECRET')
        self.owner_email = owner_email
        
        if not self.client_id or not self.client_secret:
            raise ValueError("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required")
    
    def _get_redirect_uri(self):
        """Get dynamic redirect URI based on environment"""
        base_url = os.getenv('REDIRECT_BASE_URL')
        if base_url:
            return f"{base_url}/api/ap-automation/gmail/callback"
        
        dev_domain = os.getenv('REPLIT_DEV_DOMAIN')
        if dev_domain:
            return f"https://{dev_domain}/api/ap-automation/gmail/callback"
        
        return 'http://localhost:5000/api/ap-automation/gmail/callback'
    
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
        Search for emails containing invoices using multi-language query
        
        Args:
            service: Gmail API service
            max_results: Maximum number of emails to return
            days: Number of days to look back
        
        Returns:
            List of message IDs
        """
        after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
        
        # MULTI-LANGUAGE FINANCIAL DOCUMENT QUERY
        # Supports: English, Hebrew, French, German, Spanish
        query = (
            f'after:{after_date} '
            '('
            'subject:invoice OR subject:bill OR subject:receipt OR subject:statement OR '
            'subject:payment OR subject:order OR subject:subscription OR '
            'subject:חשבונית OR subject:קבלה OR subject:תשלום OR '  # Hebrew
            'subject:facture OR subject:rechnung OR subject:recibo'  # French/German/Spanish
            ') '
            '-subject:"invitation" -subject:"newsletter" -subject:"webinar"'
        )
        
        try:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            return results.get('messages', [])
            
        except Exception as e:
            print(f"Error searching Gmail: {e}")
            return []
    
    def get_message_details(self, service, message_id):
        """Get full details of a Gmail message"""
        return service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
    
    def extract_attachments(self, service, message):
        """Extract PDF attachments from a Gmail message"""
        attachments = []
        
        parts = message['payload'].get('parts', [])
        
        def process_part(part):
            if part.get('filename') and part.get('filename').lower().endswith('.pdf'):
                if 'body' in part and 'attachmentId' in part['body']:
                    attachment_id = part['body']['attachmentId']
                    
                    attachment = service.users().messages().attachments().get(
                        userId='me',
                        messageId=message['id'],
                        id=attachment_id
                    ).execute()
                    
                    file_data = base64.urlsafe_b64decode(attachment['data'])
                    attachments.append((part['filename'], file_data))
            
            if 'parts' in part:
                for subpart in part['parts']:
                    process_part(subpart)
        
        for part in parts:
            process_part(part)
        
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
        
        return metadata
```

### Usage Example

```python
from services.gmail_service import GmailService
from flask import session, redirect

gmail = GmailService()

# Step 1: Get authorization URL (redirect user here)
auth_url, state = gmail.get_authorization_url()
session['oauth_state'] = state
# return redirect(auth_url)

# Step 2: Handle OAuth callback (in /gmail/callback route)
def gmail_callback(request):
    code = request.args.get('code')
    credentials = gmail.exchange_code_for_token(code)
    session['gmail_credentials'] = credentials
    
# Step 3: Search for invoices
service = gmail.build_service(session['gmail_credentials'])
messages = gmail.search_invoice_emails(service, days=30)

for msg in messages:
    details = gmail.get_message_details(service, msg['id'])
    metadata = gmail.get_email_metadata(details)
    print(f"Subject: {metadata['subject']}")
    print(f"From: {metadata['from']}")
    
    # Download PDF attachments
    attachments = gmail.extract_attachments(service, details)
    for filename, file_data in attachments:
        print(f"Found attachment: {filename} ({len(file_data)} bytes)")
```

---

## 4. NetSuite Sync & Events

**Source Files:** 
- `services/netsuite_service.py`
- `services/netsuite_event_tracker.py`

### Required Secrets (.env)

```bash
# NetSuite OAuth 1.0a Credentials
NETSUITE_ACCOUNT_ID=TSTDRV1234567
NETSUITE_CONSUMER_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_CONSUMER_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_TOKEN_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Default IDs for bill creation
NETSUITE_SUBSIDIARY_ID=2
NETSUITE_TAX_CODE_ID=18
NETSUITE_EXPENSE_ACCOUNT_ID=351

# BigQuery (for event tracking)
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account",...}'
```

### Core Class Code - NetSuite Service

```python
import os
import json
import time
import hashlib
import hmac
import base64
from urllib.parse import quote
import requests

class NetSuiteService:
    """NetSuite REST API service with OAuth 1.0a authentication"""
    
    def __init__(self):
        self.account_id = os.getenv('NETSUITE_ACCOUNT_ID')
        self.consumer_key = os.getenv('NETSUITE_CONSUMER_KEY')
        self.consumer_secret = os.getenv('NETSUITE_CONSUMER_SECRET')
        self.token_id = os.getenv('NETSUITE_TOKEN_ID')
        self.token_secret = os.getenv('NETSUITE_TOKEN_SECRET')
        
        self.account_id_url = self.account_id.replace('_', '-').lower()
        self.base_url = f"https://{self.account_id_url}.suitetalk.api.netsuite.com/services/rest"
        
        self.enabled = all([self.account_id, self.consumer_key, self.consumer_secret,
                           self.token_id, self.token_secret])
    
    def _generate_oauth_signature(self, method, url, oauth_params, query_params=None):
        """Generate OAuth 1.0a signature"""
        all_params = oauth_params.copy()
        if query_params:
            all_params.update(query_params)
        
        sorted_params = sorted(all_params.items())
        encoded_params = []
        for key, value in sorted_params:
            encoded_key = quote(str(key), safe='~-._')
            encoded_value = quote(str(value), safe='~-._')
            encoded_params.append(f"{encoded_key}={encoded_value}")
        
        param_string = '&'.join(encoded_params)
        signature_base = f"{method.upper()}&{quote(url, safe='')}&{quote(param_string, safe='')}"
        signing_key = f"{self.consumer_secret}&{self.token_secret}"
        
        signature_bytes = hmac.new(
            signing_key.encode('utf-8'),
            signature_base.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature_bytes).decode('utf-8')
    
    def _generate_auth_header(self, method, full_url, query_params=None):
        """Generate complete OAuth Authorization header"""
        import random
        from urllib.parse import urlparse
        
        parsed_url = urlparse(full_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        
        nonce = ''.join([str(random.randint(0, 9)) for _ in range(11)])
        timestamp = str(int(time.time()))
        
        oauth_params = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_nonce': nonce,
            'oauth_signature_method': 'HMAC-SHA256',
            'oauth_timestamp': timestamp,
            'oauth_token': self.token_id,
            'oauth_version': '1.0'
        }
        
        signature = self._generate_oauth_signature(method, base_url, oauth_params, query_params)
        oauth_params['oauth_signature'] = signature
        
        auth_parts = [f'realm="{self.account_id}"']
        for key in sorted(oauth_params.keys()):
            value = oauth_params[key]
            encoded_value = quote(str(value), safe='~-._')
            auth_parts.append(f'{key}="{encoded_value}"')
        
        return 'OAuth ' + ', '.join(auth_parts)
    
    def pull_vendors(self, limit=1000):
        """
        Pull vendors from NetSuite
        
        Returns:
            List of vendor dictionaries
        """
        endpoint = "/record/v1/vendor"
        url = f"{self.base_url}{endpoint}"
        
        params = {'limit': limit, 'offset': 0}
        auth_header = self._generate_auth_header('GET', url, params)
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': auth_header
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('items', [])
        else:
            raise Exception(f"Failed to pull vendors: {response.status_code} - {response.text}")
    
    def create_vendor_bill(self, bill_data):
        """
        Create a vendor bill in NetSuite
        
        Args:
            bill_data: dict with vendor_netsuite_id, invoice_number, total_amount, currency, line_items
        
        Returns:
            dict with created bill ID
        """
        endpoint = "/record/v1/vendorbill"
        url = f"{self.base_url}{endpoint}"
        
        # Build bill payload
        payload = {
            "entity": {"id": bill_data['vendor_netsuite_id']},
            "tranId": bill_data['invoice_number'],
            "memo": bill_data.get('memo', ''),
            "currency": {"id": self._get_currency_id(bill_data.get('currency', 'USD'))},
            "item": {
                "items": [
                    {
                        "item": {"id": self._get_expense_account_id()},
                        "description": item['description'],
                        "amount": item['amount'],
                        "quantity": item.get('quantity', 1)
                    }
                    for item in bill_data.get('line_items', [])
                ]
            }
        }
        
        auth_header = self._generate_auth_header('POST', url)
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': auth_header,
            'prefer': 'transient'
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code in [200, 201, 204]:
            # Extract ID from Location header
            location = response.headers.get('Location', '')
            bill_id = location.split('/')[-1] if location else None
            return {'success': True, 'id': bill_id}
        else:
            raise Exception(f"Failed to create bill: {response.status_code} - {response.text}")
    
    def _get_currency_id(self, currency_code):
        """Map currency code to NetSuite internal ID"""
        currency_map = {
            'USD': '1', 'EUR': '2', 'GBP': '3', 'CAD': '4',
            'ILS': '5', 'AUD': '6', 'CHF': '7', 'JPY': '8'
        }
        return currency_map.get(currency_code, '1')
    
    def _get_expense_account_id(self):
        return os.getenv('NETSUITE_EXPENSE_ACCOUNT_ID', '351')
```

### Core Class Code - Event Tracker

```python
from google.cloud import bigquery
from google.oauth2 import service_account
from datetime import datetime
from uuid import uuid4
import json
import os

class NetSuiteEventTracker:
    """Comprehensive bidirectional event tracking for NetSuite operations"""
    
    def __init__(self, project_id='<PROJECT_ID>'):
        self.project_id = project_id
        
        # Load credentials
        if os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
            credentials_json = json.loads(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
            credentials = service_account.Credentials.from_service_account_info(credentials_json)
            self.client = bigquery.Client(project=project_id, credentials=credentials)
        else:
            self.client = bigquery.Client(project=project_id)
        
        self.events_table = f"{project_id}.vendors_ai.netsuite_events"
    
    def log_event(self, 
                  direction: str,           # OUTBOUND or INBOUND
                  event_type: str,          # e.g., VENDOR_CREATE, BILL_SYNC
                  event_category: str,      # VENDOR, BILL, PAYMENT
                  status: str,              # SUCCESS, FAILED, PENDING
                  entity_type: str = None,
                  entity_id: str = None,
                  netsuite_id: str = None,
                  action: str = None,       # CREATE, UPDATE, SYNC
                  request_data: dict = None,
                  response_data: dict = None,
                  error_message: str = None,
                  duration_ms: int = None) -> bool:
        """Log a NetSuite sync event to BigQuery"""
        
        event = {
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "direction": direction,
            "event_type": event_type,
            "event_category": event_category,
            "status": status,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "netsuite_id": netsuite_id,
            "action": action,
            "request_data": json.dumps(request_data) if request_data else None,
            "response_data": json.dumps(response_data) if response_data else None,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "user": "SYSTEM"
        }
        
        table = self.client.get_table(self.events_table)
        errors = self.client.insert_rows_json(table, [event])
        
        return len(errors) == 0
    
    def get_events(self, direction=None, event_category=None, 
                   status=None, hours=24, limit=100):
        """Get NetSuite events with filters"""
        
        where_clauses = [f"timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)"]
        
        if direction:
            where_clauses.append(f"direction = '{direction}'")
        if event_category:
            where_clauses.append(f"event_category = '{event_category}'")
        if status:
            where_clauses.append(f"status = '{status}'")
        
        query = f"""
        SELECT * FROM `{self.events_table}`
        WHERE {" AND ".join(where_clauses)}
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        
        return list(self.client.query(query).result())
```

### Usage Example

```python
from services.netsuite_service import NetSuiteService
from services.netsuite_event_tracker import NetSuiteEventTracker

# Initialize services
netsuite = NetSuiteService()
event_tracker = NetSuiteEventTracker()

# Pull vendors from NetSuite
vendors = netsuite.pull_vendors(limit=100)
print(f"Pulled {len(vendors)} vendors from NetSuite")

# Track the pull event
event_tracker.log_event(
    direction='INBOUND',
    event_type='VENDOR_PULL',
    event_category='VENDOR',
    status='SUCCESS',
    response_data={'count': len(vendors)}
)

# Create a vendor bill
bill_data = {
    'vendor_netsuite_id': '12345',
    'invoice_number': 'INV-2024-001',
    'total_amount': 1500.00,
    'currency': 'USD',
    'memo': 'Monthly consulting services',
    'line_items': [
        {'description': 'Consulting services', 'amount': 1500.00}
    ]
}

result = netsuite.create_vendor_bill(bill_data)
print(f"Created bill with ID: {result['id']}")

# Track the bill creation
event_tracker.log_event(
    direction='OUTBOUND',
    event_type='BILL_CREATE',
    event_category='BILL',
    status='SUCCESS',
    entity_id='INV-2024-001',
    netsuite_id=result['id'],
    request_data=bill_data
)
```

---

## 5. Vendor CSV Import (AI Mapper)

**Source File:** `services/vendor_csv_mapper.py`

### Required Secrets (.env)

```bash
# OpenRouter (Gemini 3 Pro - Primary)
OPENROUTERA=sk-or-v1-xxxxxxxxxxxxxxxxxxxx

# Google AI Studio (Fallback)
GOOGLE_GEMINI_API_KEY=<SET_IN_REPLIT_SECRETS>

# Vertex AI Search (Optional - for RAG learning)
VERTEX_AI_SEARCH_DATA_STORE_ID=your-data-store-id
```

### Core Class Code

```python
import os
import json
import csv
import io
from google import genai
from google.genai import types
from openai import OpenAI

class VendorCSVMapper:
    """AI-First Universal CSV Mapper using Gemini + Vertex AI Search RAG"""
    
    def __init__(self):
        # PRIMARY: OpenRouter Gemini 3 Pro
        self.openrouter_client = None
        openrouter_api_key = os.getenv('OPENROUTERA')
        
        if openrouter_api_key:
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
                default_headers={
                    "HTTP-Referer": "https://replit.com",
                    "X-Title": "Enterprise Invoice Extraction System"
                }
            )
        
        # FALLBACK: AI Studio
        api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash'
        
        self.system_instruction = """🧠 AI-FIRST UNIVERSAL DATA INTEGRATION EXPERT

You are the world's most advanced **Data Integration & Schema Mapping AI**.
Your goal is **100% Semantic Accuracy** for mapping ANY vendor CSV to a standardized database schema.

CORE PHILOSOPHY: "AI-First Semantic Understanding, Not Keyword Matching"

TARGET SCHEMA (Standardized Internal Database):
- vendor_id: Unique identifier
- global_name: Official company name
- emails: Contact emails array
- domains: Web domains array
- countries: Country codes array

Return ONLY valid JSON. No markdown. No commentary."""
    
    def analyze_csv_headers(self, csv_file_content, filename="upload.csv"):
        """
        Analyze CSV headers using AI to generate semantic column mapping
        
        Args:
            csv_file_content: Raw CSV file content (bytes or string)
            filename: Original filename for context
            
        Returns:
            dict with mapping schema and metadata
        """
        # Parse CSV
        if isinstance(csv_file_content, bytes):
            csv_file_content = csv_file_content.decode('utf-8-sig')
        
        csv_reader = csv.DictReader(io.StringIO(csv_file_content))
        headers = csv_reader.fieldnames
        
        # Get sample rows
        sample_rows = []
        for i, row in enumerate(csv_reader):
            if i >= 3:
                break
            sample_rows.append(row)
        
        # Build AI prompt
        prompt = f"""
🧠 AI-FIRST CSV SCHEMA MAPPING

**Filename**: {filename}
**CSV Headers**: {json.dumps(headers, ensure_ascii=False)}
**Sample Data (First 3 Rows)**: {json.dumps(sample_rows, indent=2, ensure_ascii=False)}

### SEMANTIC REASONING PROTOCOL
1. Language Detection - What language are these headers?
2. Semantic Analysis - What does each column MEAN?
3. Standard Field Matching - Map to vendor_id, global_name, emails, countries, domains
4. Custom Field Identification - Which columns don't fit?

### OUTPUT SCHEMA (JSON ONLY):
{{
  "detectedLanguage": "en|de|es|fr|he|mixed",
  "sourceSystemGuess": "SAP|QuickBooks|Oracle|Excel|Unknown",
  "columnMapping": {{
    "csv_column_name": {{
      "targetField": "vendor_id|global_name|emails|countries|domains|custom_attributes.original_name",
      "confidence": 0.0-1.0,
      "dataType": "string|number|email|array",
      "reasoning": "Why you mapped this column this way"
    }}
  }},
  "overallConfidence": 0.0-1.0
}}
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        result_text = response.text.strip()
        
        # Clean markdown if present
        if result_text.startswith('```json'):
            result_text = result_text[7:]
        if result_text.endswith('```'):
            result_text = result_text[:-3]
        
        mapping_schema = json.loads(result_text.strip())
        
        return {
            "success": True,
            "mapping": mapping_schema,
            "headers": headers,
            "sampleRows": sample_rows
        }
    
    def transform_csv_data(self, csv_file_content, column_mapping):
        """
        Transform CSV data using the AI-generated column mapping
        
        Args:
            csv_file_content: Raw CSV content
            column_mapping: Mapping schema from analyze_csv_headers()
            
        Returns:
            List of transformed vendor records ready for BigQuery
        """
        if isinstance(csv_file_content, bytes):
            csv_file_content = csv_file_content.decode('utf-8-sig')
        
        csv_reader = csv.DictReader(io.StringIO(csv_file_content))
        transformed_vendors = []
        
        for row_num, row in enumerate(csv_reader, start=2):
            vendor_record = {
                "vendor_id": None,
                "global_name": None,
                "normalized_name": None,
                "emails": [],
                "domains": [],
                "countries": [],
                "custom_attributes": {},
                "source_system": column_mapping.get("sourceSystemGuess", "csv_upload")
            }
            
            for csv_column, value in row.items():
                if not csv_column or not value or value.strip() == "":
                    continue
                
                mapping_info = column_mapping.get("columnMapping", {}).get(csv_column, {})
                target_field = mapping_info.get("targetField", f"custom_attributes.{csv_column}")
                
                value = str(value).strip()
                
                if target_field == "vendor_id":
                    vendor_record["vendor_id"] = value
                elif target_field == "global_name":
                    vendor_record["global_name"] = value
                    vendor_record["normalized_name"] = value
                elif target_field == "emails":
                    emails = [e.strip() for e in value.replace(";", ",").split(",") if e.strip()]
                    vendor_record["emails"].extend(emails)
                elif target_field == "countries":
                    countries = [c.strip() for c in value.replace(";", ",").split(",") if c.strip()]
                    vendor_record["countries"].extend(countries)
                elif target_field == "domains":
                    domains = [d.strip() for d in value.replace(";", ",").split(",") if d.strip()]
                    vendor_record["domains"].extend(domains)
                elif target_field.startswith("custom_attributes."):
                    custom_field = target_field.replace("custom_attributes.", "")
                    vendor_record["custom_attributes"][custom_field] = value
            
            # Generate vendor_id if missing
            if not vendor_record["vendor_id"] and vendor_record["global_name"]:
                vendor_record["vendor_id"] = f"AUTO_{vendor_record['global_name'][:20].upper().replace(' ', '_')}_{row_num}"
            
            if vendor_record["global_name"]:
                transformed_vendors.append(vendor_record)
        
        return transformed_vendors
```

### Usage Example

```python
from services.vendor_csv_mapper import VendorCSVMapper
from services.bigquery_service import BigQueryService

# Initialize services
csv_mapper = VendorCSVMapper()
bigquery = BigQueryService()

# Read CSV file
with open('vendors.csv', 'rb') as f:
    csv_content = f.read()

# Step 1: Analyze headers and get AI mapping
analysis = csv_mapper.analyze_csv_headers(csv_content, filename='vendors.csv')

if analysis['success']:
    mapping = analysis['mapping']
    print(f"Detected language: {mapping['detectedLanguage']}")
    print(f"Source system: {mapping['sourceSystemGuess']}")
    print(f"Overall confidence: {mapping['overallConfidence']}")
    
    # Show column mappings
    for col, info in mapping['columnMapping'].items():
        print(f"  {col} → {info['targetField']} (confidence: {info['confidence']})")
    
    # Step 2: Transform data using the mapping
    transformed_vendors = csv_mapper.transform_csv_data(csv_content, mapping)
    print(f"Transformed {len(transformed_vendors)} vendors")
    
    # Step 3: Insert into BigQuery
    for vendor in transformed_vendors:
        bigquery.insert_vendor(vendor)
    
    print("Import complete!")
```

---

## 6. The Super Agent (LangGraph)

**Source Files:** 
- `agent/tools.py`
- `agent/brain.py`

### Required Secrets (.env)

```bash
# OpenRouter (Gemini 2.5 Pro for Agent - stable tool calling)
OPENROUTERA=sk-or-v1-xxxxxxxxxxxxxxxxxxxx

# LangSmith Tracing (optional but recommended)
LANGCHAIN_API_KEY=ls__xxxxxxxxxxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=pr-your-project-name
LANGCHAIN_TRACING_V2=true

# BigQuery (for data access)
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account",...}'

# Gmail & NetSuite (for tool access)
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
NETSUITE_ACCOUNT_ID=...
# ... (other secrets as needed)
```

### Core Class Code - Tools Definition

```python
"""
LangGraph Tools - Wraps existing services for LLM control
"""

import os
import json
from typing import Optional
from langchain_core.tools import tool

from services.gmail_service import GmailService
from services.netsuite_service import NetSuiteService
from services.bigquery_service import BigQueryService

# Initialize services
gmail_service = GmailService()
netsuite_service = NetSuiteService()
bigquery_service = BigQueryService()


@tool
def get_dashboard_status(user_email: str) -> str:
    """
    Get a comprehensive dashboard status - CALL THIS ON STARTUP.
    Returns vendor count, invoice count, Gmail status, NetSuite status.
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
    
    Returns:
        JSON with complete dashboard status
    """
    status = {
        "user_email": user_email,
        "vendor_count": 0,
        "invoice_count": 0,
        "pending_invoices": 0,
        "gmail_connected": False,
        "netsuite_connected": False,
        "suggested_actions": []
    }
    
    # Get vendor count
    vendor_query = """
    SELECT COUNT(*) as count 
    FROM `<PROJECT_ID>.vendors_ai.global_vendors`
    WHERE owner_email = @user_email
    """
    results = bigquery_service.query(vendor_query, {"user_email": user_email})
    if results:
        status["vendor_count"] = results[0].get("count", 0)
    
    return json.dumps(status, indent=2, default=str)


@tool
def search_database_first(user_email: str, query: str, search_type: str = "all") -> str:
    """
    Search the local database before using external services.
    
    Args:
        user_email: The logged-in user's email
        query: Search term (vendor name, invoice number, etc.)
        search_type: "vendors", "invoices", "subscriptions", or "all"
    
    Returns:
        JSON with search results
    """
    search_pattern = f"%{query.strip().lower()}%"
    
    results = {"vendors": [], "invoices": [], "subscriptions": []}
    
    if search_type in ["vendors", "all"]:
        vendor_query = """
        SELECT vendor_id, global_name, emails, domains
        FROM `<PROJECT_ID>.vendors_ai.global_vendors`
        WHERE owner_email = @user_email
          AND LOWER(global_name) LIKE @search_pattern
        LIMIT 10
        """
        results["vendors"] = bigquery_service.query(vendor_query, {
            "search_pattern": search_pattern,
            "user_email": user_email
        })
    
    return json.dumps(results, indent=2, default=str)


@tool
def search_gmail_invoices(user_email: str, days: int = 7, max_results: int = 20) -> str:
    """
    Search Gmail for invoice and receipt emails.
    
    Args:
        user_email: The logged-in user's email
        days: Number of days to look back (default: 7)
        max_results: Maximum number of emails (default: 20)
    
    Returns:
        JSON with list of invoice emails found
    """
    from flask import session
    
    stored_token = session.get('gmail_token')
    if not stored_token:
        return json.dumps({"error": "Gmail not connected", "action_required": True})
    
    service = gmail_service.build_service(stored_token)
    messages = gmail_service.search_invoice_emails(service, max_results=max_results, days=days)
    
    results = []
    for msg in messages[:10]:
        details = gmail_service.get_message_details(service, msg['id'])
        metadata = gmail_service.get_email_metadata(details)
        results.append({
            'id': metadata['id'],
            'subject': metadata.get('subject'),
            'from': metadata.get('from'),
            'date': metadata.get('date')
        })
    
    return json.dumps({"success": True, "emails": results}, indent=2)


@tool
def create_netsuite_bill(
    user_email: str,
    vendor_netsuite_id: str,
    invoice_number: str,
    amount: float,
    currency: str = "USD"
) -> str:
    """
    Create a vendor bill in NetSuite.
    
    Args:
        user_email: The logged-in user's email
        vendor_netsuite_id: The NetSuite internal ID of the vendor
        invoice_number: The invoice number
        amount: The total amount
        currency: Currency code (default: USD)
    
    Returns:
        JSON with created bill details
    """
    bill_data = {
        'vendor_netsuite_id': vendor_netsuite_id,
        'invoice_number': invoice_number,
        'total_amount': amount,
        'currency': currency,
        'line_items': [{'description': f"Invoice {invoice_number}", 'amount': amount}]
    }
    
    result = netsuite_service.create_vendor_bill(bill_data)
    
    return json.dumps({
        "success": True,
        "netsuite_bill_id": result.get('id'),
        "message": f"Created bill for ${amount} {currency}"
    }, indent=2)


def get_all_tools():
    """Return all available tools"""
    return [
        get_dashboard_status,
        search_database_first,
        search_gmail_invoices,
        create_netsuite_bill,
        # ... add more tools as needed
    ]
```

### Core Class Code - Graph Setup

```python
"""
LangGraph Brain - StateGraph with OpenRouter Gemini 2.5 Pro
"""

import os
from typing import Annotated, TypedDict, Sequence, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from .tools import get_all_tools


class AgentState(TypedDict):
    """State for the agent graph"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    user_email: Optional[str]


def create_llm():
    """Create the LLM using OpenRouter with Gemini 2.5 Pro"""
    api_key = os.getenv("OPENROUTERA")
    if not api_key:
        raise ValueError("OPENROUTERA environment variable not set")
    
    return ChatOpenAI(
        model="google/gemini-2.5-pro",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.1,
        max_tokens=8192
    )


def get_checkpointer():
    """Get SQLite checkpointer for conversation memory"""
    import sqlite3
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/agent_memory.db', check_same_thread=False)
    return SqliteSaver(conn)


def create_agent_graph(user_email: str = None):
    """Create the LangGraph agent"""
    
    tools = get_all_tools()
    llm = create_llm()
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = """You are an AP Automation Expert. Be direct and efficient.

RULES:
1. Call ONLY the tools needed - usually 1-2 max
2. Never apologize - state facts directly
3. Show data in clean HTML tables
4. After data, suggest ONE logical next action
"""
    
    def should_continue(state: AgentState) -> str:
        """Determine if we should continue to tools or end"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current messages"""
        from langchain_core.messages import SystemMessage
        
        messages = state["messages"]
        full_messages = [SystemMessage(content=system_prompt)] + list(messages)
        
        response = llm_with_tools.invoke(full_messages)
        return {"messages": [response]}
    
    # Create tool node
    tool_node = ToolNode(tools)
    
    # Build graph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END}
    )
    
    workflow.add_edge("tools", "agent")
    
    checkpointer = get_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


def run_agent(message: str, user_id: str = "default", user_email: str = None) -> dict:
    """
    Run the agent with a user message.
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        user_email: User's email for multi-tenant data isolation
        
    Returns:
        Dict with 'response' (text) and 'tools_used' (list)
    """
    graph = create_agent_graph(user_email)
    
    thread_id = f"thread_{user_id}_{os.urandom(4).hex()}"
    config = {"configurable": {"thread_id": thread_id}}
    
    input_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_email": user_email
    }
    
    tools_used = []
    
    result = graph.invoke(input_state, config=config)
    
    messages = result.get("messages", [])
    
    # Extract tools used
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None):
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
    
    # Get final response
    response_text = "I processed your request."
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            if not getattr(msg, 'tool_calls', None):
                response_text = msg.content
                break
    
    return {
        "response": response_text,
        "tools_used": tools_used,
        "thread_id": thread_id
    }
```

### Usage Example

```python
from agent.brain import run_agent, create_agent_graph

# Simple usage - run agent with a message
result = run_agent(
    message="Show me all vendors from NetSuite",
    user_id="user123",
    user_email="user@company.com"
)

print(f"Response: {result['response']}")
print(f"Tools used: {result['tools_used']}")

# For Flask integration
from flask import Flask, request, jsonify, session

app = Flask(__name__)

@app.route('/api/agent/chat', methods=['POST'])
def agent_chat():
    data = request.json
    message = data.get('message', '')
    user_email = session.get('user_email', 'guest@example.com')
    
    result = run_agent(
        message=message,
        user_id=session.get('user_id', 'guest'),
        user_email=user_email
    )
    
    return jsonify({
        'response': result['response'],
        'tools_used': result['tools_used']
    })

# For streaming responses
from agent.brain import stream_agent

def stream_response(message, user_email):
    for event in stream_agent(message, user_email=user_email):
        if event['type'] == 'content':
            yield f"data: {json.dumps({'content': event['content']})}\n\n"
        elif event['type'] == 'tool_call':
            yield f"data: {json.dumps({'tool': event['tool']})}\n\n"
```

---

## Summary - Model Hierarchy

| Component | Primary Model | Fallback Model |
|-----------|--------------|----------------|
| **LangGraph Agent** | Gemini 2.5 Pro (OpenRouter) | - |
| **Invoice Processing** | Gemini 3 Pro Preview (OpenRouter) | gemini-2.5-flash (AI Studio) |
| **Vendor Matching** | Gemini 3 Pro Preview (OpenRouter) | gemini-2.5-flash (AI Studio) |
| **CSV Mapping** | Gemini 3 Pro Preview (OpenRouter) | gemini-2.5-flash (AI Studio) |

**Why the split?**
- **Agent uses Gemini 2.5 Pro**: Stable tool calling, no thought_signature issues
- **Services use Gemini 3 Pro Preview**: Best reasoning for semantic tasks, with automatic fallback

---

## Environment Variables Summary

```bash
# OpenRouter (Primary AI)
OPENROUTERA=sk-or-v1-xxxxxxxxxxxxxxxxxxxx

# Google AI Studio (Fallback)
GOOGLE_GEMINI_API_KEY=<SET_IN_REPLIT_SECRETS>

# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account",...}'
GOOGLE_CLOUD_PROJECT_NUMBER=123456789012

# Document AI
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_LOCATION=us

# Vertex AI Search
VERTEX_AI_SEARCH_DATA_STORE_ID=your-data-store-id

# Gmail OAuth
GMAIL_CLIENT_ID=123456789-xxxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx

# NetSuite OAuth 1.0a
NETSUITE_ACCOUNT_ID=TSTDRV1234567
NETSUITE_CONSUMER_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_CONSUMER_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_TOKEN_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NETSUITE_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# LangSmith (Optional)
LANGCHAIN_API_KEY=ls__xxxxxxxxxxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=pr-your-project-name
```

---

*Document generated for Payouts.com AP Automation Migration*
