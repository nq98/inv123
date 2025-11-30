# INVOICE MANAGEMENT IMPLEMENTATION PROMPT

## FOR: Adding Invoice Uploader to AP Automation Tab

---

## CRITICAL: USE EXISTING INFRASTRUCTURE

The main project already has a complete AI invoice processing pipeline. You must integrate with it, not rebuild it.

### Existing Components to USE:

| Component | Location | Purpose |
|-----------|----------|---------|
| `invoice_processor.py` | Root | Complete 4-layer AI parsing pipeline |
| `services/document_ai_service.py` | Services | Document AI OCR extraction |
| `services/gemini_service.py` | Services | Gemini semantic reasoning |
| `services/vertex_search_service.py` | Services | RAG context retrieval |
| `services/bigquery_service.py` | Services | BigQuery data storage |
| `services/pdf_generator.py` | Services | GCS upload & PDF handling |
| `config.py` | Root | All secrets and configuration |
| `app.py` | Root | Existing API endpoints |

---

## EXISTING SECRETS (Already Configured)

```python
# config.py - All these exist
GOOGLE_CLOUD_PROJECT_ID = '<PROJECT_ID>'
GCS_INPUT_BUCKET = 'payouts-invoices'            # GCS bucket for PDFs
DOCAI_PROCESSOR_ID = '<SET_IN_REPLIT_SECRETS>'          # Document AI processor
VERTEX_SEARCH_DATA_STORE_ID = 'invoices-ds'      # RAG datastore
GOOGLE_GEMINI_API_KEY = <from secrets>           # Gemini API

# Authentication
GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON = <from secrets>  # Service account
```

---

## EXISTING GCS + SIGNED URL ENDPOINTS

### Already Built in `app.py`:

```
GET /api/invoices/gcs/signed-url?gcs_uri=gs://payouts-invoices/...
```

**Response:**
```json
{
  "success": true,
  "download_url": "https://storage.googleapis.com/payouts-invoices/...",
  "gcs_uri": "gs://payouts-invoices/uploads/invoice.pdf",
  "file_type": "pdf",
  "content_type": "application/pdf",
  "expires_in": 3600
}
```

### GCS Upload Path Structure:
```
gs://payouts-invoices/uploads/{filename}         # Uploaded invoices
gs://payouts-invoices/generated/{filename}       # Generated PDFs
gs://payouts-invoices/invoices/{email}/{date}/   # User-specific storage
```

---

## EXISTING 4-LAYER AI PIPELINE

### `invoice_processor.py` - Already Built:

```
┌─────────────────────────────────────────────────────────────────────┐
│                   EXISTING PIPELINE (invoice_processor.py)           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1: Document AI (document_ai_service.py)                      │
│  └── OCR, table detection, entity extraction                        │
│                                                                      │
│  Layer 1.5: Multi-Currency Detection                                 │
│  └── Currency symbols, exchange rates, base/settlement currency    │
│                                                                      │
│  Layer 2: Vertex AI Search RAG (vertex_search_service.py)           │
│  └── Historical context, vendor matching, past extractions         │
│                                                                      │
│  Layer 3: Gemini Semantic Validation (gemini_service.py)            │
│  └── AI reasoning, date parsing, amount validation, math check     │
│                                                                      │
│  Layer 3.5: Semantic Vendor Resolution                               │
│  └── True vendor identity, legal beneficiary detection              │
│                                                                      │
│  Feedback Loop: Store successful extractions to knowledge base      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### How to Use It:

```python
from invoice_processor import InvoiceProcessor

processor = InvoiceProcessor()

# Option 1: Process from local file (auto-uploads to GCS)
result = processor.process_local_file('path/to/invoice.pdf', 'application/pdf')

# Option 2: Process from GCS URI
result = processor.process_invoice('gs://payouts-invoices/uploads/invoice.pdf', 'application/pdf')

# Result contains:
# - result['gcs_uri'] - GCS path to original file
# - result['validated_data'] - AI-extracted invoice data
# - result['layers'] - Processing status per layer
# - result['status'] - 'completed' or 'error'
```

---

## WHAT YOU NEED TO BUILD

### 1. New BigQuery Table: `invoices`

Create table in `vendors_ai` dataset:

```sql
CREATE TABLE IF NOT EXISTS `<PROJECT_ID>.vendors_ai.invoices` (
    invoice_id STRING NOT NULL,
    invoice_number STRING,
    vendor_name STRING,
    vendor_id STRING,
    
    -- Financial
    amount FLOAT64,
    currency STRING DEFAULT 'USD',
    tax_amount FLOAT64,
    subtotal FLOAT64,
    
    -- Dates
    invoice_date DATE,
    due_date DATE,
    
    -- Payment
    payment_type STRING,  -- Wire, ACH, Card, PayPal, Venmo, Crypto
    
    -- Workflow
    status STRING DEFAULT 'pending',  -- pending, approved, rejected, paid
    approved_by STRING,
    approved_at TIMESTAMP,
    rejected_by STRING,
    rejected_at TIMESTAMP,
    rejection_reason STRING,
    
    -- Storage
    gcs_uri STRING,  -- gs://payouts-invoices/...
    original_filename STRING,
    
    -- AI Metadata
    extraction_confidence FLOAT64,
    raw_extraction JSON,
    
    -- User
    user_email STRING,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
```

### 2. New API Endpoints (Add to `app.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/invoices/upload` | POST | Upload single PDF → AI parse → Store |
| `/api/invoices/upload/bulk` | POST | Upload multiple PDFs |
| `/api/invoices` | GET | List invoices with filters |
| `/api/invoices/<id>` | GET | Get invoice details |
| `/api/invoices/<id>` | PUT | Update invoice |
| `/api/invoices/<id>/approve` | POST | Approve for payment |
| `/api/invoices/<id>/reject` | POST | Reject with reason |
| `/api/invoices/<id>/download` | GET | Get signed URL (use existing endpoint) |
| `/api/invoices/export` | GET | Export to CSV |

### 3. Upload Endpoint Implementation

```python
@app.route('/api/invoices/upload', methods=['POST'])
@login_required
def upload_invoice():
    """Upload and parse invoice PDF using existing 4-layer pipeline"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    # Save temporarily
    import tempfile
    import uuid
    
    temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}_{file.filename}")
    file.save(temp_path)
    
    # Determine MIME type
    ext = file.filename.lower().split('.')[-1]
    mime_type = 'application/pdf' if ext == 'pdf' else f'image/{ext}'
    
    # Use EXISTING invoice processor
    from invoice_processor import InvoiceProcessor
    processor = InvoiceProcessor()
    result = processor.process_local_file(temp_path, mime_type)
    
    # Clean up temp file
    os.remove(temp_path)
    
    if result.get('status') == 'error':
        return jsonify({'error': result.get('error')}), 500
    
    # Generate invoice ID
    invoice_id = f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    
    # Extract validated data
    validated = result.get('validated_data', {})
    vendor = validated.get('vendor', {})
    totals = validated.get('totals', {})
    
    # Store in BigQuery invoices table
    from services.bigquery_service import BigQueryService
    bq = BigQueryService()
    
    invoice_row = {
        'invoice_id': invoice_id,
        'invoice_number': validated.get('invoiceNumber'),
        'vendor_name': vendor.get('name'),
        'vendor_id': vendor.get('vendor_id'),
        'amount': totals.get('total'),
        'currency': validated.get('currency', 'USD'),
        'tax_amount': totals.get('taxTotal'),
        'subtotal': totals.get('subtotal'),
        'invoice_date': validated.get('invoiceDate'),
        'due_date': validated.get('dueDate'),
        'payment_type': validated.get('paymentType'),
        'status': 'pending',
        'gcs_uri': result.get('gcs_uri'),
        'original_filename': file.filename,
        'extraction_confidence': validated.get('extractionConfidence', 0.0),
        'raw_extraction': json.dumps(validated),
        'user_email': session.get('user_email'),
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }
    
    # Insert into BigQuery
    # (Add insert_invoice method to BigQueryService)
    
    return jsonify({
        'status': 'success',
        'invoice_id': invoice_id,
        'extracted_data': {
            'vendor_name': vendor.get('name'),
            'invoice_number': validated.get('invoiceNumber'),
            'amount': totals.get('total'),
            'currency': validated.get('currency'),
            'invoice_date': validated.get('invoiceDate'),
            'due_date': validated.get('dueDate'),
            'payment_type': validated.get('paymentType'),
            'line_items': validated.get('lineItems', [])
        },
        'gcs_uri': result.get('gcs_uri'),
        'confidence': validated.get('extractionConfidence', 0.0)
    })
```

### 4. Get Download URL (Use Existing)

```python
@app.route('/api/invoices/<invoice_id>/download', methods=['GET'])
@login_required
def download_invoice(invoice_id):
    """Get signed URL for invoice PDF - uses existing GCS signed URL logic"""
    
    # Get invoice from BigQuery
    # ... query to get gcs_uri ...
    
    # Use existing signed URL endpoint
    gcs_uri = invoice['gcs_uri']
    
    # Same logic as /api/invoices/gcs/signed-url
    # ... generate signed URL ...
    
    return jsonify({
        'status': 'success',
        'download_url': signed_url,
        'expires_in': 3600
    })
```

### 5. Frontend Components

**InvoiceUpload.tsx** - Drag & drop with progress
**InvoiceList.tsx** - Table with filters, status badges, payment type badges
**InvoiceDetail.tsx** - Full view with approve/reject buttons and PDF viewer

---

## PAYMENT TYPE DETECTION

The existing Gemini service detects payment types. Extract from `validated_data['paymentType']`:

| Type | Badge Color | Indicators |
|------|-------------|------------|
| Wire | Blue | Bank details, SWIFT, routing number |
| ACH | Green | ACH transfer, US bank |
| Card | Purple | Credit card, Visa, Mastercard |
| PayPal | Navy | PayPal email/link |
| Venmo | Teal | Venmo username |
| Crypto | Orange | Bitcoin, Ethereum, wallet address |
| Check | Gray | Mail check instructions |

---

## COMPLETE FLOW

```
User uploads PDF
       ↓
Save to temp file
       ↓
InvoiceProcessor.process_local_file()
       ↓
   ┌───────────────────────────────────────┐
   │  Layer 1: Document AI → OCR          │
   │  Layer 1.5: Currency Detection        │
   │  Layer 2: Vertex RAG → Context        │
   │  Layer 3: Gemini → Semantic Extract   │
   │  Layer 3.5: Vendor Resolution         │
   │  Auto-uploads to GCS during process   │
   └───────────────────────────────────────┘
       ↓
validated_data + gcs_uri returned
       ↓
Store in BigQuery `invoices` table
       ↓
Return extracted data to frontend
       ↓
Frontend displays with:
- Vendor name, amount, dates
- Payment type badge
- Download PDF link (signed URL)
- Approve/Reject buttons
```

---

## FILES TO CREATE/MODIFY

1. **Modify `services/bigquery_service.py`**
   - Add `insert_invoice()` method
   - Add `list_invoices()` method
   - Add `update_invoice()` method
   - Add `approve_invoice()` / `reject_invoice()` methods

2. **Modify `app.py`**
   - Add `/api/invoices/upload` endpoint
   - Add `/api/invoices/upload/bulk` endpoint
   - Add `/api/invoices` list endpoint
   - Add `/api/invoices/<id>` CRUD endpoints
   - Add `/api/invoices/<id>/approve` endpoint
   - Add `/api/invoices/<id>/reject` endpoint
   - Add `/api/invoices/export` CSV export

3. **Create Frontend (TypeScript/React)**
   - `client/src/components/InvoiceUpload.tsx`
   - `client/src/components/InvoiceList.tsx`
   - `client/src/components/InvoiceDetail.tsx`
   - Add to AP Automation tab

---

## REFERENCE DOCUMENTATION

Read these files in `docs/docs/`:
- `invoice_parser_service_complete.ts` - TypeScript reference
- `invoice_management_api.ts` - Express API routes reference
- `INVOICE_MANAGEMENT_TYPESCRIPT_GUIDE.md` - Full guide
- `INVOICE_MANAGEMENT_PROMPTS_AND_SECRETS.md` - AI prompts

---

## START IMPLEMENTATION

1. Create BigQuery `invoices` table schema
2. Add invoice methods to `BigQueryService`
3. Add upload endpoint to `app.py` using existing `InvoiceProcessor`
4. Add list/CRUD/approve/reject endpoints
5. Build frontend upload component
6. Build invoice list with filters
7. Build invoice detail with approve/reject and PDF download
8. Test full flow

**Key Point:** Use the EXISTING `invoice_processor.py` pipeline. It already uploads to GCS (`payouts-invoices` bucket) and returns `gcs_uri`. Use existing `/api/invoices/gcs/signed-url` for download links.
