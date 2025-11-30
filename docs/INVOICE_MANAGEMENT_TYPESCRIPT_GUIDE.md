# Invoice Management Integration Guide - TypeScript

## Complete TypeScript Implementation for AP Automation Invoice Management

This guide provides production-ready TypeScript code for building an Invoice Management system with AI-powered PDF parsing, bulk upload support, and comprehensive invoice lifecycle management.

---

## Table of Contents

1. [Project Setup](#project-setup)
2. [Type Definitions](#type-definitions)
3. [Invoice Parser Service](#invoice-parser-service)
4. [API Routes (Express)](#api-routes-express)
5. [Frontend Components (React/TypeScript)](#frontend-components)
6. [Database Schema](#database-schema)
7. [Environment Configuration](#environment-configuration)

---

## Project Setup

### Dependencies

```bash
# Core dependencies
npm install express multer cors helmet
npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
npm install @google/generative-ai
npm install uuid date-fns

# TypeScript dependencies
npm install -D typescript @types/node @types/express @types/multer @types/cors
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
    "declarationMap": true,
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
│   └── invoice.types.ts
├── services/
│   ├── invoice-parser.service.ts
│   ├── document-ai.service.ts
│   ├── gemini.service.ts
│   ├── storage.service.ts
│   └── bigquery.service.ts
├── routes/
│   └── invoice.routes.ts
├── middleware/
│   └── auth.middleware.ts
├── utils/
│   └── helpers.ts
└── index.ts
```

---

## Type Definitions

### src/types/invoice.types.ts

```typescript
// ============================================
// INVOICE TYPE DEFINITIONS
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

export interface ApproveInvoiceRequest {
  scheduledDate?: string;
  notes?: string;
}

export interface RejectInvoiceRequest {
  reason: string;
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

export interface DocumentAIResult {
  text: string;
  entities: Record<string, EntityValue[]>;
  tables: unknown[];
  pages: number;
}

export interface EntityValue {
  value: string;
  confidence: number;
}

export interface RAGContext {
  vendorHistory?: VendorHistoryItem[];
  typicalCategory?: string;
  typicalPaymentType?: PaymentType;
}

export interface VendorHistoryItem {
  vendorName: string;
  invoiceNumber: string;
  amount: number;
  currency: Currency;
  category: string;
  paymentType: PaymentType;
}
```

---

## Invoice Parser Service

### src/services/invoice-parser.service.ts

```typescript
import { v4 as uuidv4 } from 'uuid';
import { format } from 'date-fns';
import { DocumentAIService } from './document-ai.service';
import { GeminiService } from './gemini.service';
import { StorageService } from './storage.service';
import { BigQueryService } from './bigquery.service';
import {
  Invoice,
  ExtractedInvoiceData,
  UploadInvoiceResponse,
  BulkUploadResponse,
  BulkUploadResult,
  ListInvoicesResponse,
  ListInvoicesParams,
  InvoiceSummary,
  DocumentAIResult,
  RAGContext,
} from '../types/invoice.types';

export class InvoiceParserService {
  private documentAI: DocumentAIService;
  private gemini: GeminiService;
  private storage: StorageService;
  private bigquery: BigQueryService;

  constructor() {
    this.documentAI = new DocumentAIService();
    this.gemini = new GeminiService();
    this.storage = new StorageService();
    this.bigquery = new BigQueryService();
  }

  /**
   * Parse a single invoice using 4-layer hybrid approach
   */
  async parseInvoice(
    fileBuffer: Buffer,
    filename: string,
    mimeType: string,
    userEmail: string
  ): Promise<UploadInvoiceResponse> {
    const invoiceId = this.generateInvoiceId();

    try {
      // Layer 1: Upload to GCS
      const gcsPath = await this.storage.uploadInvoice(
        fileBuffer,
        filename,
        userEmail
      );

      // Layer 2: Document AI extraction
      const docAIResult = await this.documentAI.extractDocument(
        fileBuffer,
        mimeType
      );

      // Layer 3: Get RAG context from historical invoices
      const ragContext = await this.getRAGContext(docAIResult);

      // Layer 4: Gemini semantic reasoning
      const extractedData = await this.gemini.extractInvoiceData(
        docAIResult,
        ragContext
      );

      // Layer 5: Validation
      const validatedData = this.validateExtraction(extractedData, docAIResult);

      // Store in BigQuery
      await this.bigquery.storeInvoice({
        invoiceId,
        ...validatedData,
        gcsPath,
        userEmail,
        originalFilename: filename,
        source: 'upload',
        status: 'pending',
        paymentStatus: 'pending',
        extractionMethod: '4-layer-hybrid',
      });

      return {
        status: 'success',
        invoiceId,
        extractedData: validatedData,
        gcsPath,
        confidence: validatedData.confidence,
      };
    } catch (error) {
      console.error('Invoice parsing failed:', error);
      return {
        status: 'error',
        invoiceId,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Parse multiple invoices in bulk
   */
  async parseInvoicesBulk(
    files: Array<{ buffer: Buffer; filename: string; mimeType: string }>,
    userEmail: string
  ): Promise<BulkUploadResponse> {
    const results: BulkUploadResult[] = [];

    for (const file of files) {
      const result = await this.parseInvoice(
        file.buffer,
        file.filename,
        file.mimeType,
        userEmail
      );

      results.push({
        filename: file.filename,
        status: result.status,
        invoiceId: result.invoiceId,
        vendorName: result.extractedData?.vendorName,
        amount: result.extractedData?.amount,
        error: result.error,
      });
    }

    const successful = results.filter((r) => r.status === 'success').length;

    return {
      status: 'success',
      total: files.length,
      processed: successful,
      failed: files.length - successful,
      results,
    };
  }

  /**
   * Get historical context for RAG
   */
  private async getRAGContext(
    docAIResult: DocumentAIResult
  ): Promise<RAGContext> {
    const vendorHint = this.extractVendorHint(docAIResult);
    if (!vendorHint) return {};

    try {
      const history = await this.bigquery.getVendorHistory(vendorHint);
      if (history.length > 0) {
        return {
          vendorHistory: history,
          typicalCategory: history[0].category,
          typicalPaymentType: history[0].paymentType,
        };
      }
    } catch (error) {
      console.warn('RAG context lookup failed:', error);
    }

    return {};
  }

  /**
   * Extract vendor hint from Document AI result
   */
  private extractVendorHint(docAIResult: DocumentAIResult): string | null {
    const suppliers = docAIResult.entities?.['supplier_name'] || [];
    return suppliers.length > 0 ? suppliers[0].value : null;
  }

  /**
   * Validate extracted data
   */
  private validateExtraction(
    data: ExtractedInvoiceData,
    docAIResult: DocumentAIResult
  ): ExtractedInvoiceData {
    const validated = { ...data };

    // Mathematical verification
    if (data.subtotal && data.taxAmount && data.amount) {
      const calculatedTotal = data.subtotal + data.taxAmount;
      if (Math.abs(calculatedTotal - data.amount) > 0.01) {
        validated.validationWarning = `Total mismatch: ${data.subtotal} + ${data.taxAmount} != ${data.amount}`;
        validated.confidence = Math.min(validated.confidence, 0.7);
      }
    }

    // Date validation
    if (data.invoiceDate && data.dueDate) {
      const invDate = new Date(data.invoiceDate);
      const dueDate = new Date(data.dueDate);
      if (dueDate < invDate) {
        validated.validationWarning = 'Due date is before invoice date';
        validated.confidence = Math.min(validated.confidence, 0.7);
      }
    }

    // Ensure required fields
    if (!validated.vendorName) {
      validated.vendorName = 'Unknown Vendor';
      validated.confidence = Math.min(validated.confidence, 0.5);
    }

    if (!validated.amount || validated.amount === 0) {
      validated.amount = 0;
      validated.confidence = Math.min(validated.confidence, 0.5);
    }

    return validated;
  }

  /**
   * Generate unique invoice ID
   */
  private generateInvoiceId(): string {
    const datePrefix = format(new Date(), 'yyyyMMdd');
    const uniquePart = uuidv4().substring(0, 8).toUpperCase();
    return `INV-${datePrefix}-${uniquePart}`;
  }

  /**
   * List invoices with filters
   */
  async listInvoices(
    userEmail: string,
    params: ListInvoicesParams
  ): Promise<ListInvoicesResponse> {
    return this.bigquery.listInvoices(userEmail, params);
  }

  /**
   * Get single invoice
   */
  async getInvoice(invoiceId: string): Promise<Invoice | null> {
    return this.bigquery.getInvoice(invoiceId);
  }

  /**
   * Approve invoice
   */
  async approveInvoice(
    invoiceId: string,
    userEmail: string,
    scheduledDate?: string,
    notes?: string
  ): Promise<{ status: string; message: string }> {
    return this.bigquery.approveInvoice(
      invoiceId,
      userEmail,
      scheduledDate,
      notes
    );
  }

  /**
   * Reject invoice
   */
  async rejectInvoice(
    invoiceId: string,
    userEmail: string,
    reason: string
  ): Promise<{ status: string; message: string }> {
    return this.bigquery.rejectInvoice(invoiceId, userEmail, reason);
  }

  /**
   * Get download URL for invoice PDF
   */
  async getDownloadUrl(invoiceId: string): Promise<string | null> {
    const invoice = await this.bigquery.getInvoice(invoiceId);
    if (!invoice?.gcsPath) return null;

    return this.storage.getSignedUrl(invoice.gcsPath);
  }

  /**
   * Get invoice summary stats
   */
  async getSummary(userEmail: string): Promise<InvoiceSummary> {
    return this.bigquery.getSummaryStats(userEmail);
  }
}
```

---

### src/services/document-ai.service.ts

```typescript
import { DocumentProcessorServiceClient } from '@google-cloud/documentai';
import { DocumentAIResult, EntityValue } from '../types/invoice.types';

export class DocumentAIService {
  private client: DocumentProcessorServiceClient;
  private projectId: string;
  private location: string;
  private processorId: string;

  constructor() {
    this.projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
    this.location = process.env.DOCUMENT_AI_LOCATION || 'us';
    this.processorId = process.env.DOCUMENT_AI_PROCESSOR_ID || '';

    // Initialize with credentials from environment
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
    if (credentialsJson) {
      const credentials = JSON.parse(credentialsJson);
      this.client = new DocumentProcessorServiceClient({ credentials });
    } else {
      this.client = new DocumentProcessorServiceClient();
    }
  }

  /**
   * Extract document using Google Document AI
   */
  async extractDocument(
    content: Buffer,
    mimeType: string
  ): Promise<DocumentAIResult> {
    if (!this.processorId) {
      console.warn('Document AI processor not configured, returning empty result');
      return { text: '', entities: {}, tables: [], pages: 0 };
    }

    try {
      const processorName = `projects/${this.projectId}/locations/${this.location}/processors/${this.processorId}`;

      const [result] = await this.client.processDocument({
        name: processorName,
        rawDocument: {
          content: content.toString('base64'),
          mimeType,
        },
      });

      const document = result.document;
      if (!document) {
        return { text: '', entities: {}, tables: [], pages: 0 };
      }

      // Extract entities
      const entities: Record<string, EntityValue[]> = {};
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
        tables: [],
        pages: document.pages?.length || 0,
      };
    } catch (error) {
      console.error('Document AI extraction failed:', error);
      return { text: '', entities: {}, tables: [], pages: 0 };
    }
  }
}
```

---

### src/services/gemini.service.ts

```typescript
import { GoogleGenerativeAI } from '@google/generative-ai';
import {
  ExtractedInvoiceData,
  DocumentAIResult,
  RAGContext,
  LineItem,
  Currency,
} from '../types/invoice.types';

export class GeminiService {
  private model: any;
  private isInitialized: boolean = false;

  constructor() {
    const apiKey = process.env.GOOGLE_GEMINI_API_KEY;
    if (apiKey) {
      const genAI = new GoogleGenerativeAI(apiKey);
      this.model = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
      this.isInitialized = true;
    }
  }

  /**
   * Extract invoice data using Gemini AI
   */
  async extractInvoiceData(
    docAIResult: DocumentAIResult,
    ragContext: RAGContext
  ): Promise<ExtractedInvoiceData> {
    if (!this.isInitialized) {
      return this.fallbackExtraction(docAIResult);
    }

    const docText = docAIResult.text.substring(0, 8000);
    const ragInfo = ragContext.typicalCategory
      ? `Historical: Category=${ragContext.typicalCategory}, Payment=${ragContext.typicalPaymentType}`
      : '';

    const prompt = `You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
${docText}

${ragInfo}

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

Return ONLY valid JSON, no markdown or explanation.`;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      let text = response.text();

      // Parse JSON from response
      if (text.includes('```json')) {
        text = text.split('```json')[1].split('```')[0];
      } else if (text.includes('```')) {
        text = text.split('```')[1].split('```')[0];
      }

      const parsed = JSON.parse(text.trim());
      return this.normalizeExtractedData(parsed);
    } catch (error) {
      console.error('Gemini extraction failed:', error);
      return this.fallbackExtraction(docAIResult);
    }
  }

  /**
   * Normalize extracted data to ensure type safety
   */
  private normalizeExtractedData(data: any): ExtractedInvoiceData {
    return {
      vendorName: data.vendorName || 'Unknown Vendor',
      invoiceNumber: data.invoiceNumber || null,
      invoiceDate: data.invoiceDate || null,
      dueDate: data.dueDate || null,
      amount: typeof data.amount === 'number' ? data.amount : 0,
      subtotal: typeof data.subtotal === 'number' ? data.subtotal : null,
      taxAmount: typeof data.taxAmount === 'number' ? data.taxAmount : null,
      currency: this.normalizeCurrency(data.currency),
      documentType: data.documentType === 'receipt' ? 'receipt' : 'invoice',
      description: data.description || null,
      lineItems: this.normalizeLineItems(data.lineItems),
      paymentTerms: data.paymentTerms || null,
      category: data.category || null,
      confidence: typeof data.confidence === 'number' ? data.confidence : 0.5,
    };
  }

  /**
   * Normalize currency code
   */
  private normalizeCurrency(currency: any): Currency {
    const valid: Currency[] = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'INR', 'BRL', 'MXN'];
    if (typeof currency === 'string' && valid.includes(currency as Currency)) {
      return currency as Currency;
    }
    return 'USD';
  }

  /**
   * Normalize line items
   */
  private normalizeLineItems(items: any): LineItem[] {
    if (!Array.isArray(items)) return [];
    return items.map((item: any) => ({
      description: item.description || '',
      quantity: typeof item.quantity === 'number' ? item.quantity : undefined,
      unitPrice: typeof item.unitPrice === 'number' ? item.unitPrice : undefined,
      amount: typeof item.amount === 'number' ? item.amount : 0,
    }));
  }

  /**
   * Fallback extraction when Gemini is unavailable
   */
  private fallbackExtraction(docAIResult: DocumentAIResult): ExtractedInvoiceData {
    const entities = docAIResult.entities;
    return {
      vendorName: entities['supplier_name']?.[0]?.value || 'Unknown Vendor',
      invoiceNumber: entities['invoice_id']?.[0]?.value || null,
      invoiceDate: entities['invoice_date']?.[0]?.value || null,
      dueDate: entities['due_date']?.[0]?.value || null,
      amount: this.parseAmount(entities['total_amount']?.[0]?.value),
      subtotal: null,
      taxAmount: null,
      currency: 'USD',
      documentType: 'invoice',
      description: null,
      lineItems: [],
      paymentTerms: null,
      category: null,
      confidence: 0.5,
    };
  }

  /**
   * Parse amount string to number
   */
  private parseAmount(amountStr?: string): number {
    if (!amountStr) return 0;
    const cleaned = amountStr.replace(/[$€£¥,]/g, '').trim();
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }
}
```

---

### src/services/storage.service.ts

```typescript
import { Storage, Bucket } from '@google-cloud/storage';
import { format } from 'date-fns';

export class StorageService {
  private storage: Storage;
  private bucket: Bucket;
  private bucketName: string;

  constructor() {
    this.bucketName = process.env.GCS_BUCKET || 'payouts-invoices';

    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
    if (credentialsJson) {
      const credentials = JSON.parse(credentialsJson);
      this.storage = new Storage({ credentials });
    } else {
      this.storage = new Storage();
    }

    this.bucket = this.storage.bucket(this.bucketName);
  }

  /**
   * Upload invoice to GCS
   */
  async uploadInvoice(
    content: Buffer,
    filename: string,
    userEmail: string
  ): Promise<string> {
    const datePath = format(new Date(), 'yyyy/MM/dd');
    const safeEmail = userEmail.replace('@', '_at_').replace(/\./g, '_');
    const gcsPath = `invoices/${safeEmail}/${datePath}/${filename}`;

    const file = this.bucket.file(gcsPath);
    await file.save(content, {
      contentType: this.getMimeType(filename),
      metadata: {
        uploadedBy: userEmail,
        uploadedAt: new Date().toISOString(),
      },
    });

    return gcsPath;
  }

  /**
   * Get signed URL for download
   */
  async getSignedUrl(gcsPath: string): Promise<string> {
    const file = this.bucket.file(gcsPath);
    const [url] = await file.getSignedUrl({
      version: 'v4',
      action: 'read',
      expires: Date.now() + 60 * 60 * 1000, // 1 hour
    });
    return url;
  }

  /**
   * Delete file from GCS
   */
  async deleteFile(gcsPath: string): Promise<void> {
    const file = this.bucket.file(gcsPath);
    await file.delete();
  }

  /**
   * Get MIME type from filename
   */
  private getMimeType(filename: string): string {
    const ext = filename.toLowerCase().split('.').pop();
    const mimeTypes: Record<string, string> = {
      pdf: 'application/pdf',
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
    };
    return mimeTypes[ext || ''] || 'application/octet-stream';
  }
}
```

---

### src/services/bigquery.service.ts

```typescript
import { BigQuery } from '@google-cloud/bigquery';
import {
  Invoice,
  InvoiceStatus,
  ListInvoicesResponse,
  ListInvoicesParams,
  InvoiceSummary,
  VendorHistoryItem,
  PaymentType,
} from '../types/invoice.types';

export class BigQueryService {
  private client: BigQuery;
  private projectId: string;
  private datasetId: string;
  private tableId: string;

  constructor() {
    this.projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
    this.datasetId = process.env.BIGQUERY_DATASET || 'vendors_ai';
    this.tableId = `${this.projectId}.${this.datasetId}.invoices`;

    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
    if (credentialsJson) {
      const credentials = JSON.parse(credentialsJson);
      this.client = new BigQuery({ credentials, projectId: this.projectId });
    } else {
      this.client = new BigQuery({ projectId: this.projectId });
    }
  }

  /**
   * Store invoice in BigQuery
   */
  async storeInvoice(invoice: Partial<Invoice>): Promise<void> {
    const row = {
      invoice_id: invoice.invoiceId,
      invoice_number: invoice.invoiceNumber,
      vendor_name: invoice.vendorName,
      vendor_id: invoice.vendorId,
      amount: invoice.amount,
      currency: invoice.currency || 'USD',
      tax_amount: invoice.taxAmount,
      subtotal: invoice.subtotal,
      invoice_date: invoice.invoiceDate,
      due_date: invoice.dueDate,
      scheduled_date: invoice.scheduledDate,
      payment_type: invoice.paymentType,
      payment_status: invoice.paymentStatus || 'pending',
      category: invoice.category,
      gl_code: invoice.glCode,
      description: invoice.description,
      line_items: JSON.stringify(invoice.lineItems || []),
      status: invoice.status || 'pending',
      approval_status: invoice.approvalStatus,
      approved_by: invoice.approvedBy,
      approved_at: invoice.approvedAt,
      rejected_by: invoice.rejectedBy,
      rejected_at: invoice.rejectedAt,
      rejection_reason: invoice.rejectionReason,
      source: invoice.source || 'upload',
      original_filename: invoice.originalFilename,
      gcs_path: invoice.gcsPath,
      extraction_confidence: invoice.extractionConfidence,
      extraction_method: invoice.extractionMethod,
      raw_extraction: JSON.stringify(invoice.rawExtraction || {}),
      user_email: invoice.userEmail,
      tenant_id: invoice.tenantId,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    await this.client.dataset(this.datasetId).table('invoices').insert([row]);
  }

  /**
   * List invoices with filters and pagination
   */
  async listInvoices(
    userEmail: string,
    params: ListInvoicesParams
  ): Promise<ListInvoicesResponse> {
    const {
      page = 1,
      limit = 50,
      status,
      paymentType,
      currency,
      dateFrom,
      dateTo,
      search,
      sortBy = 'created_at',
      sortOrder = 'desc',
    } = params;

    const offset = (page - 1) * limit;
    const conditions: string[] = [`user_email = '${userEmail}'`];

    if (status) conditions.push(`status = '${status}'`);
    if (paymentType) conditions.push(`payment_type = '${paymentType}'`);
    if (currency) conditions.push(`currency = '${currency}'`);
    if (dateFrom) conditions.push(`invoice_date >= '${dateFrom}'`);
    if (dateTo) conditions.push(`invoice_date <= '${dateTo}'`);
    if (search) {
      conditions.push(
        `(LOWER(vendor_name) LIKE LOWER('%${search}%') OR LOWER(invoice_number) LIKE LOWER('%${search}%'))`
      );
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const sortColumn = this.mapSortColumn(sortBy);
    const order = sortOrder.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

    const query = `
      SELECT * FROM \`${this.tableId}\`
      ${whereClause}
      ORDER BY ${sortColumn} ${order}
      LIMIT ${limit} OFFSET ${offset}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM \`${this.tableId}\`
      ${whereClause}
    `;

    const [invoiceRows] = await this.client.query({ query });
    const [countRows] = await this.client.query({ query: countQuery });

    const invoices = invoiceRows.map(this.mapRowToInvoice);
    const total = countRows[0]?.total || 0;
    const summary = await this.getSummaryStats(userEmail);

    return {
      invoices,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
      summary,
    };
  }

  /**
   * Get single invoice by ID
   */
  async getInvoice(invoiceId: string): Promise<Invoice | null> {
    const query = `
      SELECT * FROM \`${this.tableId}\`
      WHERE invoice_id = @invoiceId
    `;

    const [rows] = await this.client.query({
      query,
      params: { invoiceId },
    });

    return rows.length > 0 ? this.mapRowToInvoice(rows[0]) : null;
  }

  /**
   * Approve invoice
   */
  async approveInvoice(
    invoiceId: string,
    userEmail: string,
    scheduledDate?: string,
    notes?: string
  ): Promise<{ status: string; message: string }> {
    const scheduledSql = scheduledDate
      ? `, scheduled_date = '${scheduledDate}'`
      : '';

    const query = `
      UPDATE \`${this.tableId}\`
      SET status = 'approved',
          approval_status = 'approved',
          approved_by = '${userEmail}',
          approved_at = CURRENT_TIMESTAMP(),
          updated_at = CURRENT_TIMESTAMP()
          ${scheduledSql}
      WHERE invoice_id = '${invoiceId}'
    `;

    await this.client.query({ query });
    return { status: 'success', message: 'Invoice approved' };
  }

  /**
   * Reject invoice
   */
  async rejectInvoice(
    invoiceId: string,
    userEmail: string,
    reason: string
  ): Promise<{ status: string; message: string }> {
    const query = `
      UPDATE \`${this.tableId}\`
      SET status = 'rejected',
          approval_status = 'rejected',
          rejected_by = '${userEmail}',
          rejected_at = CURRENT_TIMESTAMP(),
          rejection_reason = '${reason.replace(/'/g, "''")}',
          updated_at = CURRENT_TIMESTAMP()
      WHERE invoice_id = '${invoiceId}'
    `;

    await this.client.query({ query });
    return { status: 'success', message: 'Invoice rejected' };
  }

  /**
   * Get vendor history for RAG context
   */
  async getVendorHistory(vendorHint: string): Promise<VendorHistoryItem[]> {
    const query = `
      SELECT vendor_name, invoice_number, amount, currency, category, payment_type
      FROM \`${this.tableId}\`
      WHERE LOWER(vendor_name) LIKE LOWER('%${vendorHint.substring(0, 20)}%')
      ORDER BY created_at DESC
      LIMIT 5
    `;

    const [rows] = await this.client.query({ query });
    return rows.map((row: any) => ({
      vendorName: row.vendor_name,
      invoiceNumber: row.invoice_number,
      amount: row.amount,
      currency: row.currency,
      category: row.category,
      paymentType: row.payment_type,
    }));
  }

  /**
   * Get summary statistics
   */
  async getSummaryStats(userEmail: string): Promise<InvoiceSummary> {
    const query = `
      SELECT
        COUNT(CASE WHEN status = 'pending' THEN 1 END) as total_pending,
        COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) as total_due,
        COUNT(CASE WHEN status = 'pending' AND due_date < CURRENT_DATE() THEN 1 END) as overdue,
        COUNT(CASE WHEN status = 'pending' AND approval_status IS NULL THEN 1 END) as awaiting_approval,
        COALESCE(SUM(CASE WHEN status = 'paid' AND EXTRACT(MONTH FROM updated_at) = EXTRACT(MONTH FROM CURRENT_DATE()) THEN amount ELSE 0 END), 0) as paid_this_month,
        COUNT(CASE WHEN scheduled_date IS NOT NULL AND status = 'approved' THEN 1 END) as scheduled
      FROM \`${this.tableId}\`
      WHERE user_email = '${userEmail}'
    `;

    const [rows] = await this.client.query({ query });
    const row = rows[0] || {};

    return {
      totalPending: row.total_pending || 0,
      totalDue: row.total_due || 0,
      overdue: row.overdue || 0,
      awaitingApproval: row.awaiting_approval || 0,
      paidThisMonth: row.paid_this_month || 0,
      scheduled: row.scheduled || 0,
    };
  }

  /**
   * Map BigQuery row to Invoice type
   */
  private mapRowToInvoice(row: any): Invoice {
    return {
      invoiceId: row.invoice_id,
      invoiceNumber: row.invoice_number,
      vendorName: row.vendor_name,
      vendorId: row.vendor_id,
      amount: row.amount,
      currency: row.currency || 'USD',
      taxAmount: row.tax_amount,
      subtotal: row.subtotal,
      invoiceDate: row.invoice_date,
      dueDate: row.due_date,
      scheduledDate: row.scheduled_date,
      paymentType: row.payment_type,
      paymentStatus: row.payment_status || 'pending',
      category: row.category,
      glCode: row.gl_code,
      description: row.description,
      lineItems: this.parseJson(row.line_items, []),
      status: row.status || 'pending',
      approvalStatus: row.approval_status,
      approvedBy: row.approved_by,
      approvedAt: row.approved_at,
      rejectedBy: row.rejected_by,
      rejectedAt: row.rejected_at,
      rejectionReason: row.rejection_reason,
      source: row.source || 'upload',
      originalFilename: row.original_filename,
      gcsPath: row.gcs_path,
      extractionConfidence: row.extraction_confidence || 0,
      extractionMethod: row.extraction_method || 'unknown',
      rawExtraction: this.parseJson(row.raw_extraction, null),
      userEmail: row.user_email,
      tenantId: row.tenant_id,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  }

  /**
   * Map sort column name
   */
  private mapSortColumn(sortBy: string): string {
    const map: Record<string, string> = {
      createdAt: 'created_at',
      invoiceDate: 'invoice_date',
      amount: 'amount',
      vendorName: 'vendor_name',
      status: 'status',
    };
    return map[sortBy] || 'created_at';
  }

  /**
   * Safe JSON parse
   */
  private parseJson<T>(value: any, defaultValue: T): T {
    if (!value) return defaultValue;
    try {
      return typeof value === 'string' ? JSON.parse(value) : value;
    } catch {
      return defaultValue;
    }
  }
}
```

---

## API Routes (Express)

### src/routes/invoice.routes.ts

```typescript
import { Router, Request, Response, NextFunction } from 'express';
import multer from 'multer';
import { InvoiceParserService } from '../services/invoice-parser.service';
import {
  ListInvoicesParams,
  ApproveInvoiceRequest,
  RejectInvoiceRequest,
} from '../types/invoice.types';

const router = Router();
const upload = multer({ storage: multer.memoryStorage() });
const invoiceService = new InvoiceParserService();

// Middleware to get user email from session/auth
const getUserEmail = (req: Request): string => {
  return (req as any).user?.email || 'unknown@example.com';
};

/**
 * POST /api/invoices/upload
 * Upload and parse a single invoice
 */
router.post(
  '/upload',
  upload.single('file'),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const file = req.file;
      if (!file) {
        return res.status(400).json({ status: 'error', message: 'No file provided' });
      }

      const allowedTypes = [
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/jpg',
      ];
      if (!allowedTypes.includes(file.mimetype)) {
        return res.status(400).json({ status: 'error', message: 'Invalid file type' });
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.parseInvoice(
        file.buffer,
        file.originalname,
        file.mimetype,
        userEmail
      );

      res.json(result);
    } catch (error) {
      next(error);
    }
  }
);

/**
 * POST /api/invoices/upload/bulk
 * Upload and parse multiple invoices
 */
router.post(
  '/upload/bulk',
  upload.array('files[]', 50),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const files = req.files as Express.Multer.File[];
      if (!files || files.length === 0) {
        return res.status(400).json({ status: 'error', message: 'No files provided' });
      }

      const allowedTypes = [
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/jpg',
      ];
      const validFiles = files
        .filter((f) => allowedTypes.includes(f.mimetype))
        .map((f) => ({
          buffer: f.buffer,
          filename: f.originalname,
          mimeType: f.mimetype,
        }));

      if (validFiles.length === 0) {
        return res.status(400).json({ status: 'error', message: 'No valid files' });
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.parseInvoicesBulk(validFiles, userEmail);

      res.json(result);
    } catch (error) {
      next(error);
    }
  }
);

/**
 * GET /api/invoices
 * List invoices with filters and pagination
 */
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userEmail = getUserEmail(req);
    const params: ListInvoicesParams = {
      page: parseInt(req.query.page as string) || 1,
      limit: parseInt(req.query.limit as string) || 50,
      status: req.query.status as any,
      paymentType: req.query.paymentType as any,
      currency: req.query.currency as any,
      dateFrom: req.query.dateFrom as string,
      dateTo: req.query.dateTo as string,
      search: req.query.search as string,
      sortBy: req.query.sortBy as any,
      sortOrder: req.query.sortOrder as any,
    };

    const result = await invoiceService.listInvoices(userEmail, params);
    res.json(result);
  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/invoices/summary
 * Get invoice summary statistics
 */
router.get('/summary', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userEmail = getUserEmail(req);
    const summary = await invoiceService.getSummary(userEmail);
    res.json({ status: 'success', summary });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/invoices/:invoiceId
 * Get single invoice details
 */
router.get('/:invoiceId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const invoice = await invoiceService.getInvoice(req.params.invoiceId);
    if (!invoice) {
      return res.status(404).json({ status: 'error', message: 'Invoice not found' });
    }
    res.json({ status: 'success', invoice });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /api/invoices/:invoiceId/approve
 * Approve an invoice
 */
router.post(
  '/:invoiceId/approve',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const userEmail = getUserEmail(req);
      const { scheduledDate, notes } = req.body as ApproveInvoiceRequest;

      const result = await invoiceService.approveInvoice(
        req.params.invoiceId,
        userEmail,
        scheduledDate,
        notes
      );

      res.json(result);
    } catch (error) {
      next(error);
    }
  }
);

/**
 * POST /api/invoices/:invoiceId/reject
 * Reject an invoice
 */
router.post(
  '/:invoiceId/reject',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { reason } = req.body as RejectInvoiceRequest;
      if (!reason) {
        return res.status(400).json({ status: 'error', message: 'Rejection reason required' });
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.rejectInvoice(
        req.params.invoiceId,
        userEmail,
        reason
      );

      res.json(result);
    } catch (error) {
      next(error);
    }
  }
);

/**
 * GET /api/invoices/:invoiceId/download
 * Get signed URL for PDF download
 */
router.get(
  '/:invoiceId/download',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const url = await invoiceService.getDownloadUrl(req.params.invoiceId);
      if (!url) {
        return res.status(404).json({ status: 'error', message: 'PDF not found' });
      }

      res.json({
        status: 'success',
        downloadUrl: url,
        expiresIn: 3600,
      });
    } catch (error) {
      next(error);
    }
  }
);

/**
 * GET /api/invoices/export
 * Export invoices to CSV
 */
router.get('/export/csv', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userEmail = getUserEmail(req);
    const params: ListInvoicesParams = {
      limit: 10000,
      status: req.query.status as any,
      dateFrom: req.query.dateFrom as string,
      dateTo: req.query.dateTo as string,
    };

    const { invoices } = await invoiceService.listInvoices(userEmail, params);

    const headers = [
      'Invoice ID',
      'Invoice Number',
      'Vendor',
      'Amount',
      'Currency',
      'Invoice Date',
      'Due Date',
      'Status',
      'Payment Type',
      'Category',
    ];

    const rows = invoices.map((inv) => [
      inv.invoiceId,
      inv.invoiceNumber || '',
      inv.vendorName,
      inv.amount,
      inv.currency,
      inv.invoiceDate || '',
      inv.dueDate || '',
      inv.status,
      inv.paymentType || '',
      inv.category || '',
    ]);

    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n');

    res.setHeader('Content-Type', 'text/csv');
    res.setHeader(
      'Content-Disposition',
      `attachment; filename=invoices_${new Date().toISOString().split('T')[0]}.csv`
    );
    res.send(csv);
  } catch (error) {
    next(error);
  }
});

export default router;
```

---

### src/index.ts (Express App Entry Point)

```typescript
import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import invoiceRoutes from './routes/invoice.routes';

const app: Express = express();
const PORT = process.env.PORT || 5000;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Routes
app.use('/api/invoices', invoiceRoutes);

// Health check
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Error handler
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Error:', err);
  res.status(500).json({
    status: 'error',
    message: err.message || 'Internal server error',
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Invoice Management API running on port ${PORT}`);
});

export default app;
```

---

## Frontend Components (React/TypeScript)

### src/components/InvoiceUpload.tsx

```tsx
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
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<UploadResult | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      uploadFile(files[0]);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      uploadFile(files[0]);
    }
  }, []);

  const uploadFile = async (file: File) => {
    const validTypes = ['application/pdf', 'image/png', 'image/jpeg'];
    if (!validTypes.includes(file.type)) {
      setResult({ status: 'error', error: 'Please upload a PDF or image file' });
      return;
    }

    setIsUploading(true);
    setProgress(0);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      setProgress(30);
      
      const response = await fetch('/api/invoices/upload', {
        method: 'POST',
        body: formData,
      });

      setProgress(70);

      const data = await response.json();
      setProgress(100);
      setResult(data);
    } catch (error) {
      setResult({
        status: 'error',
        error: error instanceof Error ? error.message : 'Upload failed',
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="invoice-upload">
      <div
        className={`dropzone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="dropzone-content">
          <span className="upload-icon">📄</span>
          <p>Drag & drop your invoice PDF here</p>
          <p className="or-text">or</p>
          <label className="browse-btn">
            Browse Files
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={handleFileSelect}
              hidden
            />
          </label>
        </div>
      </div>

      {isUploading && (
        <div className="progress-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p>{progress < 50 ? 'Uploading...' : 'Processing with AI...'}</p>
        </div>
      )}

      {result && (
        <div className={`result ${result.status}`}>
          {result.status === 'success' ? (
            <>
              <span className="success-icon">✓</span>
              <p>Invoice parsed successfully!</p>
              <p className="vendor">{result.extractedData?.vendorName}</p>
              <p className="amount">
                {new Intl.NumberFormat('en-US', {
                  style: 'currency',
                  currency: result.extractedData?.currency || 'USD',
                }).format(result.extractedData?.amount || 0)}
              </p>
            </>
          ) : (
            <>
              <span className="error-icon">✗</span>
              <p>{result.error}</p>
            </>
          )}
        </div>
      )}

      <style jsx>{`
        .invoice-upload {
          max-width: 500px;
          margin: 0 auto;
        }

        .dropzone {
          border: 2px dashed #d1d5db;
          border-radius: 12px;
          padding: 48px 24px;
          text-align: center;
          transition: all 0.2s;
          cursor: pointer;
        }

        .dropzone.dragging {
          border-color: #6366f1;
          background: #eef2ff;
        }

        .upload-icon {
          font-size: 48px;
          display: block;
          margin-bottom: 16px;
        }

        .or-text {
          color: #9ca3af;
          margin: 12px 0;
        }

        .browse-btn {
          display: inline-block;
          padding: 10px 20px;
          background: #f3f4f6;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
        }

        .browse-btn:hover {
          background: #e5e7eb;
        }

        .progress-container {
          margin-top: 24px;
          text-align: center;
        }

        .progress-bar {
          height: 8px;
          background: #e5e7eb;
          border-radius: 4px;
          overflow: hidden;
        }

        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #6366f1, #8b5cf6);
          transition: width 0.3s ease;
        }

        .result {
          margin-top: 24px;
          padding: 16px;
          border-radius: 8px;
          text-align: center;
        }

        .result.success {
          background: #d1fae5;
          color: #065f46;
        }

        .result.error {
          background: #fee2e2;
          color: #991b1b;
        }

        .success-icon,
        .error-icon {
          font-size: 32px;
          display: block;
          margin-bottom: 8px;
        }

        .vendor {
          font-weight: 600;
          font-size: 18px;
        }

        .amount {
          font-size: 24px;
          font-weight: 700;
        }
      `}</style>
    </div>
  );
};
```

---

### src/components/InvoiceList.tsx

```tsx
import React, { useState, useEffect, useCallback } from 'react';

interface Invoice {
  invoiceId: string;
  invoiceNumber: string | null;
  vendorName: string;
  amount: number;
  currency: string;
  invoiceDate: string | null;
  dueDate: string | null;
  status: string;
  paymentType: string | null;
  approvalStatus: string | null;
}

interface InvoiceSummary {
  totalPending: number;
  totalDue: number;
  overdue: number;
  awaitingApproval: number;
  paidThisMonth: number;
  scheduled: number;
}

export const InvoiceList: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<InvoiceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  const loadInvoices = useCallback(async () => {
    try {
      const params = new URLSearchParams({ search, limit: '50' });
      const response = await fetch(`/api/invoices?${params}`);
      const data = await response.json();
      setInvoices(data.invoices || []);
      setSummary(data.summary);
    } catch (error) {
      console.error('Failed to load invoices:', error);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadInvoices();
  }, [loadInvoices]);

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
    }).format(amount);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, React.CSSProperties> = {
      pending: { background: '#fef3c7', color: '#92400e' },
      approved: { background: '#d1fae5', color: '#065f46' },
      rejected: { background: '#fee2e2', color: '#991b1b' },
      paid: { background: '#dbeafe', color: '#1e40af' },
    };

    return (
      <span className="status-badge" style={styles[status] || {}}>
        {status}
      </span>
    );
  };

  const getPaymentBadge = (type: string | null) => {
    if (!type) return '-';

    const colors: Record<string, string> = {
      Wire: '#22c55e',
      ACH: '#a855f7',
      Card: '#3b82f6',
      PayPal: '#0070ba',
      Venmo: '#3d95ce',
      Crypto: '#f7931a',
    };

    return (
      <span
        className="payment-badge"
        style={{ background: colors[type] || '#6b7280' }}
      >
        {type}
      </span>
    );
  };

  const handleApprove = async (invoiceId: string) => {
    try {
      await fetch(`/api/invoices/${invoiceId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      loadInvoices();
      setSelectedInvoice(null);
    } catch (error) {
      console.error('Approve failed:', error);
    }
  };

  const handleReject = async (invoiceId: string) => {
    const reason = prompt('Please provide a reason for rejection:');
    if (!reason) return;

    try {
      await fetch(`/api/invoices/${invoiceId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      loadInvoices();
      setSelectedInvoice(null);
    } catch (error) {
      console.error('Reject failed:', error);
    }
  };

  if (loading) {
    return <div className="loading">Loading invoices...</div>;
  }

  return (
    <div className="invoice-list-container">
      {/* Summary Cards */}
      {summary && (
        <div className="summary-cards">
          <div className="summary-card">
            <div className="value">{summary.totalPending}</div>
            <div className="label">Total Pending</div>
          </div>
          <div className="summary-card">
            <div className="value">{formatCurrency(summary.totalDue)}</div>
            <div className="label">Total Due</div>
          </div>
          <div className="summary-card warning">
            <div className="value">{summary.overdue}</div>
            <div className="label">Overdue</div>
          </div>
          <div className="summary-card">
            <div className="value">{summary.awaitingApproval}</div>
            <div className="label">Awaiting Approval</div>
          </div>
          <div className="summary-card success">
            <div className="value">{formatCurrency(summary.paidThisMonth)}</div>
            <div className="label">Paid This Month</div>
          </div>
          <div className="summary-card">
            <div className="value">{summary.scheduled}</div>
            <div className="label">Scheduled</div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="search-bar">
        <input
          type="text"
          placeholder="Search invoices and recipients..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Table */}
      <table className="invoice-table">
        <thead>
          <tr>
            <th>Issue Date</th>
            <th>Invoice #</th>
            <th>Recipient</th>
            <th>Payment Type</th>
            <th>Due Date</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Approvals</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr
              key={invoice.invoiceId}
              onClick={() => setSelectedInvoice(invoice)}
              className={selectedInvoice?.invoiceId === invoice.invoiceId ? 'selected' : ''}
            >
              <td>{formatDate(invoice.invoiceDate)}</td>
              <td>{invoice.invoiceNumber || '-'}</td>
              <td>{invoice.vendorName}</td>
              <td>{getPaymentBadge(invoice.paymentType)}</td>
              <td className={invoice.dueDate && new Date(invoice.dueDate) < new Date() ? 'overdue' : ''}>
                {formatDate(invoice.dueDate)}
              </td>
              <td>{formatCurrency(invoice.amount, invoice.currency)}</td>
              <td>{getStatusBadge(invoice.status)}</td>
              <td>{invoice.approvalStatus ? getStatusBadge(invoice.approvalStatus) : '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Details Sidebar */}
      {selectedInvoice && (
        <div className="details-sidebar">
          <div className="sidebar-header">
            <h3>Invoice Details</h3>
            <button className="close-btn" onClick={() => setSelectedInvoice(null)}>
              &times;
            </button>
          </div>
          <div className="sidebar-content">
            {getStatusBadge(selectedInvoice.status)}
            <div className="invoice-number">{selectedInvoice.invoiceNumber}</div>
            <div className="amount-display">
              {formatCurrency(selectedInvoice.amount, selectedInvoice.currency)}
            </div>

            <div className="detail-section">
              <h4>Invoice Information</h4>
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Vendor</label>
                  <span>{selectedInvoice.vendorName}</span>
                </div>
                <div className="detail-item">
                  <label>Invoice Date</label>
                  <span>{formatDate(selectedInvoice.invoiceDate)}</span>
                </div>
                <div className="detail-item">
                  <label>Due Date</label>
                  <span>{formatDate(selectedInvoice.dueDate)}</span>
                </div>
              </div>
            </div>

            {selectedInvoice.status === 'pending' && (
              <div className="action-buttons">
                <button
                  className="btn-success"
                  onClick={() => handleApprove(selectedInvoice.invoiceId)}
                >
                  ✓ Approve
                </button>
                <button
                  className="btn-danger"
                  onClick={() => handleReject(selectedInvoice.invoiceId)}
                >
                  ✗ Reject
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .invoice-list-container {
          padding: 24px;
        }

        .summary-cards {
          display: flex;
          gap: 16px;
          margin-bottom: 24px;
          flex-wrap: wrap;
        }

        .summary-card {
          flex: 1;
          min-width: 150px;
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

        .summary-card.warning .value {
          color: #dc2626;
        }

        .summary-card.success .value {
          color: #22c55e;
        }

        .search-bar {
          margin-bottom: 16px;
        }

        .search-bar input {
          width: 100%;
          max-width: 400px;
          padding: 10px 16px;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          font-size: 14px;
        }

        .invoice-table {
          width: 100%;
          border-collapse: collapse;
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

        .invoice-table tr.selected {
          background: #eef2ff;
        }

        .status-badge {
          display: inline-block;
          padding: 4px 12px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 500;
        }

        .payment-badge {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
          color: white;
        }

        .overdue {
          color: #dc2626;
          font-weight: 500;
        }

        .details-sidebar {
          position: fixed;
          top: 0;
          right: 0;
          width: 400px;
          height: 100%;
          background: white;
          box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
          z-index: 1000;
        }

        .sidebar-header {
          padding: 24px;
          border-bottom: 1px solid #e5e7eb;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .close-btn {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
        }

        .sidebar-content {
          padding: 24px;
        }

        .invoice-number {
          font-size: 14px;
          color: #6b7280;
          margin-top: 8px;
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
          margin-top: 24px;
        }

        .btn-success {
          flex: 1;
          padding: 12px 24px;
          background: #22c55e;
          color: white;
          border: none;
          border-radius: 8px;
          font-weight: 500;
          cursor: pointer;
        }

        .btn-danger {
          flex: 1;
          padding: 12px 24px;
          background: white;
          color: #dc2626;
          border: 1px solid #dc2626;
          border-radius: 8px;
          font-weight: 500;
          cursor: pointer;
        }

        .loading {
          text-align: center;
          padding: 48px;
          color: #6b7280;
        }
      `}</style>
    </div>
  );
};
```

---

## Environment Configuration

### .env.example

```bash
# Server
PORT=5000
NODE_ENV=development

# Google Cloud Project
GOOGLE_CLOUD_PROJECT=your-project-id

# Google Cloud Credentials (JSON string)
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}

# Document AI
DOCUMENT_AI_LOCATION=us
DOCUMENT_AI_PROCESSOR_ID=your-processor-id

# Gemini AI
GOOGLE_GEMINI_API_KEY=your-gemini-api-key

# BigQuery
BIGQUERY_DATASET=vendors_ai

# Cloud Storage
GCS_BUCKET=your-invoice-bucket
```

---

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Copy environment template
cp .env.example .env

# 3. Configure environment variables in .env

# 4. Build TypeScript
npm run build

# 5. Start server
npm start

# Or for development with hot reload
npm run dev
```

---

## API Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/invoices/upload | Upload single invoice |
| POST | /api/invoices/upload/bulk | Upload multiple invoices |
| GET | /api/invoices | List invoices with filters |
| GET | /api/invoices/summary | Get summary statistics |
| GET | /api/invoices/:id | Get invoice details |
| POST | /api/invoices/:id/approve | Approve invoice |
| POST | /api/invoices/:id/reject | Reject invoice |
| GET | /api/invoices/:id/download | Get PDF download URL |
| GET | /api/invoices/export/csv | Export to CSV |

---

## Support

For questions about:
- **Google Document AI**: https://cloud.google.com/document-ai/docs
- **Gemini API**: https://ai.google.dev/docs
- **BigQuery**: https://cloud.google.com/bigquery/docs
- **Cloud Storage**: https://cloud.google.com/storage/docs
