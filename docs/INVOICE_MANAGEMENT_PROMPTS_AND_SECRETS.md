# Invoice Management - AI Prompts & Secrets Configuration (TypeScript)

## Complete Reference for AI Prompts and Environment Secrets

This document provides all AI prompts used in the Invoice Management system and detailed TypeScript configuration for each Google Cloud service and secret.

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

### Environment Variables Template

```bash
# ============================================
# INVOICE MANAGEMENT SECRETS
# ============================================

# Google Cloud Project ID
GOOGLE_CLOUD_PROJECT=<SET_IN_REPLIT_SECRETS>

# Service Account Credentials (JSON string - same as main project)
# NOTE: This is already configured in Replit Secrets - DO NOT copy real values here
GOOGLE_APPLICATION_CREDENTIALS_JSON=<SET_IN_REPLIT_SECRETS>

# Gemini AI API Key
GOOGLE_GEMINI_API_KEY=<SET_IN_REPLIT_SECRETS>

# Document AI Processor
DOCUMENT_AI_PROCESSOR_ID=<SET_IN_REPLIT_SECRETS>
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
const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
const projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
const location = process.env.DOCUMENT_AI_LOCATION || 'us';
const processorId = process.env.DOCUMENT_AI_PROCESSOR_ID || '';

const client = credentials
  ? new DocumentProcessorServiceClient({ credentials })
  : new DocumentProcessorServiceClient();

// Build processor name
const processorName = `projects/${projectId}/locations/${location}/processors/${processorId}`;
```

### How Document AI Is Used

```typescript
interface DocumentAIResult {
  text: string;
  entities: Record<string, { value: string; confidence: number }[]>;
  pages: number;
}

async function extractWithDocumentAI(
  content: Buffer,
  mimeType: string
): Promise<DocumentAIResult> {
  const [result] = await client.processDocument({
    name: processorName,
    rawDocument: {
      content: content.toString('base64'),
      mimeType,
    },
  });

  const document = result.document;
  if (!document) {
    return { text: '', entities: {}, pages: 0 };
  }

  // Extract entities
  const entities: Record<string, { value: string; confidence: number }[]> = {};
  for (const entity of document.entities || []) {
    const type = entity.type || 'unknown';
    if (!entities[type]) {
      entities[type] = [];
    }
    entities[type].push({
      value: entity.mentionText || '',
      confidence: entity.confidence || 0,
    });
  }

  return {
    text: document.text || '',
    entities,
    pages: document.pages?.length || 0,
  };
}
```

---

## Google Gemini AI

### Secrets Used

| Secret | Usage |
|--------|-------|
| `GOOGLE_GEMINI_API_KEY` | API key for Gemini 1.5 Pro |

### TypeScript Configuration

```typescript
import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';

// Initialize with API key from secret
const apiKey = process.env.GOOGLE_GEMINI_API_KEY || '';
const genAI = new GoogleGenerativeAI(apiKey);
const model: GenerativeModel = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
```

### How Gemini Is Used

```typescript
interface ExtractedInvoiceData {
  vendorName: string;
  invoiceNumber: string | null;
  invoiceDate: string | null;
  dueDate: string | null;
  amount: number;
  subtotal: number | null;
  taxAmount: number | null;
  currency: string;
  documentType: 'invoice' | 'receipt';
  lineItems: Array<{ description: string; amount: number }>;
  confidence: number;
}

async function semanticExtraction(
  docText: string,
  ragContext: string
): Promise<ExtractedInvoiceData> {
  const prompt = `You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
${docText.substring(0, 8000)}

${ragContext}

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
    "lineItems": [{"description": "string", "amount": number}],
    "confidence": 0.0 to 1.0
}

Return ONLY valid JSON, no markdown.`;

  const result = await model.generateContent(prompt);
  const response = await result.response;
  let text = response.text();

  // Parse JSON from response
  if (text.includes('```json')) {
    text = text.split('```json')[1].split('```')[0];
  }

  return JSON.parse(text.trim());
}
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
import { Storage, Bucket } from '@google-cloud/storage';

// Initialize with credentials from secret
const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
const bucketName = process.env.GCS_BUCKET || 'payouts-invoices';

const storage = credentials
  ? new Storage({ credentials })
  : new Storage();

const bucket: Bucket = storage.bucket(bucketName);
```

### How GCS Is Used

```typescript
import { format } from 'date-fns';

async function uploadToGCS(
  content: Buffer,
  filename: string,
  userEmail: string
): Promise<string> {
  const datePath = format(new Date(), 'yyyy/MM/dd');
  const safeEmail = userEmail.replace('@', '_at_').replace(/\./g, '_');
  const gcsPath = `invoices/${safeEmail}/${datePath}/${filename}`;

  const file = bucket.file(gcsPath);
  await file.save(content, {
    contentType: 'application/pdf',
    metadata: {
      uploadedBy: userEmail,
      uploadedAt: new Date().toISOString(),
    },
  });

  return gcsPath;
}

async function getSignedUrl(gcsPath: string): Promise<string> {
  const file = bucket.file(gcsPath);
  const [url] = await file.getSignedUrl({
    version: 'v4',
    action: 'read',
    expires: Date.now() + 60 * 60 * 1000, // 1 hour
  });
  return url;
}
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
const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
const projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
const datasetId = process.env.BIGQUERY_DATASET || 'vendors_ai';

const bigquery = credentials
  ? new BigQuery({ credentials, projectId })
  : new BigQuery({ projectId });

const tableId = `${projectId}.${datasetId}.invoices`;
```

### How BigQuery Is Used

```typescript
interface InvoiceRow {
  invoice_id: string;
  invoice_number: string | null;
  vendor_name: string;
  amount: number;
  currency: string;
  status: string;
  user_email: string;
  created_at: string;
}

async function storeInvoice(invoice: InvoiceRow): Promise<void> {
  await bigquery.dataset(datasetId).table('invoices').insert([invoice]);
}

async function listInvoices(
  userEmail: string,
  page: number = 1,
  limit: number = 50
): Promise<InvoiceRow[]> {
  const offset = (page - 1) * limit;
  const query = `
    SELECT * FROM \`${tableId}\`
    WHERE user_email = @userEmail
    ORDER BY created_at DESC
    LIMIT ${limit} OFFSET ${offset}
  `;

  const [rows] = await bigquery.query({
    query,
    params: { userEmail },
  });

  return rows as InvoiceRow[];
}

async function approveInvoice(
  invoiceId: string,
  userEmail: string
): Promise<void> {
  const query = `
    UPDATE \`${tableId}\`
    SET status = 'approved',
        approved_by = '${userEmail}',
        approved_at = CURRENT_TIMESTAMP(),
        updated_at = CURRENT_TIMESTAMP()
    WHERE invoice_id = '${invoiceId}'
  `;

  await bigquery.query({ query });
}
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
const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
const projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
const dataStoreId = process.env.VERTEX_AI_SEARCH_DATA_STORE_ID || '';

const client = credentials
  ? new SearchServiceClient({ credentials })
  : new SearchServiceClient();

const servingConfig = `projects/${projectId}/locations/global/collections/default_collection/dataStores/${dataStoreId}/servingConfigs/default_search`;
```

### How RAG Is Used

```typescript
interface RAGContext {
  typicalCategory?: string;
  typicalPaymentType?: string;
  vendorHistory?: Array<{ amount: number; category: string }>;
}

async function getRAGContext(vendorHint: string): Promise<RAGContext> {
  if (!vendorHint || !dataStoreId) return {};

  try {
    const [response] = await client.search({
      servingConfig,
      query: vendorHint,
      pageSize: 5,
    });

    if (response.results && response.results.length > 0) {
      const firstResult = response.results[0].document as any;
      return {
        typicalCategory: firstResult?.category,
        typicalPaymentType: firstResult?.paymentType,
      };
    }
  } catch (error) {
    console.warn('RAG context lookup failed:', error);
  }

  return {};
}
```

---

## Complete Prompts Reference

### 1. Main Invoice Extraction Prompt (Gemini 1.5 Pro)

**Used In:** `InvoiceParserService.semanticExtraction()`

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

### 2. Payment Type Detection Prompt

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

### 3. Invoice Category Classification Prompt

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

## TypeScript Integration Checklist

- [ ] Set `GOOGLE_APPLICATION_CREDENTIALS_JSON` secret
- [ ] Set `GOOGLE_GEMINI_API_KEY` secret
- [ ] Set `GOOGLE_CLOUD_PROJECT` environment variable
- [ ] Set `DOCUMENT_AI_PROCESSOR_ID` environment variable
- [ ] Set `GCS_BUCKET` environment variable
- [ ] Set `BIGQUERY_DATASET` environment variable
- [ ] Set `VERTEX_AI_SEARCH_DATA_STORE_ID` environment variable (optional)
- [ ] Install npm packages:
  ```bash
  npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
  npm install @google/generative-ai @google-cloud/discoveryengine
  ```
- [ ] Create BigQuery table using schema
- [ ] Grant service account required IAM roles
- [ ] Test all services

---

## Complete Implementation Files

| File | Description |
|------|-------------|
| `invoice_parser_service_complete.ts` | Full TypeScript parser service |
| `invoice_management_api.ts` | Complete Express API routes |
| `INVOICE_MANAGEMENT_TYPESCRIPT_GUIDE.md` | Detailed TypeScript guide |
| `INVOICE_MANAGEMENT_INTEGRATION_GUIDE.md` | Integration documentation |

All files are TypeScript-only with full type definitions.
