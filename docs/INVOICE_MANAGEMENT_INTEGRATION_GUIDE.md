# Invoice Management Integration Guide - TypeScript

## Complete TypeScript Documentation for AP Automation Invoice Management

This guide provides everything needed to build a production-ready Invoice Management system with AI-powered PDF parsing, bulk upload support, and comprehensive invoice lifecycle management using TypeScript/Express.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Project Setup](#project-setup)
3. [Type Definitions](#type-definitions)
4. [Database Schema](#database-schema)
5. [Backend API Endpoints](#backend-api-endpoints)
6. [AI Invoice Parsing Service](#ai-invoice-parsing-service)
7. [Frontend Components](#frontend-components)
8. [Environment Configuration](#environment-configuration)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Frontend (React + TypeScript)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Upload PDF  │  │ Invoice List│  │Invoice Detail│ │  Filters    │ │
│  │ (Bulk/Single)│  │   Table     │  │   Panel     │ │  & Search   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────┼────────────────┼────────────────┼────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Express + TypeScript API                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │POST /upload │  │GET /invoices│  │PUT /invoice │  │POST /approve│ │
│  │   /bulk     │  │             │  │   /:id      │  │   /reject   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
└─────────┼────────────────┼────────────────┼────────────────┼────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Service Layer (TypeScript)                      │
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

## Project Setup

### Dependencies

```bash
# Core dependencies
npm install express cors helmet multer uuid date-fns
npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
npm install @google/generative-ai

# TypeScript dependencies
npm install -D typescript @types/node @types/express @types/multer @types/cors @types/uuid
npm install -D ts-node nodemon
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

### Project Structure

```
src/
├── types/
│   └── invoice.types.ts        # All TypeScript interfaces
├── services/
│   └── invoice-parser.service.ts  # 4-layer AI parsing
├── routes/
│   └── invoice.routes.ts       # Express API routes
├── middleware/
│   └── auth.middleware.ts      # Authentication
├── utils/
│   └── helpers.ts              # Utility functions
└── index.ts                    # Express app entry
```

---

## Type Definitions

### src/types/invoice.types.ts

```typescript
// ============================================
// CORE INVOICE TYPES
// ============================================

export interface Invoice {
  invoiceId: string;
  invoiceNumber: string | null;
  vendorName: string;
  vendorId: string | null;
  
  // Financial
  amount: number;
  currency: Currency;
  taxAmount: number | null;
  subtotal: number | null;
  
  // Dates
  invoiceDate: string | null;
  dueDate: string | null;
  scheduledDate: string | null;
  
  // Payment
  paymentType: PaymentType | null;
  paymentStatus: PaymentStatus;
  
  // Categorization
  category: string | null;
  glCode: string | null;
  description: string | null;
  lineItems: LineItem[];
  
  // Workflow
  status: InvoiceStatus;
  approvalStatus: ApprovalStatus | null;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectedBy: string | null;
  rejectedAt: string | null;
  rejectionReason: string | null;
  
  // Source
  source: InvoiceSource;
  originalFilename: string | null;
  gcsPath: string | null;
  
  // AI Metadata
  extractionConfidence: number;
  extractionMethod: string;
  rawExtraction: Record<string, unknown> | null;
  
  // Tenant
  userEmail: string;
  tenantId: string | null;
  
  // Timestamps
  createdAt: string;
  updatedAt: string;
}

export interface LineItem {
  description: string;
  quantity?: number;
  unitPrice?: number;
  amount: number;
}

// ============================================
// ENUMS
// ============================================

export type Currency = 'USD' | 'EUR' | 'GBP' | 'CAD' | 'AUD' | 'JPY' | 'CNY' | 'INR' | 'BRL' | 'MXN';
export type PaymentType = 'Wire' | 'ACH' | 'Card' | 'PayPal' | 'Venmo' | 'Crypto' | 'Check';
export type PaymentStatus = 'pending' | 'processing' | 'paid' | 'failed' | 'cancelled';
export type InvoiceStatus = 'pending' | 'approved' | 'rejected' | 'paid' | 'cancelled';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected';
export type InvoiceSource = 'upload' | 'gmail' | 'netsuite' | 'manual' | 'api';

// ============================================
// API REQUEST/RESPONSE TYPES
// ============================================

export interface UploadInvoiceResponse {
  status: 'success' | 'error';
  invoiceId: string;
  extractedData?: ExtractedInvoiceData;
  gcsPath?: string;
  confidence?: number;
  error?: string;
}

export interface BulkUploadResponse {
  status: 'success' | 'error';
  total: number;
  processed: number;
  failed: number;
  results: BulkUploadResult[];
}

export interface BulkUploadResult {
  filename: string;
  status: 'success' | 'error';
  invoiceId?: string;
  vendorName?: string;
  amount?: number;
  error?: string;
}

export interface ListInvoicesResponse {
  invoices: Invoice[];
  pagination: Pagination;
  summary: InvoiceSummary;
}

export interface Pagination {
  page: number;
  limit: number;
  total: number;
  pages: number;
}

export interface InvoiceSummary {
  totalPending: number;
  totalDue: number;
  overdue: number;
  awaitingApproval: number;
  paidThisMonth: number;
  scheduled: number;
}

export interface ListInvoicesParams {
  page?: number;
  limit?: number;
  status?: InvoiceStatus;
  paymentType?: PaymentType;
  currency?: Currency;
  dateFrom?: string;
  dateTo?: string;
  search?: string;
  sortBy?: 'createdAt' | 'invoiceDate' | 'amount' | 'vendorName' | 'status';
  sortOrder?: 'asc' | 'desc';
}

// ============================================
// AI EXTRACTION TYPES
// ============================================

export interface ExtractedInvoiceData {
  vendorName: string;
  invoiceNumber: string | null;
  invoiceDate: string | null;
  dueDate: string | null;
  amount: number;
  subtotal: number | null;
  taxAmount: number | null;
  currency: Currency;
  documentType: 'invoice' | 'receipt';
  description: string | null;
  lineItems: LineItem[];
  paymentTerms: string | null;
  category: string | null;
  confidence: number;
  validationWarning?: string;
}
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
    payment_status STRING DEFAULT 'pending',
    
    -- Categorization
    category STRING,
    gl_code STRING,
    description STRING,
    line_items STRING,  -- JSON array
    
    -- Workflow Status
    status STRING DEFAULT 'pending',
    approval_status STRING,
    approved_by STRING,
    approved_at TIMESTAMP,
    rejected_by STRING,
    rejected_at TIMESTAMP,
    rejection_reason STRING,
    
    -- Source Tracking
    source STRING,
    original_filename STRING,
    gcs_path STRING,
    
    -- AI Extraction Metadata
    extraction_confidence FLOAT64,
    extraction_method STRING,
    raw_extraction STRING,
    
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

### API Routes Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/invoices/upload` | Upload single invoice PDF |
| POST | `/api/invoices/upload/bulk` | Upload multiple PDFs |
| GET | `/api/invoices` | List invoices with filters |
| GET | `/api/invoices/summary` | Get summary statistics |
| GET | `/api/invoices/export` | Export to CSV |
| GET | `/api/invoices/:id` | Get invoice details |
| PUT | `/api/invoices/:id` | Update invoice |
| POST | `/api/invoices/:id/approve` | Approve invoice |
| POST | `/api/invoices/:id/reject` | Reject invoice |
| GET | `/api/invoices/:id/download` | Get PDF download URL |

### Express Router Implementation

```typescript
// src/routes/invoice.routes.ts

import { Router, Request, Response, NextFunction } from 'express';
import multer from 'multer';
import { InvoiceParserService } from '../services/invoice-parser.service';

const router = Router();
const upload = multer({ storage: multer.memoryStorage() });
const invoiceService = new InvoiceParserService();

// POST /api/invoices/upload
router.post('/upload', upload.single('file'), async (req: Request, res: Response) => {
  const file = req.file;
  if (!file) {
    return res.status(400).json({ status: 'error', message: 'No file provided' });
  }

  const userEmail = (req as any).user?.email || 'unknown@example.com';
  const result = await invoiceService.parseInvoice(
    file.buffer,
    file.originalname,
    file.mimetype,
    userEmail
  );

  res.json(result);
});

// POST /api/invoices/upload/bulk
router.post('/upload/bulk', upload.array('files[]', 50), async (req: Request, res: Response) => {
  const files = req.files as Express.Multer.File[];
  if (!files || files.length === 0) {
    return res.status(400).json({ status: 'error', message: 'No files provided' });
  }

  const userEmail = (req as any).user?.email || 'unknown@example.com';
  const validFiles = files
    .filter((f) => ['application/pdf', 'image/png', 'image/jpeg'].includes(f.mimetype))
    .map((f) => ({ buffer: f.buffer, filename: f.originalname, mimeType: f.mimetype }));

  const result = await invoiceService.parseInvoicesBulk(validFiles, userEmail);
  res.json(result);
});

// GET /api/invoices
router.get('/', async (req: Request, res: Response) => {
  const userEmail = (req as any).user?.email;
  const params = {
    page: parseInt(req.query.page as string) || 1,
    limit: parseInt(req.query.limit as string) || 50,
    status: req.query.status as any,
    search: req.query.search as string,
  };

  const result = await invoiceService.listInvoices(userEmail, params);
  res.json(result);
});

// POST /api/invoices/:id/approve
router.post('/:invoiceId/approve', async (req: Request, res: Response) => {
  const { invoiceId } = req.params;
  const userEmail = (req as any).user?.email;
  const { scheduledDate } = req.body || {};

  const result = await invoiceService.approveInvoice(invoiceId, userEmail, scheduledDate);
  res.json(result);
});

// POST /api/invoices/:id/reject
router.post('/:invoiceId/reject', async (req: Request, res: Response) => {
  const { invoiceId } = req.params;
  const { reason } = req.body;

  if (!reason) {
    return res.status(400).json({ status: 'error', message: 'Rejection reason required' });
  }

  const userEmail = (req as any).user?.email;
  const result = await invoiceService.rejectInvoice(invoiceId, userEmail, reason);
  res.json(result);
});

// GET /api/invoices/:id/download
router.get('/:invoiceId/download', async (req: Request, res: Response) => {
  const { invoiceId } = req.params;
  const url = await invoiceService.getDownloadUrl(invoiceId);

  if (!url) {
    return res.status(404).json({ status: 'error', message: 'PDF not found' });
  }

  res.json({ status: 'success', downloadUrl: url, expiresIn: 3600 });
});

export default router;
```

---

## AI Invoice Parsing Service

### 4-Layer Hybrid Extraction Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    4-LAYER HYBRID EXTRACTION                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Layer 1: Document AI (Google Cloud)                                │
│  └── OCR and layout extraction                                      │
│  └── Table detection                                                │
│  └── Entity recognition                                             │
│                                                                      │
│  Layer 2: Vertex AI Search RAG                                      │
│  └── Historical invoice context                                     │
│  └── Vendor pattern matching                                        │
│  └── Previous extraction corrections                                │
│                                                                      │
│  Layer 3: Gemini AI Semantic Reasoning                              │
│  └── Multi-language support (40+ languages)                        │
│  └── Complex date parsing                                           │
│  └── Amount disambiguation                                          │
│  └── Receipt vs Invoice classification                              │
│                                                                      │
│  Layer 4: Validation & Verification                                 │
│  └── Mathematical verification (subtotal + tax = total)            │
│  └── Cross-field validation                                         │
│  └── Confidence scoring                                             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Invoice Parser Service (TypeScript)

```typescript
// src/services/invoice-parser.service.ts

import { v4 as uuidv4 } from 'uuid';
import { format } from 'date-fns';
import { DocumentProcessorServiceClient } from '@google-cloud/documentai';
import { Storage } from '@google-cloud/storage';
import { BigQuery } from '@google-cloud/bigquery';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { ExtractedInvoiceData, UploadInvoiceResponse } from '../types/invoice.types';

export class InvoiceParserService {
  private projectId: string;
  private docAIClient: DocumentProcessorServiceClient | null = null;
  private storage: Storage | null = null;
  private bigquery: BigQuery | null = null;
  private geminiModel: any = null;

  constructor() {
    this.projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
    this.initClients();
  }

  private initClients(): void {
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
    let credentials: any;

    if (credentialsJson) {
      credentials = JSON.parse(credentialsJson);
    }

    // Document AI
    this.docAIClient = credentials
      ? new DocumentProcessorServiceClient({ credentials })
      : new DocumentProcessorServiceClient();

    // GCS
    this.storage = credentials
      ? new Storage({ credentials })
      : new Storage();

    // BigQuery
    this.bigquery = credentials
      ? new BigQuery({ credentials, projectId: this.projectId })
      : new BigQuery({ projectId: this.projectId });

    // Gemini
    const geminiApiKey = process.env.GOOGLE_GEMINI_API_KEY;
    if (geminiApiKey) {
      const genAI = new GoogleGenerativeAI(geminiApiKey);
      this.geminiModel = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
    }
  }

  async parseInvoice(
    fileBuffer: Buffer,
    filename: string,
    mimeType: string,
    userEmail: string
  ): Promise<UploadInvoiceResponse> {
    const invoiceId = this.generateInvoiceId();

    try {
      // Layer 1: Upload to GCS
      const gcsPath = await this.uploadToGCS(fileBuffer, filename, userEmail);

      // Layer 2: Document AI extraction
      const docAIResult = await this.extractWithDocumentAI(fileBuffer, mimeType);

      // Layer 3: Get RAG context
      const ragContext = await this.getRAGContext(docAIResult);

      // Layer 4: Gemini semantic extraction
      const extractedData = await this.semanticExtraction(docAIResult, ragContext);

      // Layer 5: Validation
      const validatedData = this.validateExtraction(extractedData);

      // Store in BigQuery
      await this.storeInvoice(invoiceId, validatedData, gcsPath, userEmail, filename);

      return {
        status: 'success',
        invoiceId,
        extractedData: validatedData,
        gcsPath,
        confidence: validatedData.confidence,
      };
    } catch (error) {
      return {
        status: 'error',
        invoiceId,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private generateInvoiceId(): string {
    const datePrefix = format(new Date(), 'yyyyMMdd');
    const uniquePart = uuidv4().substring(0, 8).toUpperCase();
    return `INV-${datePrefix}-${uniquePart}`;
  }

  // ... Additional methods from invoice_parser_service_complete.ts
}
```

---

## Frontend Components

### InvoiceUpload Component (React + TypeScript)

```tsx
// src/components/InvoiceUpload.tsx

import React, { useState, useCallback } from 'react';

interface UploadResult {
  status: 'success' | 'error';
  invoiceId?: string;
  extractedData?: {
    vendorName: string;
    amount: number;
    currency: string;
  };
  error?: string;
}

export const InvoiceUpload: React.FC = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await uploadFile(files[0]);
    }
  }, []);

  const uploadFile = async (file: File) => {
    setIsUploading(true);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/invoices/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({ status: 'error', error: 'Upload failed' });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div
      className={`dropzone ${isDragging ? 'dragging' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <p>Drag & drop your invoice PDF here</p>
      <input type="file" accept=".pdf,.png,.jpg" onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])} />
      
      {isUploading && <p>Processing with AI...</p>}
      
      {result?.status === 'success' && (
        <div className="success">
          <p>Invoice parsed: {result.extractedData?.vendorName}</p>
          <p>Amount: ${result.extractedData?.amount}</p>
        </div>
      )}
    </div>
  );
};
```

### InvoiceList Component (React + TypeScript)

```tsx
// src/components/InvoiceList.tsx

import React, { useState, useEffect } from 'react';

interface Invoice {
  invoiceId: string;
  vendorName: string;
  amount: number;
  currency: string;
  status: string;
  invoiceDate: string | null;
}

export const InvoiceList: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInvoices();
  }, []);

  const loadInvoices = async () => {
    const response = await fetch('/api/invoices');
    const data = await response.json();
    setInvoices(data.invoices || []);
    setLoading(false);
  };

  const handleApprove = async (invoiceId: string) => {
    await fetch(`/api/invoices/${invoiceId}/approve`, { method: 'POST' });
    loadInvoices();
  };

  const handleReject = async (invoiceId: string) => {
    const reason = prompt('Rejection reason:');
    if (reason) {
      await fetch(`/api/invoices/${invoiceId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      loadInvoices();
    }
  };

  if (loading) return <p>Loading...</p>;

  return (
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Vendor</th>
          <th>Amount</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {invoices.map((inv) => (
          <tr key={inv.invoiceId}>
            <td>{inv.invoiceDate}</td>
            <td>{inv.vendorName}</td>
            <td>{inv.currency} {inv.amount}</td>
            <td>{inv.status}</td>
            <td>
              {inv.status === 'pending' && (
                <>
                  <button onClick={() => handleApprove(inv.invoiceId)}>Approve</button>
                  <button onClick={() => handleReject(inv.invoiceId)}>Reject</button>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
```

---

## Environment Configuration

### Required Environment Variables

```bash
# Google Cloud Project
GOOGLE_CLOUD_PROJECT=your-project-id

# Service Account Credentials (JSON string)
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account",...}

# Gemini AI
GOOGLE_GEMINI_API_KEY=<SET_IN_REPLIT_SECRETS>

# Document AI
DOCUMENT_AI_PROCESSOR_ID=abc123def456
DOCUMENT_AI_LOCATION=us

# Cloud Storage
GCS_BUCKET=payouts-invoices

# BigQuery
BIGQUERY_DATASET=vendors_ai

# Vertex AI Search (optional)
VERTEX_AI_SEARCH_DATA_STORE_ID=your-datastore-id
```

---

## Quick Start

```bash
# 1. Clone the repository
git clone <your-repo>

# 2. Install dependencies
npm install

# 3. Configure environment variables
cp .env.example .env

# 4. Build TypeScript
npm run build

# 5. Start server
npm start

# Development mode
npm run dev
```

---

## Complete Implementation Files

For production-ready code, use these files:

| File | Description |
|------|-------------|
| `invoice_parser_service_complete.ts` | Full 4-layer AI parser service |
| `invoice_management_api.ts` | Complete Express API routes |
| `INVOICE_MANAGEMENT_PROMPTS_AND_SECRETS.md` | All AI prompts and secrets |
| `INVOICE_MANAGEMENT_TYPESCRIPT_GUIDE.md` | Detailed TypeScript guide |

All files are TypeScript-ready with full type definitions.
