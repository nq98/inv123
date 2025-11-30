# Invoice Management Integration Guide

## Complete Technical Documentation for AP Automation Invoice Management

This guide provides everything needed to build a production-ready Invoice Management system with AI-powered PDF parsing, bulk upload support, and comprehensive invoice lifecycle management.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Database Schema](#database-schema)
3. [Backend API Endpoints](#backend-api-endpoints)
4. [AI Invoice Parsing Service](#ai-invoice-parsing-service)
5. [Frontend Components](#frontend-components)
6. [File Upload Handling](#file-upload-handling)
7. [Complete Code Examples](#complete-code-examples)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (React/Vue/HTML)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Upload PDF  │  │ Invoice List│  │Invoice Detail│ │  Filters    │ │
│  │ (Bulk/Single)│  │   Table     │  │   Panel     │ │  & Search   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────┼────────────────┼────────────────┼────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Flask API Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │POST /upload │  │GET /invoices│  │PUT /invoice │  │POST /approve│ │
│  │   /bulk     │  │             │  │   /:id      │  │   /reject   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────┼────────────────┼────────────────┼────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Service Layer                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Invoice Parser   │  │ Document AI      │  │ Gemini AI        │   │
│  │ (4-Layer Hybrid) │  │ (Google Cloud)   │  │ (Semantic Logic) │   │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘   │
└───────────┼─────────────────────┼─────────────────────┼─────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Google Cloud     │  │ BigQuery         │  │ Vertex AI Search │   │
│  │ Storage (PDFs)   │  │ (Invoice Data)   │  │ (RAG Context)    │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### BigQuery Table: `invoices`

```sql
CREATE TABLE IF NOT EXISTS `project_id.dataset.invoices` (
    -- Primary Key
    invoice_id STRING NOT NULL,
    
    -- Core Invoice Data
    invoice_number STRING,
    vendor_name STRING,
    vendor_id STRING,
    
    -- Financial Data
    amount FLOAT64,
    currency STRING DEFAULT 'USD',
    tax_amount FLOAT64,
    subtotal FLOAT64,
    
    -- Dates
    invoice_date DATE,
    due_date DATE,
    scheduled_date DATE,
    
    -- Payment Info
    payment_type STRING,  -- Wire, ACH, Card, PayPal, Venmo, Crypto
    payment_status STRING DEFAULT 'pending',  -- pending, paid, overdue, cancelled
    
    -- Categorization
    category STRING,
    gl_code STRING,
    description STRING,
    line_items STRING,  -- JSON array of line items
    
    -- Workflow Status
    status STRING DEFAULT 'pending',  -- pending, approved, rejected, paid
    approval_status STRING,
    approved_by STRING,
    approved_at TIMESTAMP,
    rejected_by STRING,
    rejected_at TIMESTAMP,
    rejection_reason STRING,
    
    -- Source Tracking
    source STRING,  -- upload, gmail, netsuite, manual
    original_filename STRING,
    gcs_path STRING,
    
    -- AI Extraction Metadata
    extraction_confidence FLOAT64,
    extraction_method STRING,
    raw_extraction JSON,
    
    -- User/Tenant Info
    user_email STRING,
    tenant_id STRING,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
```

### Invoice Status Flow

```
                    ┌──────────┐
                    │ Uploaded │
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
              ┌─────│ Pending  │─────┐
              │     └────┬─────┘     │
              │          │           │
              ▼          ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Approved │ │Scheduled │ │ Rejected │
        └────┬─────┘ └────┬─────┘ └──────────┘
             │            │
             ▼            ▼
        ┌──────────┐ ┌──────────┐
        │   Paid   │ │  Paid    │
        └──────────┘ └──────────┘
```

---

## Backend API Endpoints

### 1. Single PDF Upload

```python
@app.route('/api/invoices/upload', methods=['POST'])
@login_required
def upload_invoice():
    """
    Upload and parse a single invoice PDF
    
    Request:
        - file: PDF file (multipart/form-data)
        
    Response:
        {
            "status": "success",
            "invoice_id": "INV-2024-001",
            "extracted_data": {
                "vendor_name": "AWS Inc.",
                "invoice_number": "AWS-2024-11-001",
                "amount": 4532.99,
                "currency": "USD",
                "invoice_date": "2024-11-20",
                "due_date": "2024-12-20",
                "line_items": [...],
                "confidence": 0.95
            }
        }
    """
    pass
```

### 2. Bulk PDF Upload

```python
@app.route('/api/invoices/upload/bulk', methods=['POST'])
@login_required
def upload_invoices_bulk():
    """
    Upload and parse multiple invoice PDFs
    
    Request:
        - files[]: Multiple PDF files (multipart/form-data)
        
    Response:
        {
            "status": "success",
            "total": 5,
            "processed": 5,
            "results": [
                {"filename": "invoice1.pdf", "status": "success", "invoice_id": "..."},
                {"filename": "invoice2.pdf", "status": "success", "invoice_id": "..."},
                {"filename": "invoice3.pdf", "status": "error", "error": "..."}
            ]
        }
    """
    pass
```

### 3. List Invoices

```python
@app.route('/api/invoices', methods=['GET'])
@login_required
def list_invoices():
    """
    Get paginated list of invoices with filters
    
    Query Parameters:
        - page: int (default 1)
        - limit: int (default 50)
        - status: pending|approved|rejected|paid
        - payment_type: Wire|ACH|Card|PayPal|Venmo|Crypto
        - currency: USD|EUR|GBP|...
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
        - search: string (vendor name, invoice number)
        - sort_by: date|amount|vendor|status
        - sort_order: asc|desc
        
    Response:
        {
            "invoices": [...],
            "pagination": {
                "page": 1,
                "limit": 50,
                "total": 234,
                "pages": 5
            },
            "summary": {
                "total_pending": 12,
                "total_due": 47890,
                "overdue": 3,
                "awaiting_approval": 5,
                "paid_this_month": 124500,
                "scheduled": 4
            }
        }
    """
    pass
```

### 4. Get Invoice Details

```python
@app.route('/api/invoices/<invoice_id>', methods=['GET'])
@login_required
def get_invoice(invoice_id):
    """
    Get detailed invoice information
    
    Response:
        {
            "invoice_id": "INV-2024-001",
            "invoice_number": "AWS-2024-11-001",
            "vendor": {
                "name": "Amazon Web Services",
                "id": "vendor-123",
                "category": "Cloud Services"
            },
            "amount": 4532.99,
            "currency": "USD",
            "invoice_date": "2024-11-20",
            "due_date": "2024-12-20",
            "description": "Monthly cloud infrastructure and compute services",
            "line_items": [
                {"description": "EC2 Instances", "amount": 2500.00},
                {"description": "S3 Storage", "amount": 1200.00},
                {"description": "Data Transfer", "amount": 832.99}
            ],
            "payment_type": "Wire",
            "status": "pending",
            "approval_status": null,
            "pdf_url": "https://storage.googleapis.com/...",
            "created_at": "2024-11-20T10:30:00Z"
        }
    """
    pass
```

### 5. Approve Invoice

```python
@app.route('/api/invoices/<invoice_id>/approve', methods=['POST'])
@login_required
def approve_invoice(invoice_id):
    """
    Approve an invoice for payment
    
    Request:
        {
            "scheduled_date": "2024-12-18",  # Optional
            "notes": "Approved for payment"   # Optional
        }
        
    Response:
        {
            "status": "success",
            "message": "Invoice approved",
            "invoice_id": "INV-2024-001",
            "approved_by": "user@company.com",
            "approved_at": "2024-11-20T14:30:00Z"
        }
    """
    pass
```

### 6. Reject Invoice

```python
@app.route('/api/invoices/<invoice_id>/reject', methods=['POST'])
@login_required
def reject_invoice(invoice_id):
    """
    Reject an invoice
    
    Request:
        {
            "reason": "Duplicate invoice"  # Required
        }
        
    Response:
        {
            "status": "success",
            "message": "Invoice rejected",
            "invoice_id": "INV-2024-001",
            "rejected_by": "user@company.com",
            "rejected_at": "2024-11-20T14:30:00Z"
        }
    """
    pass
```

### 7. Export Invoices CSV

```python
@app.route('/api/invoices/export', methods=['GET'])
@login_required
def export_invoices():
    """
    Export invoices to CSV
    
    Query Parameters:
        - Same filters as list_invoices
        
    Response:
        - CSV file download
    """
    pass
```

### 8. Download Original PDF

```python
@app.route('/api/invoices/<invoice_id>/download', methods=['GET'])
@login_required
def download_invoice_pdf(invoice_id):
    """
    Get signed URL to download original invoice PDF
    
    Response:
        {
            "download_url": "https://storage.googleapis.com/...",
            "expires_in": 3600,
            "filename": "AWS-2024-11-001.pdf"
        }
    """
    pass
```

---

## AI Invoice Parsing Service

### 4-Layer Hybrid Extraction Architecture

```python
"""
Invoice Parsing Service - 4-Layer Hybrid Architecture

Layer 1: Document AI (Google Cloud)
    - OCR and layout extraction
    - Table detection
    - Entity recognition
    
Layer 2: Vertex AI Search RAG
    - Historical invoice context
    - Vendor pattern matching
    - Previous extraction corrections
    
Layer 3: Gemini AI Semantic Reasoning
    - Multi-language support (40+ languages)
    - Complex date parsing
    - Amount disambiguation
    - Receipt vs Invoice classification
    
Layer 4: Validation & Verification
    - Mathematical verification (subtotal + tax = total)
    - Cross-field validation
    - Confidence scoring
"""
```

### Complete Parsing Service Code

```python
# services/invoice_parser_service.py

import os
import json
import logging
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional, List
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google.cloud import bigquery
import google.generativeai as genai

logger = logging.getLogger(__name__)

class InvoiceParserService:
    """
    4-Layer Hybrid Invoice Parsing Engine
    
    Combines Document AI, Vertex RAG, and Gemini for
    accurate multi-language invoice extraction.
    """
    
    PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    LOCATION = 'us'
    PROCESSOR_ID = os.environ.get('DOCUMENT_AI_PROCESSOR_ID')
    GCS_BUCKET = os.environ.get('GCS_BUCKET', 'payouts-invoices')
    
    def __init__(self):
        # Initialize Google Cloud clients
        self._init_document_ai()
        self._init_storage()
        self._init_gemini()
        self._init_bigquery()
        
    def _init_document_ai(self):
        """Initialize Document AI client"""
        try:
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            if creds_json:
                import json
                from google.oauth2 import service_account
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.doc_ai_client = documentai.DocumentProcessorServiceClient(credentials=credentials)
            else:
                self.doc_ai_client = documentai.DocumentProcessorServiceClient()
            logger.info("Document AI client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Document AI: {e}")
            self.doc_ai_client = None
            
    def _init_storage(self):
        """Initialize GCS client"""
        try:
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            if creds_json:
                import json
                from google.oauth2 import service_account
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.storage_client = storage.Client(credentials=credentials)
            else:
                self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(self.GCS_BUCKET)
            logger.info("GCS client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GCS: {e}")
            self.storage_client = None
            
    def _init_gemini(self):
        """Initialize Gemini AI client"""
        try:
            api_key = os.environ.get('GOOGLE_GEMINI_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                self.gemini_model = genai.GenerativeModel('gemini-1.5-pro')
                logger.info("Gemini AI initialized")
            else:
                self.gemini_model = None
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.gemini_model = None
            
    def _init_bigquery(self):
        """Initialize BigQuery client"""
        try:
            creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            if creds_json:
                import json
                from google.oauth2 import service_account
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.bq_client = bigquery.Client(credentials=credentials, project=self.PROJECT_ID)
            else:
                self.bq_client = bigquery.Client(project=self.PROJECT_ID)
            logger.info("BigQuery client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery: {e}")
            self.bq_client = None

    def parse_invoice(self, file_content: bytes, filename: str, user_email: str) -> Dict[str, Any]:
        """
        Main entry point - Parse an invoice PDF using 4-layer hybrid approach
        
        Args:
            file_content: Raw PDF bytes
            filename: Original filename
            user_email: User who uploaded the invoice
            
        Returns:
            Dict with extracted invoice data and metadata
        """
        logger.info(f"Starting invoice parsing for: {filename}")
        
        # Generate unique invoice ID
        import uuid
        invoice_id = f"INV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        try:
            # Step 1: Upload to GCS
            gcs_path = self._upload_to_gcs(file_content, filename, user_email)
            
            # Step 2: Layer 1 - Document AI extraction
            doc_ai_result = self._extract_with_document_ai(file_content, filename)
            
            # Step 3: Layer 2 - Get RAG context from historical invoices
            rag_context = self._get_rag_context(doc_ai_result)
            
            # Step 4: Layer 3 - Gemini semantic reasoning
            gemini_result = self._semantic_extraction(doc_ai_result, rag_context, file_content)
            
            # Step 5: Layer 4 - Validation and verification
            validated_result = self._validate_extraction(gemini_result, doc_ai_result)
            
            # Step 6: Store in BigQuery
            self._store_invoice(invoice_id, validated_result, gcs_path, user_email, filename)
            
            return {
                'status': 'success',
                'invoice_id': invoice_id,
                'extracted_data': validated_result,
                'gcs_path': gcs_path,
                'confidence': validated_result.get('confidence', 0.0)
            }
            
        except Exception as e:
            logger.error(f"Invoice parsing failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'error': str(e),
                'invoice_id': invoice_id
            }
    
    def _upload_to_gcs(self, file_content: bytes, filename: str, user_email: str) -> str:
        """Upload invoice PDF to Google Cloud Storage"""
        if not self.storage_client:
            raise Exception("GCS client not initialized")
            
        # Create path: invoices/{user_email}/{date}/{filename}
        date_path = datetime.now().strftime('%Y/%m/%d')
        safe_email = user_email.replace('@', '_at_').replace('.', '_')
        gcs_path = f"invoices/{safe_email}/{date_path}/{filename}"
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(file_content, content_type='application/pdf')
        
        logger.info(f"Uploaded to GCS: {gcs_path}")
        return gcs_path
    
    def _extract_with_document_ai(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Layer 1: Extract using Google Document AI"""
        if not self.doc_ai_client or not self.PROCESSOR_ID:
            logger.warning("Document AI not available, using Gemini-only extraction")
            return {}
            
        try:
            # Determine MIME type
            mime_type = 'application/pdf'
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                mime_type = 'image/png' if filename.lower().endswith('.png') else 'image/jpeg'
            
            # Build processor name
            processor_name = self.doc_ai_client.processor_path(
                self.PROJECT_ID, self.LOCATION, self.PROCESSOR_ID
            )
            
            # Create document
            raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)
            
            # Process
            request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
            result = self.doc_ai_client.process_document(request=request)
            document = result.document
            
            # Extract entities
            extracted = {
                'text': document.text,
                'entities': {},
                'tables': [],
                'pages': len(document.pages)
            }
            
            for entity in document.entities:
                entity_type = entity.type_
                entity_value = entity.mention_text
                confidence = entity.confidence
                
                if entity_type not in extracted['entities']:
                    extracted['entities'][entity_type] = []
                    
                extracted['entities'][entity_type].append({
                    'value': entity_value,
                    'confidence': confidence
                })
            
            logger.info(f"Document AI extracted {len(extracted['entities'])} entity types")
            return extracted
            
        except Exception as e:
            logger.error(f"Document AI extraction failed: {e}")
            return {}
    
    def _get_rag_context(self, doc_ai_result: Dict) -> Dict[str, Any]:
        """Layer 2: Get historical context from Vertex AI Search"""
        # Extract potential vendor name for context lookup
        vendor_hint = None
        if 'entities' in doc_ai_result:
            supplier_entities = doc_ai_result['entities'].get('supplier_name', [])
            if supplier_entities:
                vendor_hint = supplier_entities[0].get('value')
        
        if not vendor_hint:
            return {}
            
        try:
            # Query historical invoices for this vendor
            query = f"""
                SELECT 
                    vendor_name,
                    invoice_number,
                    amount,
                    currency,
                    category,
                    payment_type
                FROM `{self.PROJECT_ID}.vendors_ai.invoices`
                WHERE LOWER(vendor_name) LIKE LOWER('%{vendor_hint[:20]}%')
                ORDER BY created_at DESC
                LIMIT 5
            """
            
            if self.bq_client:
                results = self.bq_client.query(query).result()
                historical = [dict(row) for row in results]
                
                if historical:
                    return {
                        'vendor_history': historical,
                        'typical_category': historical[0].get('category'),
                        'typical_payment_type': historical[0].get('payment_type')
                    }
        except Exception as e:
            logger.warning(f"RAG context lookup failed: {e}")
            
        return {}
    
    def _semantic_extraction(self, doc_ai_result: Dict, rag_context: Dict, 
                            file_content: bytes) -> Dict[str, Any]:
        """Layer 3: Gemini AI semantic reasoning and extraction"""
        if not self.gemini_model:
            logger.warning("Gemini not available")
            return self._fallback_extraction(doc_ai_result)
        
        # Build prompt with Document AI results and RAG context
        doc_text = doc_ai_result.get('text', '')[:8000]  # Limit text length
        
        rag_info = ""
        if rag_context.get('vendor_history'):
            rag_info = f"""
Historical Context for this vendor:
- Typical Category: {rag_context.get('typical_category', 'Unknown')}
- Typical Payment Type: {rag_context.get('typical_payment_type', 'Unknown')}
- Previous invoices found: {len(rag_context.get('vendor_history', []))}
"""

        prompt = f"""You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
{doc_text}

{rag_info}

EXTRACTION RULES:
1. Extract vendor/supplier name (company issuing the invoice)
2. Extract invoice number exactly as shown
3. Extract all monetary amounts (subtotal, tax, total)
4. Parse dates in ISO format (YYYY-MM-DD)
5. Identify currency (USD, EUR, GBP, etc.)
6. Extract line items with descriptions and amounts
7. Determine if this is an Invoice or Receipt
8. Assess payment terms and due date

MULTI-CURRENCY HANDLING:
- Look for currency symbols ($, €, £, ¥) and codes
- If multiple currencies appear, identify the primary invoice currency
- Note any currency conversion information

DATE PARSING (handle all formats):
- US format: MM/DD/YYYY
- EU format: DD/MM/YYYY or DD.MM.YYYY
- ISO format: YYYY-MM-DD
- Written format: "November 20, 2024"

Return a JSON object with this exact structure:
{{
    "vendor_name": "string",
    "invoice_number": "string",
    "invoice_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD or null",
    "amount": number,
    "subtotal": number or null,
    "tax_amount": number or null,
    "currency": "USD",
    "document_type": "invoice" or "receipt",
    "description": "brief description of services/goods",
    "line_items": [
        {{"description": "string", "quantity": number, "unit_price": number, "amount": number}}
    ],
    "payment_terms": "string or null",
    "category": "suggested category",
    "confidence": 0.0 to 1.0
}}

Return ONLY valid JSON, no markdown or explanation."""

        try:
            response = self.gemini_model.generate_content(prompt)
            result_text = response.text
            
            # Parse JSON from response
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
                
            extracted = json.loads(result_text.strip())
            logger.info(f"Gemini extracted invoice: {extracted.get('vendor_name')} - {extracted.get('amount')}")
            return extracted
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            return self._fallback_extraction(doc_ai_result)
    
    def _fallback_extraction(self, doc_ai_result: Dict) -> Dict[str, Any]:
        """Fallback extraction when Gemini is unavailable"""
        entities = doc_ai_result.get('entities', {})
        
        return {
            'vendor_name': self._get_first_entity(entities, 'supplier_name'),
            'invoice_number': self._get_first_entity(entities, 'invoice_id'),
            'invoice_date': self._get_first_entity(entities, 'invoice_date'),
            'due_date': self._get_first_entity(entities, 'due_date'),
            'amount': self._parse_amount(self._get_first_entity(entities, 'total_amount')),
            'currency': self._get_first_entity(entities, 'currency') or 'USD',
            'document_type': 'invoice',
            'confidence': 0.5
        }
    
    def _get_first_entity(self, entities: Dict, key: str) -> Optional[str]:
        """Get first value for an entity type"""
        values = entities.get(key, [])
        if values:
            return values[0].get('value')
        return None
    
    def _parse_amount(self, amount_str: Optional[str]) -> Optional[float]:
        """Parse amount string to float"""
        if not amount_str:
            return None
        try:
            # Remove currency symbols and commas
            cleaned = amount_str.replace('$', '').replace('€', '').replace('£', '')
            cleaned = cleaned.replace(',', '').strip()
            return float(cleaned)
        except:
            return None
    
    def _validate_extraction(self, gemini_result: Dict, doc_ai_result: Dict) -> Dict[str, Any]:
        """Layer 4: Validate and verify extraction"""
        validated = gemini_result.copy()
        
        # Mathematical verification
        subtotal = gemini_result.get('subtotal')
        tax = gemini_result.get('tax_amount')
        total = gemini_result.get('amount')
        
        if subtotal and tax and total:
            calculated_total = subtotal + tax
            if abs(calculated_total - total) > 0.01:
                # Math doesn't match - flag for review
                validated['validation_warning'] = f"Total mismatch: {subtotal} + {tax} != {total}"
                validated['confidence'] = min(validated.get('confidence', 1.0), 0.7)
        
        # Date validation
        invoice_date = validated.get('invoice_date')
        due_date = validated.get('due_date')
        
        if invoice_date and due_date:
            try:
                inv_dt = datetime.strptime(invoice_date, '%Y-%m-%d')
                due_dt = datetime.strptime(due_date, '%Y-%m-%d')
                if due_dt < inv_dt:
                    validated['validation_warning'] = "Due date is before invoice date"
                    validated['confidence'] = min(validated.get('confidence', 1.0), 0.7)
            except:
                pass
        
        # Ensure required fields
        if not validated.get('vendor_name'):
            validated['vendor_name'] = 'Unknown Vendor'
            validated['confidence'] = min(validated.get('confidence', 1.0), 0.5)
            
        if not validated.get('amount'):
            validated['amount'] = 0.0
            validated['confidence'] = min(validated.get('confidence', 1.0), 0.5)
        
        return validated
    
    def _store_invoice(self, invoice_id: str, data: Dict, gcs_path: str, 
                       user_email: str, filename: str):
        """Store extracted invoice in BigQuery"""
        if not self.bq_client:
            logger.warning("BigQuery not available, skipping storage")
            return
            
        table_id = f"{self.PROJECT_ID}.vendors_ai.invoices"
        
        row = {
            'invoice_id': invoice_id,
            'invoice_number': data.get('invoice_number'),
            'vendor_name': data.get('vendor_name'),
            'amount': data.get('amount'),
            'currency': data.get('currency', 'USD'),
            'tax_amount': data.get('tax_amount'),
            'subtotal': data.get('subtotal'),
            'invoice_date': data.get('invoice_date'),
            'due_date': data.get('due_date'),
            'description': data.get('description'),
            'category': data.get('category'),
            'line_items': json.dumps(data.get('line_items', [])),
            'status': 'pending',
            'payment_status': 'pending',
            'source': 'upload',
            'original_filename': filename,
            'gcs_path': gcs_path,
            'extraction_confidence': data.get('confidence', 0.0),
            'extraction_method': '4-layer-hybrid',
            'raw_extraction': json.dumps(data),
            'user_email': user_email,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        errors = self.bq_client.insert_rows_json(table_id, [row])
        if errors:
            logger.error(f"BigQuery insert errors: {errors}")
        else:
            logger.info(f"Stored invoice {invoice_id} in BigQuery")
    
    def parse_invoices_bulk(self, files: List[tuple], user_email: str) -> Dict[str, Any]:
        """
        Parse multiple invoices in bulk
        
        Args:
            files: List of (file_content, filename) tuples
            user_email: User who uploaded
            
        Returns:
            Summary with results for each file
        """
        results = []
        
        for file_content, filename in files:
            result = self.parse_invoice(file_content, filename, user_email)
            results.append({
                'filename': filename,
                'status': result.get('status'),
                'invoice_id': result.get('invoice_id'),
                'vendor_name': result.get('extracted_data', {}).get('vendor_name'),
                'amount': result.get('extracted_data', {}).get('amount'),
                'error': result.get('error')
            })
        
        successful = sum(1 for r in results if r['status'] == 'success')
        
        return {
            'status': 'success',
            'total': len(files),
            'processed': successful,
            'failed': len(files) - successful,
            'results': results
        }
    
    def get_download_url(self, invoice_id: str) -> Optional[str]:
        """Get signed URL to download invoice PDF"""
        if not self.bq_client or not self.storage_client:
            return None
            
        # Get GCS path from BigQuery
        query = f"""
            SELECT gcs_path, original_filename
            FROM `{self.PROJECT_ID}.vendors_ai.invoices`
            WHERE invoice_id = @invoice_id
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)
            ]
        )
        
        result = list(self.bq_client.query(query, job_config=job_config).result())
        if not result:
            return None
            
        gcs_path = result[0]['gcs_path']
        
        # Generate signed URL
        from datetime import timedelta
        blob = self.bucket.blob(gcs_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET"
        )
        
        return url
```

---

## Frontend Components

### Invoice List Table Component

```html
<!-- Invoice List Table -->
<div class="invoice-list-container">
    <div class="invoice-header">
        <h2>Pending Invoices</h2>
        <p>View and manage all incoming bills</p>
    </div>
    
    <div class="invoice-toolbar">
        <div class="search-box">
            <input type="text" id="invoiceSearch" placeholder="Search invoices and recipients...">
        </div>
        <button class="btn-secondary" onclick="showFilters()">
            <span>Filters</span>
        </button>
        <button class="btn-secondary" onclick="exportCSV()">
            <span>Export CSV</span>
        </button>
        <button class="btn-primary" onclick="showCreateInvoice()">
            + Create Invoice
        </button>
    </div>
    
    <table class="invoice-table">
        <thead>
            <tr>
                <th><input type="checkbox" id="selectAll"></th>
                <th>Issue Date</th>
                <th>Invoice #</th>
                <th>Recipient</th>
                <th>Payment Type</th>
                <th>Due Date</th>
                <th>Scheduled</th>
                <th>Amount</th>
                <th>Paid Ext.</th>
                <th>Status</th>
                <th>Approvals</th>
            </tr>
        </thead>
        <tbody id="invoiceTableBody">
            <!-- Rows populated by JavaScript -->
        </tbody>
    </table>
</div>
```

### Invoice Upload Modal

```html
<!-- Upload Modal -->
<div id="uploadModal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <h3>Upload Invoice</h3>
            <button class="close-btn" onclick="closeUploadModal()">&times;</button>
        </div>
        
        <div class="upload-tabs">
            <button class="tab-btn active" data-tab="single">Single Upload</button>
            <button class="tab-btn" data-tab="bulk">Bulk Upload</button>
        </div>
        
        <div id="singleUpload" class="tab-content active">
            <div class="upload-dropzone" id="singleDropzone">
                <div class="dropzone-content">
                    <div class="upload-icon">📄</div>
                    <p>Drag & drop your invoice PDF here</p>
                    <p class="or-text">or</p>
                    <button class="btn-secondary" onclick="document.getElementById('singleFileInput').click()">
                        Browse Files
                    </button>
                    <input type="file" id="singleFileInput" accept=".pdf,.png,.jpg,.jpeg" hidden>
                </div>
            </div>
            
            <div id="singleUploadProgress" class="upload-progress" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="singleProgressFill"></div>
                </div>
                <p id="singleProgressText">Uploading...</p>
            </div>
        </div>
        
        <div id="bulkUpload" class="tab-content">
            <div class="upload-dropzone" id="bulkDropzone">
                <div class="dropzone-content">
                    <div class="upload-icon">📁</div>
                    <p>Drag & drop multiple invoice PDFs</p>
                    <p class="or-text">or</p>
                    <button class="btn-secondary" onclick="document.getElementById('bulkFileInput').click()">
                        Browse Files
                    </button>
                    <input type="file" id="bulkFileInput" accept=".pdf,.png,.jpg,.jpeg" multiple hidden>
                </div>
            </div>
            
            <div id="bulkFileList" class="file-list" style="display: none;">
                <!-- File list populated here -->
            </div>
            
            <div id="bulkUploadProgress" class="upload-progress" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="bulkProgressFill"></div>
                </div>
                <p id="bulkProgressText">Processing 0 of 0 invoices...</p>
            </div>
        </div>
    </div>
</div>
```

### Invoice Details Sidebar

```html
<!-- Invoice Details Sidebar -->
<div id="invoiceDetailsSidebar" class="details-sidebar">
    <div class="sidebar-header">
        <h3>Invoice Details</h3>
        <p>View and manage invoice information</p>
        <button class="close-btn" onclick="closeDetailsSidebar()">&times;</button>
    </div>
    
    <div class="sidebar-content">
        <div class="status-badge" id="detailStatus">Pending</div>
        <div class="invoice-number" id="detailInvoiceNumber">AWS-2024-11-001</div>
        
        <div class="amount-display">
            <span class="amount" id="detailAmount">$4,532.99</span>
            <span class="currency" id="detailCurrency">USD</span>
        </div>
        
        <div class="detail-section">
            <h4>Invoice Information</h4>
            <div class="detail-grid">
                <div class="detail-item">
                    <label>Vendor</label>
                    <span id="detailVendor">Amazon Web Services</span>
                </div>
                <div class="detail-item">
                    <label>Category</label>
                    <span id="detailCategory">Cloud Services</span>
                </div>
                <div class="detail-item">
                    <label>Invoice Date</label>
                    <span id="detailInvoiceDate">2024-11-20</span>
                </div>
                <div class="detail-item">
                    <label>Due Date</label>
                    <span id="detailDueDate">2024-12-20</span>
                </div>
            </div>
        </div>
        
        <div class="detail-section">
            <h4>Description</h4>
            <p id="detailDescription">Monthly cloud infrastructure and compute services</p>
        </div>
        
        <div class="detail-section">
            <h4>Actions</h4>
            <div class="action-buttons">
                <button class="btn-secondary" onclick="downloadPDF()">
                    ⬇️ Download PDF
                </button>
                <button class="btn-secondary" onclick="printInvoice()">
                    🖨️ Print
                </button>
            </div>
            <div class="action-buttons primary">
                <button class="btn-success" onclick="approveInvoice()">
                    ✓ Approve
                </button>
                <button class="btn-danger" onclick="rejectInvoice()">
                    ✗ Reject
                </button>
            </div>
        </div>
    </div>
</div>
```

---

## JavaScript Implementation

```javascript
// invoice-management.js

class InvoiceManager {
    constructor() {
        this.invoices = [];
        this.currentPage = 1;
        this.pageSize = 50;
        this.filters = {};
        this.selectedInvoice = null;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadInvoices();
        this.setupUploadHandlers();
    }
    
    setupEventListeners() {
        // Search
        document.getElementById('invoiceSearch').addEventListener('input', 
            this.debounce(() => this.loadInvoices(), 300));
        
        // Select all checkbox
        document.getElementById('selectAll').addEventListener('change', (e) => {
            document.querySelectorAll('.invoice-checkbox').forEach(cb => {
                cb.checked = e.target.checked;
            });
        });
        
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });
    }
    
    setupUploadHandlers() {
        // Single file upload
        const singleDropzone = document.getElementById('singleDropzone');
        const singleInput = document.getElementById('singleFileInput');
        
        singleDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            singleDropzone.classList.add('dragover');
        });
        
        singleDropzone.addEventListener('dragleave', () => {
            singleDropzone.classList.remove('dragover');
        });
        
        singleDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            singleDropzone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadSingleFile(files[0]);
            }
        });
        
        singleInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadSingleFile(e.target.files[0]);
            }
        });
        
        // Bulk file upload
        const bulkDropzone = document.getElementById('bulkDropzone');
        const bulkInput = document.getElementById('bulkFileInput');
        
        bulkDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            bulkDropzone.classList.add('dragover');
        });
        
        bulkDropzone.addEventListener('dragleave', () => {
            bulkDropzone.classList.remove('dragover');
        });
        
        bulkDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            bulkDropzone.classList.remove('dragover');
            this.uploadBulkFiles(e.dataTransfer.files);
        });
        
        bulkInput.addEventListener('change', (e) => {
            this.uploadBulkFiles(e.target.files);
        });
    }
    
    async loadInvoices() {
        try {
            const search = document.getElementById('invoiceSearch').value;
            const params = new URLSearchParams({
                page: this.currentPage,
                limit: this.pageSize,
                search: search,
                ...this.filters
            });
            
            const response = await fetch(`/api/invoices?${params}`);
            const data = await response.json();
            
            this.invoices = data.invoices;
            this.renderInvoiceTable();
            this.updateSummaryCards(data.summary);
            
        } catch (error) {
            console.error('Failed to load invoices:', error);
            this.showToast('Failed to load invoices', 'error');
        }
    }
    
    renderInvoiceTable() {
        const tbody = document.getElementById('invoiceTableBody');
        tbody.innerHTML = '';
        
        this.invoices.forEach(invoice => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><input type="checkbox" class="invoice-checkbox" data-id="${invoice.invoice_id}"></td>
                <td>${this.formatDate(invoice.invoice_date)}</td>
                <td>${invoice.invoice_number || '-'}</td>
                <td>${invoice.vendor_name}</td>
                <td>${this.renderPaymentType(invoice.payment_type)}</td>
                <td>${this.renderDueDate(invoice.due_date)}</td>
                <td>${invoice.scheduled_date || '-'}</td>
                <td>${this.formatCurrency(invoice.amount, invoice.currency)}</td>
                <td>${invoice.paid_externally ? 'Yes' : 'No'}</td>
                <td>${this.renderStatus(invoice.status)}</td>
                <td>${this.renderApprovalStatus(invoice.approval_status)}</td>
            `;
            
            row.addEventListener('click', () => this.showInvoiceDetails(invoice));
            tbody.appendChild(row);
        });
    }
    
    renderPaymentType(type) {
        const colors = {
            'Wire': '#22c55e',
            'ACH': '#a855f7',
            'Card': '#3b82f6',
            'PayPal': '#0070ba',
            'Venmo': '#3d95ce',
            'Crypto': '#f7931a'
        };
        
        const color = colors[type] || '#6b7280';
        return `<span class="payment-badge" style="background: ${color}">${type || 'Unknown'}</span>`;
    }
    
    renderDueDate(dueDate) {
        if (!dueDate) return '-';
        
        const due = new Date(dueDate);
        const today = new Date();
        const isOverdue = due < today;
        
        const formatted = this.formatDate(dueDate);
        return isOverdue 
            ? `<span class="overdue">${formatted}</span>`
            : formatted;
    }
    
    renderStatus(status) {
        const styles = {
            'pending': 'background: #fef3c7; color: #92400e',
            'approved': 'background: #d1fae5; color: #065f46',
            'rejected': 'background: #fee2e2; color: #991b1b',
            'paid': 'background: #dbeafe; color: #1e40af'
        };
        
        return `<span class="status-badge" style="${styles[status] || ''}">${status}</span>`;
    }
    
    renderApprovalStatus(status) {
        if (!status) return '-';
        
        const icons = {
            'approved': '✓ Approved',
            'rejected': '✗ Rejected',
            'pending': '⏳ Pending'
        };
        
        return icons[status] || status;
    }
    
    async uploadSingleFile(file) {
        if (!this.validateFile(file)) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        this.showUploadProgress('single', 0, 'Uploading...');
        
        try {
            const response = await fetch('/api/invoices/upload', {
                method: 'POST',
                body: formData
            });
            
            this.showUploadProgress('single', 50, 'Processing with AI...');
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showUploadProgress('single', 100, 'Complete!');
                this.showToast(`Invoice parsed: ${data.extracted_data.vendor_name} - ${this.formatCurrency(data.extracted_data.amount)}`, 'success');
                this.loadInvoices();
                
                setTimeout(() => this.closeUploadModal(), 1500);
            } else {
                throw new Error(data.error || 'Upload failed');
            }
            
        } catch (error) {
            console.error('Upload failed:', error);
            this.showToast(`Upload failed: ${error.message}`, 'error');
            this.hideUploadProgress('single');
        }
    }
    
    async uploadBulkFiles(files) {
        const validFiles = Array.from(files).filter(f => this.validateFile(f, false));
        
        if (validFiles.length === 0) {
            this.showToast('No valid PDF files selected', 'error');
            return;
        }
        
        // Show file list
        this.showBulkFileList(validFiles);
        
        // Upload all files
        const formData = new FormData();
        validFiles.forEach(file => formData.append('files[]', file));
        
        this.showUploadProgress('bulk', 0, `Processing 0 of ${validFiles.length} invoices...`);
        
        try {
            const response = await fetch('/api/invoices/upload/bulk', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showUploadProgress('bulk', 100, 
                    `Complete! ${data.processed} of ${data.total} processed successfully`);
                
                this.showToast(`Bulk upload complete: ${data.processed} invoices processed`, 'success');
                this.loadInvoices();
                
                setTimeout(() => this.closeUploadModal(), 2000);
            } else {
                throw new Error(data.error || 'Bulk upload failed');
            }
            
        } catch (error) {
            console.error('Bulk upload failed:', error);
            this.showToast(`Bulk upload failed: ${error.message}`, 'error');
            this.hideUploadProgress('bulk');
        }
    }
    
    validateFile(file, showError = true) {
        const validTypes = ['application/pdf', 'image/png', 'image/jpeg'];
        const maxSize = 10 * 1024 * 1024; // 10MB
        
        if (!validTypes.includes(file.type)) {
            if (showError) this.showToast('Please upload a PDF or image file', 'error');
            return false;
        }
        
        if (file.size > maxSize) {
            if (showError) this.showToast('File size must be under 10MB', 'error');
            return false;
        }
        
        return true;
    }
    
    showBulkFileList(files) {
        const listContainer = document.getElementById('bulkFileList');
        listContainer.innerHTML = '';
        listContainer.style.display = 'block';
        
        files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.innerHTML = `
                <span class="file-icon">📄</span>
                <span class="file-name">${file.name}</span>
                <span class="file-size">${this.formatFileSize(file.size)}</span>
            `;
            listContainer.appendChild(item);
        });
    }
    
    showUploadProgress(type, percent, text) {
        const container = document.getElementById(`${type}UploadProgress`);
        const fill = document.getElementById(`${type}ProgressFill`);
        const textEl = document.getElementById(`${type}ProgressText`);
        
        container.style.display = 'block';
        fill.style.width = `${percent}%`;
        textEl.textContent = text;
    }
    
    hideUploadProgress(type) {
        document.getElementById(`${type}UploadProgress`).style.display = 'none';
    }
    
    showInvoiceDetails(invoice) {
        this.selectedInvoice = invoice;
        
        document.getElementById('detailStatus').textContent = invoice.status;
        document.getElementById('detailStatus').className = `status-badge ${invoice.status}`;
        document.getElementById('detailInvoiceNumber').textContent = invoice.invoice_number || 'N/A';
        document.getElementById('detailAmount').textContent = this.formatCurrency(invoice.amount, invoice.currency);
        document.getElementById('detailCurrency').textContent = invoice.currency || 'USD';
        document.getElementById('detailVendor').textContent = invoice.vendor_name;
        document.getElementById('detailCategory').textContent = invoice.category || 'Uncategorized';
        document.getElementById('detailInvoiceDate').textContent = this.formatDate(invoice.invoice_date);
        document.getElementById('detailDueDate').textContent = this.formatDate(invoice.due_date);
        document.getElementById('detailDescription').textContent = invoice.description || 'No description';
        
        document.getElementById('invoiceDetailsSidebar').classList.add('open');
    }
    
    closeDetailsSidebar() {
        document.getElementById('invoiceDetailsSidebar').classList.remove('open');
        this.selectedInvoice = null;
    }
    
    async approveInvoice() {
        if (!this.selectedInvoice) return;
        
        try {
            const response = await fetch(`/api/invoices/${this.selectedInvoice.invoice_id}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast('Invoice approved', 'success');
                this.loadInvoices();
                this.closeDetailsSidebar();
            } else {
                throw new Error(data.message || 'Approval failed');
            }
            
        } catch (error) {
            this.showToast(`Approval failed: ${error.message}`, 'error');
        }
    }
    
    async rejectInvoice() {
        if (!this.selectedInvoice) return;
        
        const reason = prompt('Please provide a reason for rejection:');
        if (!reason) return;
        
        try {
            const response = await fetch(`/api/invoices/${this.selectedInvoice.invoice_id}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast('Invoice rejected', 'success');
                this.loadInvoices();
                this.closeDetailsSidebar();
            } else {
                throw new Error(data.message || 'Rejection failed');
            }
            
        } catch (error) {
            this.showToast(`Rejection failed: ${error.message}`, 'error');
        }
    }
    
    async downloadPDF() {
        if (!this.selectedInvoice) return;
        
        try {
            const response = await fetch(`/api/invoices/${this.selectedInvoice.invoice_id}/download`);
            const data = await response.json();
            
            if (data.download_url) {
                window.open(data.download_url, '_blank');
            } else {
                throw new Error('No download URL available');
            }
            
        } catch (error) {
            this.showToast(`Download failed: ${error.message}`, 'error');
        }
    }
    
    async exportCSV() {
        try {
            const params = new URLSearchParams(this.filters);
            const response = await fetch(`/api/invoices/export?${params}`);
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `invoices_${new Date().toISOString().split('T')[0]}.csv`;
            a.click();
            
        } catch (error) {
            this.showToast('Export failed', 'error');
        }
    }
    
    updateSummaryCards(summary) {
        if (!summary) return;
        
        document.getElementById('totalPending').textContent = summary.total_pending || 0;
        document.getElementById('totalDue').textContent = this.formatCurrency(summary.total_due || 0);
        document.getElementById('overdueCount').textContent = summary.overdue || 0;
        document.getElementById('awaitingApproval').textContent = summary.awaiting_approval || 0;
        document.getElementById('paidThisMonth').textContent = this.formatCurrency(summary.paid_this_month || 0);
        document.getElementById('scheduledCount').textContent = summary.scheduled || 0;
    }
    
    // Utility methods
    formatDate(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
    
    formatCurrency(amount, currency = 'USD') {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency
        }).format(amount || 0);
    }
    
    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
    
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast') || this.createToast();
        toast.textContent = message;
        toast.className = `toast ${type}`;
        toast.style.display = 'block';
        
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
    
    createToast() {
        const toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        document.body.appendChild(toast);
        return toast;
    }
    
    debounce(func, wait) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }
    
    switchTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}Upload`);
        });
    }
    
    openUploadModal() {
        document.getElementById('uploadModal').style.display = 'flex';
    }
    
    closeUploadModal() {
        document.getElementById('uploadModal').style.display = 'none';
        this.hideUploadProgress('single');
        this.hideUploadProgress('bulk');
        document.getElementById('bulkFileList').style.display = 'none';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.invoiceManager = new InvoiceManager();
});
```

---

## CSS Styles

```css
/* invoice-management.css */

/* Invoice Table */
.invoice-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}

.invoice-table th {
    text-align: left;
    padding: 12px 16px;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 500;
    color: #6b7280;
}

.invoice-table td {
    padding: 12px 16px;
    border-bottom: 1px solid #f3f4f6;
}

.invoice-table tr:hover {
    background: #f9fafb;
    cursor: pointer;
}

/* Payment Type Badges */
.payment-badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    color: white;
}

/* Status Badges */
.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
}

.status-badge.pending {
    background: #fef3c7;
    color: #92400e;
}

.status-badge.approved {
    background: #d1fae5;
    color: #065f46;
}

.status-badge.rejected {
    background: #fee2e2;
    color: #991b1b;
}

.status-badge.paid {
    background: #dbeafe;
    color: #1e40af;
}

/* Overdue Date */
.overdue {
    color: #dc2626;
    font-weight: 500;
}

/* Upload Modal */
.modal {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    justify-content: center;
    align-items: center;
    z-index: 1000;
}

.modal-content {
    background: white;
    border-radius: 12px;
    padding: 24px;
    width: 90%;
    max-width: 500px;
    max-height: 80vh;
    overflow-y: auto;
}

/* Dropzone */
.upload-dropzone {
    border: 2px dashed #d1d5db;
    border-radius: 12px;
    padding: 48px 24px;
    text-align: center;
    transition: all 0.2s;
}

.upload-dropzone.dragover {
    border-color: #6366f1;
    background: #eef2ff;
}

.upload-icon {
    font-size: 48px;
    margin-bottom: 16px;
}

/* Progress Bar */
.progress-bar {
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
    margin: 16px 0;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
    transition: width 0.3s ease;
}

/* Details Sidebar */
.details-sidebar {
    position: fixed;
    top: 0;
    right: -400px;
    width: 400px;
    height: 100%;
    background: white;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
    transition: right 0.3s ease;
    z-index: 1000;
    overflow-y: auto;
}

.details-sidebar.open {
    right: 0;
}

.sidebar-header {
    padding: 24px;
    border-bottom: 1px solid #e5e7eb;
}

.sidebar-content {
    padding: 24px;
}

.amount-display {
    font-size: 32px;
    font-weight: 700;
    margin: 16px 0;
}

.detail-section {
    margin: 24px 0;
}

.detail-section h4 {
    font-size: 14px;
    color: #6b7280;
    margin-bottom: 12px;
}

.detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}

.detail-item label {
    display: block;
    font-size: 12px;
    color: #9ca3af;
    margin-bottom: 4px;
}

.action-buttons {
    display: flex;
    gap: 12px;
    margin: 12px 0;
}

.action-buttons.primary {
    margin-top: 24px;
}

/* Buttons */
.btn-primary {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
}

.btn-secondary {
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #e5e7eb;
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
}

.btn-success {
    background: #22c55e;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    flex: 1;
}

.btn-danger {
    background: white;
    color: #dc2626;
    border: 1px solid #dc2626;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    flex: 1;
}

/* Toast */
.toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 500;
    z-index: 2000;
}

.toast.success {
    background: #d1fae5;
    color: #065f46;
}

.toast.error {
    background: #fee2e2;
    color: #991b1b;
}

.toast.info {
    background: #dbeafe;
    color: #1e40af;
}

/* Summary Cards */
.summary-cards {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
}

.summary-card {
    flex: 1;
    background: white;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #e5e7eb;
}

.summary-card .value {
    font-size: 24px;
    font-weight: 700;
}

.summary-card .label {
    font-size: 12px;
    color: #6b7280;
}
```

---

## Environment Variables Required

```bash
# Google Cloud
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account",...}

# Document AI
DOCUMENT_AI_PROCESSOR_ID=your-processor-id

# Gemini AI
GOOGLE_GEMINI_API_KEY=your-gemini-api-key

# Storage
GCS_BUCKET=your-invoice-bucket

# Vertex AI Search (for RAG)
VERTEX_AI_SEARCH_DATA_STORE_ID=your-datastore-id
```

---

## Quick Start Integration

### 1. Copy the Parser Service
Copy `services/invoice_parser_service.py` to your project.

### 2. Add API Endpoints
Add the invoice endpoints to your Flask app (see Backend API Endpoints section).

### 3. Create BigQuery Table
Run the CREATE TABLE SQL in BigQuery console.

### 4. Add Frontend Components
Copy the HTML, CSS, and JavaScript to your frontend.

### 5. Configure Environment
Set up all required environment variables.

### 6. Test Upload
Test with a sample PDF to verify the full pipeline works.

---

## Support

For questions or issues with this integration, refer to:
- Google Document AI documentation
- Gemini API documentation
- BigQuery ML documentation

