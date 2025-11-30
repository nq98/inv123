# Invoice Management - AI Prompts & Secrets Configuration

## Complete Reference for AI Prompts and Environment Secrets

This document provides all AI prompts used in the Invoice Management system and detailed configuration for each Google Cloud service and secret.

---

## Table of Contents

1. [Secrets Overview](#secrets-overview)
2. [Google Document AI](#google-document-ai)
3. [Google Gemini AI](#google-gemini-ai)
4. [Google Cloud Storage (GCS)](#google-cloud-storage)
5. [Google BigQuery](#google-bigquery)
6. [Vertex AI Search (RAG)](#vertex-ai-search-rag)
7. [Complete Prompts Reference](#complete-prompts-reference)

---

## Secrets Overview

### Required Secrets (Same Names as Main Project)

| Secret Name | Service | Description |
|-------------|---------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | All Google Cloud | Service account JSON for authentication |
| `GOOGLE_GEMINI_API_KEY` | Gemini AI | API key for Gemini 1.5 Pro |
| `GOOGLE_CLOUD_PROJECT` | All Google Cloud | Your GCP project ID |
| `DOCUMENT_AI_PROCESSOR_ID` | Document AI | Invoice processor ID |
| `GCS_BUCKET` | Cloud Storage | Bucket name for storing PDFs |
| `VERTEX_AI_SEARCH_DATA_STORE_ID` | Vertex AI Search | Data store ID for RAG |

### Environment Variables

```bash
# ============================================
# INVOICE MANAGEMENT SECRETS
# ============================================

# Google Cloud Project ID
GOOGLE_CLOUD_PROJECT=your-project-id

# Service Account Credentials (JSON string - same as main project)
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project-id","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"your-service-account@your-project-id.iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/..."}

# Gemini AI API Key
GOOGLE_GEMINI_API_KEY=AIza...your-api-key

# Document AI Processor
DOCUMENT_AI_PROCESSOR_ID=abc123def456
DOCUMENT_AI_LOCATION=us

# Cloud Storage Bucket
GCS_BUCKET=payouts-invoices

# BigQuery Dataset
BIGQUERY_DATASET=vendors_ai

# Vertex AI Search (for RAG)
VERTEX_AI_SEARCH_DATA_STORE_ID=your-datastore-id
```

---

## Google Document AI

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Authentication to Document AI API |
| `GOOGLE_CLOUD_PROJECT` | Project ID for processor path |
| `DOCUMENT_AI_PROCESSOR_ID` | Specific invoice parser processor |
| `DOCUMENT_AI_LOCATION` | Region (default: `us`) |

### TypeScript Configuration

```typescript
import { DocumentProcessorServiceClient } from '@google-cloud/documentai';

// Initialize with credentials from secret
const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
const credentials = JSON.parse(credentialsJson);
const projectId = process.env.GOOGLE_CLOUD_PROJECT;
const location = process.env.DOCUMENT_AI_LOCATION || 'us';
const processorId = process.env.DOCUMENT_AI_PROCESSOR_ID;

const client = new DocumentProcessorServiceClient({ credentials });

// Build processor name
const processorName = `projects/${projectId}/locations/${location}/processors/${processorId}`;
```

### Python Configuration

```python
import os
import json
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account

# Load credentials from secret
creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
creds_dict = json.loads(creds_json)
credentials = service_account.Credentials.from_service_account_info(creds_dict)

# Initialize client
client = documentai.DocumentProcessorServiceClient(credentials=credentials)

# Build processor path
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
location = os.environ.get('DOCUMENT_AI_LOCATION', 'us')
processor_id = os.environ.get('DOCUMENT_AI_PROCESSOR_ID')
processor_name = client.processor_path(project_id, location, processor_id)
```

### How Document AI Is Used

```typescript
// Process invoice PDF
const [result] = await client.processDocument({
  name: processorName,
  rawDocument: {
    content: pdfBuffer.toString('base64'),
    mimeType: 'application/pdf',
  },
});

// Extract entities
const entities = result.document.entities;
// Returns: supplier_name, invoice_id, invoice_date, due_date, total_amount, currency, line_items
```

---

## Google Gemini AI

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_GEMINI_API_KEY` | API key for Gemini 1.5 Pro |

### TypeScript Configuration

```typescript
import { GoogleGenerativeAI } from '@google/generative-ai';

// Initialize with API key from secret
const apiKey = process.env.GOOGLE_GEMINI_API_KEY;
const genAI = new GoogleGenerativeAI(apiKey);
const model = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
```

### Python Configuration

```python
import os
import google.generativeai as genai

# Initialize with API key from secret
api_key = os.environ.get('GOOGLE_GEMINI_API_KEY')
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')
```

### Main Invoice Extraction Prompt

```
You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
{document_text}

{rag_context_if_available}

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
{
    "vendorName": "string",
    "invoiceNumber": "string or null",
    "invoiceDate": "YYYY-MM-DD or null",
    "dueDate": "YYYY-MM-DD or null",
    "amount": number,
    "subtotal": number or null,
    "taxAmount": number or null,
    "currency": "USD",
    "documentType": "invoice" or "receipt",
    "description": "brief description or null",
    "lineItems": [
        {"description": "string", "quantity": number, "unitPrice": number, "amount": number}
    ],
    "paymentTerms": "string or null",
    "category": "suggested category or null",
    "confidence": 0.0 to 1.0
}

Return ONLY valid JSON, no markdown or explanation.
```

### How Gemini Is Used

```typescript
// Send prompt to Gemini
const result = await model.generateContent(prompt);
const response = await result.response;
let text = response.text();

// Parse JSON from response
if (text.includes('```json')) {
  text = text.split('```json')[1].split('```')[0];
}
const extractedData = JSON.parse(text.trim());
```

---

## Google Cloud Storage

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Authentication to GCS |
| `GCS_BUCKET` | Bucket name for invoice PDFs |

### TypeScript Configuration

```typescript
import { Storage } from '@google-cloud/storage';

// Initialize with credentials from secret
const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
const credentials = JSON.parse(credentialsJson);
const bucketName = process.env.GCS_BUCKET || 'payouts-invoices';

const storage = new Storage({ credentials });
const bucket = storage.bucket(bucketName);
```

### Python Configuration

```python
import os
import json
from google.cloud import storage
from google.oauth2 import service_account

# Load credentials from secret
creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
creds_dict = json.loads(creds_json)
credentials = service_account.Credentials.from_service_account_info(creds_dict)

# Initialize client
storage_client = storage.Client(credentials=credentials)
bucket_name = os.environ.get('GCS_BUCKET', 'payouts-invoices')
bucket = storage_client.bucket(bucket_name)
```

### How GCS Is Used

```typescript
// Upload invoice PDF
const gcsPath = `invoices/${userEmail}/${datePath}/${filename}`;
const file = bucket.file(gcsPath);
await file.save(pdfBuffer, {
  contentType: 'application/pdf',
  metadata: { uploadedBy: userEmail }
});

// Generate signed URL for download
const [signedUrl] = await file.getSignedUrl({
  version: 'v4',
  action: 'read',
  expires: Date.now() + 60 * 60 * 1000 // 1 hour
});
```

---

## Google BigQuery

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Authentication to BigQuery |
| `GOOGLE_CLOUD_PROJECT` | Project ID |
| `BIGQUERY_DATASET` | Dataset name (default: `vendors_ai`) |

### TypeScript Configuration

```typescript
import { BigQuery } from '@google-cloud/bigquery';

// Initialize with credentials from secret
const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
const credentials = JSON.parse(credentialsJson);
const projectId = process.env.GOOGLE_CLOUD_PROJECT;
const datasetId = process.env.BIGQUERY_DATASET || 'vendors_ai';

const bigquery = new BigQuery({ credentials, projectId });
const tableId = `${projectId}.${datasetId}.invoices`;
```

### Python Configuration

```python
import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

# Load credentials from secret
creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
creds_dict = json.loads(creds_json)
credentials = service_account.Credentials.from_service_account_info(creds_dict)

# Initialize client
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
bq_client = bigquery.Client(credentials=credentials, project=project_id)
dataset_id = os.environ.get('BIGQUERY_DATASET', 'vendors_ai')
table_id = f"{project_id}.{dataset_id}.invoices"
```

### BigQuery Table Schema

```sql
CREATE TABLE IF NOT EXISTS `{project_id}.{dataset_id}.invoices` (
    invoice_id STRING NOT NULL,
    invoice_number STRING,
    vendor_name STRING,
    vendor_id STRING,
    amount FLOAT64,
    currency STRING DEFAULT 'USD',
    tax_amount FLOAT64,
    subtotal FLOAT64,
    invoice_date DATE,
    due_date DATE,
    scheduled_date DATE,
    payment_type STRING,
    payment_status STRING DEFAULT 'pending',
    category STRING,
    gl_code STRING,
    description STRING,
    line_items STRING,
    status STRING DEFAULT 'pending',
    approval_status STRING,
    approved_by STRING,
    approved_at TIMESTAMP,
    rejected_by STRING,
    rejected_at TIMESTAMP,
    rejection_reason STRING,
    source STRING,
    original_filename STRING,
    gcs_path STRING,
    extraction_confidence FLOAT64,
    extraction_method STRING,
    raw_extraction STRING,
    user_email STRING,
    tenant_id STRING,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
```

### How BigQuery Is Used

```typescript
// Store invoice
await bigquery.dataset(datasetId).table('invoices').insert([invoiceRow]);

// Query invoices
const [rows] = await bigquery.query({
  query: `SELECT * FROM \`${tableId}\` WHERE user_email = @email`,
  params: { email: userEmail }
});

// Update invoice status
await bigquery.query({
  query: `UPDATE \`${tableId}\` SET status = 'approved' WHERE invoice_id = '${invoiceId}'`
});
```

---

## Vertex AI Search (RAG)

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Authentication |
| `GOOGLE_CLOUD_PROJECT` | Project ID |
| `VERTEX_AI_SEARCH_DATA_STORE_ID` | Data store for historical invoices |

### TypeScript Configuration

```typescript
import { SearchServiceClient } from '@google-cloud/discoveryengine';

const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
const credentials = JSON.parse(credentialsJson);
const projectId = process.env.GOOGLE_CLOUD_PROJECT;
const dataStoreId = process.env.VERTEX_AI_SEARCH_DATA_STORE_ID;

const client = new SearchServiceClient({ credentials });
const servingConfig = `projects/${projectId}/locations/global/collections/default_collection/dataStores/${dataStoreId}/servingConfigs/default_search`;
```

### Python Configuration

```python
import os
import json
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account

# Load credentials from secret
creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
creds_dict = json.loads(creds_json)
credentials = service_account.Credentials.from_service_account_info(creds_dict)

# Initialize client
client = discoveryengine.SearchServiceClient(credentials=credentials)
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
data_store_id = os.environ.get('VERTEX_AI_SEARCH_DATA_STORE_ID')
serving_config = f"projects/{project_id}/locations/global/collections/default_collection/dataStores/{data_store_id}/servingConfigs/default_search"
```

### How RAG Is Used

```typescript
// Search for historical invoice context
const [response] = await client.search({
  servingConfig,
  query: vendorName,
  pageSize: 5,
});

// Use historical data to improve extraction
const ragContext = {
  typicalCategory: response.results[0]?.document?.category,
  typicalPaymentType: response.results[0]?.document?.paymentType,
};
```

---

## Complete Prompts Reference

### 1. Main Invoice Extraction Prompt (Gemini 1.5 Pro)

**Used In:** `InvoiceParserService.extractInvoiceData()`

**Purpose:** Extract structured invoice data from OCR text

```
You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
{document_text_from_document_ai}

Historical Context for this vendor:
- Typical Category: {rag_context.typicalCategory}
- Typical Payment Type: {rag_context.typicalPaymentType}

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
{
    "vendorName": "string",
    "invoiceNumber": "string or null",
    "invoiceDate": "YYYY-MM-DD or null",
    "dueDate": "YYYY-MM-DD or null",
    "amount": number,
    "subtotal": number or null,
    "taxAmount": number or null,
    "currency": "USD",
    "documentType": "invoice" or "receipt",
    "description": "brief description or null",
    "lineItems": [
        {"description": "string", "quantity": number, "unitPrice": number, "amount": number}
    ],
    "paymentTerms": "string or null",
    "category": "suggested category or null",
    "confidence": 0.0 to 1.0
}

Return ONLY valid JSON, no markdown or explanation.
```

### 2. Payment Type Detection Prompt (Optional Enhancement)

**Purpose:** Detect payment method from invoice text

```
Analyze this invoice text and determine the most likely payment type.

INVOICE TEXT:
{invoice_text}

PAYMENT TYPES TO DETECT:
- Wire: Bank wire transfer, SWIFT, routing number, account number
- ACH: ACH transfer, direct debit, US bank details
- Card: Credit card, Visa, Mastercard, Amex
- PayPal: PayPal email, PayPal link
- Venmo: Venmo username, Venmo link
- Crypto: Bitcoin, Ethereum, wallet address, crypto payment
- Check: Mail check, check payment

Return JSON:
{
    "paymentType": "Wire" | "ACH" | "Card" | "PayPal" | "Venmo" | "Crypto" | "Check" | null,
    "confidence": 0.0 to 1.0,
    "evidence": "text that indicates this payment type"
}

Return ONLY valid JSON.
```

### 3. Invoice Category Classification Prompt (Optional Enhancement)

**Purpose:** Classify invoice into spending category

```
Classify this invoice into a spending category.

VENDOR: {vendor_name}
DESCRIPTION: {description}
LINE ITEMS: {line_items}

CATEGORIES:
- Cloud Services (AWS, Azure, GCP, hosting)
- Software & SaaS (subscriptions, licenses)
- Marketing & Advertising (ads, campaigns)
- Professional Services (consulting, legal, accounting)
- Office & Supplies (furniture, equipment)
- Travel & Entertainment (flights, hotels, meals)
- Telecommunications (phone, internet)
- Utilities (electricity, water, gas)
- Insurance (business insurance)
- Shipping & Logistics (FedEx, UPS, freight)
- Manufacturing & Production
- Research & Development
- Human Resources (recruiting, training)
- IT Infrastructure (hardware, networking)
- Other

Return JSON:
{
    "category": "selected category",
    "confidence": 0.0 to 1.0
}

Return ONLY valid JSON.
```

---

## Service Account Permissions

Your service account needs these IAM roles:

| Role | Service | Purpose |
|------|---------|---------|
| `roles/documentai.apiUser` | Document AI | Process documents |
| `roles/storage.objectAdmin` | Cloud Storage | Upload/download PDFs |
| `roles/bigquery.dataEditor` | BigQuery | Read/write invoices table |
| `roles/bigquery.jobUser` | BigQuery | Run queries |
| `roles/discoveryengine.viewer` | Vertex AI Search | Query RAG data store |

---

## Quick Reference: Secret Usage by Service

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SECRETS MAPPING                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  GOOGLE_APPLICATION_CREDENTIALS_JSON                                 │
│  └── Used by: Document AI, GCS, BigQuery, Vertex AI Search         │
│                                                                      │
│  GOOGLE_GEMINI_API_KEY                                               │
│  └── Used by: Gemini AI (invoice extraction prompts)                │
│                                                                      │
│  GOOGLE_CLOUD_PROJECT                                                │
│  └── Used by: All services (project identifier)                     │
│                                                                      │
│  DOCUMENT_AI_PROCESSOR_ID                                            │
│  └── Used by: Document AI (invoice parser processor)                │
│                                                                      │
│  GCS_BUCKET                                                          │
│  └── Used by: Cloud Storage (PDF storage bucket)                    │
│                                                                      │
│  BIGQUERY_DATASET                                                    │
│  └── Used by: BigQuery (invoices table dataset)                     │
│                                                                      │
│  VERTEX_AI_SEARCH_DATA_STORE_ID                                      │
│  └── Used by: Vertex AI Search (RAG historical context)             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Integration Checklist

- [ ] Set `GOOGLE_APPLICATION_CREDENTIALS_JSON` secret
- [ ] Set `GOOGLE_GEMINI_API_KEY` secret
- [ ] Set `GOOGLE_CLOUD_PROJECT` environment variable
- [ ] Set `DOCUMENT_AI_PROCESSOR_ID` environment variable
- [ ] Set `GCS_BUCKET` environment variable
- [ ] Set `BIGQUERY_DATASET` environment variable (optional, defaults to `vendors_ai`)
- [ ] Set `VERTEX_AI_SEARCH_DATA_STORE_ID` environment variable (optional for RAG)
- [ ] Create BigQuery table using schema above
- [ ] Grant service account required IAM roles
- [ ] Test Document AI processor with sample PDF
- [ ] Test Gemini API key with sample prompt
- [ ] Test GCS bucket access (upload/download)
- [ ] Test BigQuery table access (insert/query)

---

## Troubleshooting

### Document AI Not Working
```bash
# Check processor exists
gcloud documentai processors list --location=us --project=$GOOGLE_CLOUD_PROJECT
```

### Gemini API Errors
```bash
# Test API key
curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=$GOOGLE_GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'
```

### GCS Permission Denied
```bash
# Check bucket access
gsutil ls gs://$GCS_BUCKET
```

### BigQuery Errors
```bash
# Check table exists
bq show $GOOGLE_CLOUD_PROJECT:$BIGQUERY_DATASET.invoices
```
