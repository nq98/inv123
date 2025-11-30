# INVOICE MANAGEMENT - TYPESCRIPT IMPLEMENTATION PROMPT

## FOR: Adding Invoice Uploader to AP Automation Tab (TypeScript/Express)

---

## ARCHITECTURE: TypeScript Integration with Existing Python Services

Your TypeScript frontend/API will call the existing Python services via internal API or directly use Google Cloud SDKs.

---

## REQUIRED NPM PACKAGES

```bash
npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
npm install @google/generative-ai @google-cloud/discoveryengine
npm install express multer uuid date-fns cors helmet
npm install -D @types/express @types/multer @types/uuid @types/cors typescript
```

---

## SECRETS CONFIGURATION (TypeScript)

```typescript
// src/config/index.ts

export const config = {
  // Google Cloud Project
  GOOGLE_CLOUD_PROJECT_ID: process.env.GOOGLE_CLOUD_PROJECT_ID || '<PROJECT_ID>',
  GOOGLE_CLOUD_PROJECT_NUMBER: process.env.GOOGLE_CLOUD_PROJECT_NUMBER || '437918215047',
  
  // GCS Bucket for Invoice Storage
  GCS_BUCKET: process.env.GCS_INPUT_BUCKET || process.env.GCS_BUCKET_NAME || 'payouts-invoices',
  
  // Document AI
  DOCAI_PROCESSOR_ID: process.env.DOCAI_PROCESSOR_ID || '<PROCESSOR_ID>',
  DOCAI_LOCATION: process.env.DOCAI_LOCATION || 'us',
  
  // Vertex AI Search (RAG)
  VERTEX_SEARCH_DATA_STORE_ID: process.env.VERTEX_SEARCH_DATA_STORE_ID || 'invoices-ds',
  VERTEX_SEARCH_COLLECTION: process.env.VERTEX_SEARCH_COLLECTION || 'default_collection',
  
  // Gemini AI
  GOOGLE_GEMINI_API_KEY: process.env.GOOGLE_GEMINI_API_KEY || '',
  
  // BigQuery
  BIGQUERY_DATASET: process.env.BIGQUERY_DATASET || 'vendors_ai',
  
  // Service Account JSON (from secrets)
  GOOGLE_APPLICATION_CREDENTIALS_JSON: process.env.GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON || '',
  
  // Computed paths
  get DOCAI_PROCESSOR_NAME(): string {
    return `projects/${this.GOOGLE_CLOUD_PROJECT_ID}/locations/${this.DOCAI_LOCATION}/processors/${this.DOCAI_PROCESSOR_ID}`;
  },
  
  get VERTEX_SEARCH_SERVING_CONFIG(): string {
    return `projects/${this.GOOGLE_CLOUD_PROJECT_NUMBER}/locations/global/collections/${this.VERTEX_SEARCH_COLLECTION}/dataStores/${this.VERTEX_SEARCH_DATA_STORE_ID}/servingConfigs/default_search`;
  }
};
```

---

## TYPE DEFINITIONS

```typescript
// src/types/invoice.types.ts

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
  
  // Payment
  paymentType: PaymentType | null;
  
  // Workflow
  status: InvoiceStatus;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectedBy: string | null;
  rejectedAt: string | null;
  rejectionReason: string | null;
  
  // Storage
  gcsUri: string;
  originalFilename: string;
  
  // AI Metadata
  extractionConfidence: number;
  rawExtraction: Record<string, unknown> | null;
  
  // User
  userEmail: string;
  
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

export type Currency = 'USD' | 'EUR' | 'GBP' | 'CAD' | 'AUD' | 'JPY' | 'CNY' | 'INR' | 'ILS';
export type PaymentType = 'Wire' | 'ACH' | 'Card' | 'PayPal' | 'Venmo' | 'Crypto' | 'Check';
export type InvoiceStatus = 'pending' | 'approved' | 'rejected' | 'paid' | 'cancelled';

export interface ExtractedInvoiceData {
  vendorName: string;
  invoiceNumber: string | null;
  invoiceDate: string | null;
  dueDate: string | null;
  amount: number;
  subtotal: number | null;
  taxAmount: number | null;
  currency: Currency;
  paymentType: PaymentType | null;
  lineItems: LineItem[];
  confidence: number;
}

export interface UploadResponse {
  status: 'success' | 'error';
  invoiceId: string;
  extractedData?: ExtractedInvoiceData;
  gcsUri?: string;
  downloadUrl?: string;
  confidence?: number;
  error?: string;
}
```

---

## GCS SERVICE (TypeScript)

```typescript
// src/services/gcs.service.ts

import { Storage, Bucket, File } from '@google-cloud/storage';
import { format } from 'date-fns';
import { config } from '../config';

export class GCSService {
  private storage: Storage;
  private bucket: Bucket;
  
  constructor() {
    const credentials = config.GOOGLE_APPLICATION_CREDENTIALS_JSON
      ? JSON.parse(config.GOOGLE_APPLICATION_CREDENTIALS_JSON)
      : undefined;
    
    this.storage = credentials
      ? new Storage({ credentials, projectId: config.GOOGLE_CLOUD_PROJECT_ID })
      : new Storage({ projectId: config.GOOGLE_CLOUD_PROJECT_ID });
    
    this.bucket = this.storage.bucket(config.GCS_BUCKET);
  }
  
  /**
   * Upload invoice PDF to GCS
   * Path: invoices/{user_email}/{date}/{filename}
   */
  async uploadInvoice(
    buffer: Buffer,
    filename: string,
    userEmail: string,
    mimeType: string = 'application/pdf'
  ): Promise<string> {
    const datePath = format(new Date(), 'yyyy/MM/dd');
    const safeEmail = userEmail.replace('@', '_at_').replace(/\./g, '_');
    const gcsPath = `invoices/${safeEmail}/${datePath}/${filename}`;
    
    const file = this.bucket.file(gcsPath);
    
    await file.save(buffer, {
      contentType: mimeType,
      metadata: {
        uploadedBy: userEmail,
        uploadedAt: new Date().toISOString(),
      },
    });
    
    console.log(`✅ Uploaded to GCS: gs://${config.GCS_BUCKET}/${gcsPath}`);
    return `gs://${config.GCS_BUCKET}/${gcsPath}`;
  }
  
  /**
   * Generate signed URL for viewing/downloading PDF
   * Expires in 1 hour by default
   */
  async getSignedUrl(gcsUri: string, expirationSeconds: number = 3600): Promise<string> {
    // Parse gs://bucket/path format
    const uriParts = gcsUri.replace('gs://', '').split('/');
    const bucketName = uriParts[0];
    const filePath = uriParts.slice(1).join('/');
    
    const bucket = this.storage.bucket(bucketName);
    const file = bucket.file(filePath);
    
    // Check if file exists
    const [exists] = await file.exists();
    if (!exists) {
      throw new Error('File not found in storage');
    }
    
    // Determine content type
    const ext = filePath.split('.').pop()?.toLowerCase() || '';
    const contentTypeMap: Record<string, string> = {
      pdf: 'application/pdf',
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
    };
    const contentType = contentTypeMap[ext] || 'application/octet-stream';
    
    const [url] = await file.getSignedUrl({
      version: 'v4',
      action: 'read',
      expires: Date.now() + expirationSeconds * 1000,
      responseType: contentType,
    });
    
    return url;
  }
  
  /**
   * Check if file exists in GCS
   */
  async fileExists(gcsUri: string): Promise<boolean> {
    const uriParts = gcsUri.replace('gs://', '').split('/');
    const bucketName = uriParts[0];
    const filePath = uriParts.slice(1).join('/');
    
    const bucket = this.storage.bucket(bucketName);
    const file = bucket.file(filePath);
    const [exists] = await file.exists();
    return exists;
  }
}
```

---

## DOCUMENT AI SERVICE (TypeScript)

```typescript
// src/services/document-ai.service.ts

import { DocumentProcessorServiceClient } from '@google-cloud/documentai';
import { config } from '../config';

interface DocumentAIResult {
  text: string;
  entities: Record<string, Array<{ value: string; confidence: number }>>;
  pages: number;
}

export class DocumentAIService {
  private client: DocumentProcessorServiceClient;
  private processorName: string;
  
  constructor() {
    const credentials = config.GOOGLE_APPLICATION_CREDENTIALS_JSON
      ? JSON.parse(config.GOOGLE_APPLICATION_CREDENTIALS_JSON)
      : undefined;
    
    this.client = credentials
      ? new DocumentProcessorServiceClient({ credentials })
      : new DocumentProcessorServiceClient();
    
    this.processorName = config.DOCAI_PROCESSOR_NAME;
  }
  
  /**
   * Layer 1: Extract text and entities using Document AI OCR
   */
  async processDocument(content: Buffer, mimeType: string): Promise<DocumentAIResult> {
    console.log('📄 Layer 1: Document AI - OCR Extraction...');
    
    const [result] = await this.client.processDocument({
      name: this.processorName,
      rawDocument: {
        content: content.toString('base64'),
        mimeType,
      },
    });
    
    const document = result.document;
    if (!document) {
      return { text: '', entities: {}, pages: 0 };
    }
    
    // Extract entities by type
    const entities: Record<string, Array<{ value: string; confidence: number }>> = {};
    
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
    
    console.log(`✅ Extracted ${document.text?.length || 0} chars, ${Object.keys(entities).length} entity types`);
    
    return {
      text: document.text || '',
      entities,
      pages: document.pages?.length || 0,
    };
  }
}
```

---

## GEMINI SERVICE (TypeScript)

```typescript
// src/services/gemini.service.ts

import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';
import { config } from '../config';
import { ExtractedInvoiceData, Currency, PaymentType } from '../types/invoice.types';

export class GeminiService {
  private model: GenerativeModel;
  
  constructor() {
    const genAI = new GoogleGenerativeAI(config.GOOGLE_GEMINI_API_KEY);
    this.model = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
  }
  
  /**
   * Layer 3: Semantic extraction using Gemini AI
   */
  async extractInvoiceData(
    documentText: string,
    ragContext: string = ''
  ): Promise<ExtractedInvoiceData> {
    console.log('🧠 Layer 3: Gemini AI - Semantic Extraction...');
    
    const prompt = `You are an expert invoice parser. Extract all invoice data from this document.

DOCUMENT TEXT:
${documentText.substring(0, 8000)}

${ragContext ? `HISTORICAL CONTEXT:\n${ragContext}` : ''}

EXTRACTION RULES:
1. Extract vendor/supplier name (company issuing the invoice)
2. Extract invoice number exactly as shown
3. Extract all monetary amounts (subtotal, tax, total)
4. Parse dates in ISO format (YYYY-MM-DD)
5. Identify currency (USD, EUR, GBP, etc.)
6. Extract line items with descriptions and amounts
7. Detect payment type if mentioned: Wire, ACH, Card, PayPal, Venmo, Crypto, Check

PAYMENT TYPE DETECTION:
- Wire: Bank wire, SWIFT, routing number, international transfer
- ACH: ACH transfer, direct debit, US bank details
- Card: Credit card, Visa, Mastercard, Amex
- PayPal: PayPal email or link
- Venmo: Venmo username
- Crypto: Bitcoin, Ethereum, wallet address
- Check: Mail check instructions

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
    "paymentType": "Wire" | "ACH" | "Card" | "PayPal" | "Venmo" | "Crypto" | "Check" | null,
    "lineItems": [{"description": "string", "quantity": number, "unitPrice": number, "amount": number}],
    "confidence": 0.0 to 1.0
}

Return ONLY valid JSON, no markdown or explanation.`;

    const result = await this.model.generateContent(prompt);
    const response = await result.response;
    let text = response.text();
    
    // Parse JSON from response
    if (text.includes('```json')) {
      text = text.split('```json')[1].split('```')[0];
    } else if (text.includes('```')) {
      text = text.split('```')[1].split('```')[0];
    }
    
    try {
      const parsed = JSON.parse(text.trim());
      console.log(`✅ Extracted: ${parsed.vendorName}, ${parsed.currency} ${parsed.amount}`);
      return parsed as ExtractedInvoiceData;
    } catch (e) {
      console.error('❌ Failed to parse Gemini response:', e);
      throw new Error('Failed to parse invoice data from AI response');
    }
  }
}
```

---

## BIGQUERY SERVICE (TypeScript)

```typescript
// src/services/bigquery.service.ts

import { BigQuery } from '@google-cloud/bigquery';
import { config } from '../config';
import { Invoice, InvoiceStatus } from '../types/invoice.types';

export class BigQueryService {
  private client: BigQuery;
  private datasetId: string;
  private tableId: string;
  private fullTableId: string;
  
  constructor() {
    const credentials = config.GOOGLE_APPLICATION_CREDENTIALS_JSON
      ? JSON.parse(config.GOOGLE_APPLICATION_CREDENTIALS_JSON)
      : undefined;
    
    this.client = credentials
      ? new BigQuery({ credentials, projectId: config.GOOGLE_CLOUD_PROJECT_ID })
      : new BigQuery({ projectId: config.GOOGLE_CLOUD_PROJECT_ID });
    
    this.datasetId = config.BIGQUERY_DATASET;
    this.tableId = 'invoices';
    this.fullTableId = `${config.GOOGLE_CLOUD_PROJECT_ID}.${this.datasetId}.${this.tableId}`;
  }
  
  /**
   * Insert new invoice into BigQuery
   */
  async insertInvoice(invoice: Partial<Invoice>): Promise<void> {
    const row = {
      invoice_id: invoice.invoiceId,
      invoice_number: invoice.invoiceNumber,
      vendor_name: invoice.vendorName,
      vendor_id: invoice.vendorId,
      amount: invoice.amount,
      currency: invoice.currency,
      tax_amount: invoice.taxAmount,
      subtotal: invoice.subtotal,
      invoice_date: invoice.invoiceDate,
      due_date: invoice.dueDate,
      payment_type: invoice.paymentType,
      status: invoice.status || 'pending',
      gcs_uri: invoice.gcsUri,
      original_filename: invoice.originalFilename,
      extraction_confidence: invoice.extractionConfidence,
      raw_extraction: invoice.rawExtraction ? JSON.stringify(invoice.rawExtraction) : null,
      user_email: invoice.userEmail,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    
    await this.client.dataset(this.datasetId).table(this.tableId).insert([row]);
    console.log(`✅ Stored invoice ${invoice.invoiceId} in BigQuery`);
  }
  
  /**
   * List invoices with filters
   */
  async listInvoices(
    userEmail: string,
    options: {
      page?: number;
      limit?: number;
      status?: InvoiceStatus;
      search?: string;
    } = {}
  ): Promise<{ invoices: Invoice[]; total: number }> {
    const { page = 1, limit = 50, status, search } = options;
    const offset = (page - 1) * limit;
    
    let whereClause = `WHERE user_email = @userEmail`;
    if (status) {
      whereClause += ` AND status = @status`;
    }
    if (search) {
      whereClause += ` AND (vendor_name LIKE @search OR invoice_number LIKE @search)`;
    }
    
    const query = `
      SELECT * FROM \`${this.fullTableId}\`
      ${whereClause}
      ORDER BY created_at DESC
      LIMIT ${limit} OFFSET ${offset}
    `;
    
    const [rows] = await this.client.query({
      query,
      params: { userEmail, status, search: search ? `%${search}%` : undefined },
    });
    
    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total FROM \`${this.fullTableId}\`
      ${whereClause}
    `;
    const [countRows] = await this.client.query({
      query: countQuery,
      params: { userEmail, status, search: search ? `%${search}%` : undefined },
    });
    
    return {
      invoices: rows as Invoice[],
      total: countRows[0]?.total || 0,
    };
  }
  
  /**
   * Get single invoice by ID
   */
  async getInvoice(invoiceId: string): Promise<Invoice | null> {
    const query = `
      SELECT * FROM \`${this.fullTableId}\`
      WHERE invoice_id = @invoiceId
      LIMIT 1
    `;
    
    const [rows] = await this.client.query({ query, params: { invoiceId } });
    return rows.length > 0 ? (rows[0] as Invoice) : null;
  }
  
  /**
   * Approve invoice
   */
  async approveInvoice(invoiceId: string, userEmail: string): Promise<void> {
    const query = `
      UPDATE \`${this.fullTableId}\`
      SET status = 'approved',
          approved_by = @userEmail,
          approved_at = CURRENT_TIMESTAMP(),
          updated_at = CURRENT_TIMESTAMP()
      WHERE invoice_id = @invoiceId
    `;
    
    await this.client.query({ query, params: { invoiceId, userEmail } });
    console.log(`✅ Approved invoice ${invoiceId}`);
  }
  
  /**
   * Reject invoice
   */
  async rejectInvoice(invoiceId: string, userEmail: string, reason: string): Promise<void> {
    const query = `
      UPDATE \`${this.fullTableId}\`
      SET status = 'rejected',
          rejected_by = @userEmail,
          rejected_at = CURRENT_TIMESTAMP(),
          rejection_reason = @reason,
          updated_at = CURRENT_TIMESTAMP()
      WHERE invoice_id = @invoiceId
    `;
    
    await this.client.query({ query, params: { invoiceId, userEmail, reason } });
    console.log(`❌ Rejected invoice ${invoiceId}: ${reason}`);
  }
}
```

---

## INVOICE PARSER SERVICE (TypeScript)

```typescript
// src/services/invoice-parser.service.ts

import { v4 as uuidv4 } from 'uuid';
import { format } from 'date-fns';
import { GCSService } from './gcs.service';
import { DocumentAIService } from './document-ai.service';
import { GeminiService } from './gemini.service';
import { BigQueryService } from './bigquery.service';
import { UploadResponse, ExtractedInvoiceData } from '../types/invoice.types';

export class InvoiceParserService {
  private gcsService: GCSService;
  private docAIService: DocumentAIService;
  private geminiService: GeminiService;
  private bigqueryService: BigQueryService;
  
  constructor() {
    this.gcsService = new GCSService();
    this.docAIService = new DocumentAIService();
    this.geminiService = new GeminiService();
    this.bigqueryService = new BigQueryService();
  }
  
  /**
   * Parse invoice using 4-layer AI pipeline
   */
  async parseInvoice(
    buffer: Buffer,
    filename: string,
    mimeType: string,
    userEmail: string
  ): Promise<UploadResponse> {
    const invoiceId = this.generateInvoiceId();
    
    console.log(`\n${'='.repeat(60)}`);
    console.log(`PROCESSING INVOICE: ${filename}`);
    console.log(`${'='.repeat(60)}\n`);
    
    try {
      // Layer 0: Upload to GCS
      console.log('📤 Uploading to GCS...');
      const gcsUri = await this.gcsService.uploadInvoice(buffer, filename, userEmail, mimeType);
      
      // Layer 1: Document AI OCR
      const docAIResult = await this.docAIService.processDocument(buffer, mimeType);
      
      // Layer 2: RAG Context (optional - implement if needed)
      const ragContext = ''; // Add Vertex AI Search integration here
      
      // Layer 3: Gemini Semantic Extraction
      const extractedData = await this.geminiService.extractInvoiceData(docAIResult.text, ragContext);
      
      // Layer 4: Validation
      const validatedData = this.validateExtraction(extractedData, docAIResult);
      
      // Store in BigQuery
      await this.bigqueryService.insertInvoice({
        invoiceId,
        invoiceNumber: validatedData.invoiceNumber,
        vendorName: validatedData.vendorName,
        amount: validatedData.amount,
        currency: validatedData.currency,
        taxAmount: validatedData.taxAmount,
        subtotal: validatedData.subtotal,
        invoiceDate: validatedData.invoiceDate,
        dueDate: validatedData.dueDate,
        paymentType: validatedData.paymentType,
        status: 'pending',
        gcsUri,
        originalFilename: filename,
        extractionConfidence: validatedData.confidence,
        rawExtraction: validatedData,
        userEmail,
      });
      
      // Generate signed URL for immediate viewing
      const downloadUrl = await this.gcsService.getSignedUrl(gcsUri);
      
      console.log(`\n${'='.repeat(60)}`);
      console.log('✅ PROCESSING COMPLETE');
      console.log(`${'='.repeat(60)}\n`);
      
      return {
        status: 'success',
        invoiceId,
        extractedData: validatedData,
        gcsUri,
        downloadUrl,
        confidence: validatedData.confidence,
      };
      
    } catch (error) {
      console.error('❌ Invoice parsing failed:', error);
      return {
        status: 'error',
        invoiceId,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
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
   * Layer 4: Validate extraction
   */
  private validateExtraction(
    extracted: ExtractedInvoiceData,
    docAI: { text: string; entities: Record<string, any[]> }
  ): ExtractedInvoiceData {
    console.log('✅ Layer 4: Validation...');
    
    // Math validation: subtotal + tax = total
    if (extracted.subtotal && extracted.taxAmount) {
      const calculated = extracted.subtotal + extracted.taxAmount;
      if (Math.abs(calculated - extracted.amount) > 0.01) {
        console.warn(`⚠️ Math mismatch: ${extracted.subtotal} + ${extracted.taxAmount} != ${extracted.amount}`);
      }
    }
    
    return extracted;
  }
  
  /**
   * Get signed URL for invoice download
   */
  async getDownloadUrl(invoiceId: string): Promise<string | null> {
    const invoice = await this.bigqueryService.getInvoice(invoiceId);
    if (!invoice?.gcsUri) return null;
    return this.gcsService.getSignedUrl(invoice.gcsUri);
  }
  
  /**
   * List invoices
   */
  async listInvoices(userEmail: string, options?: any) {
    return this.bigqueryService.listInvoices(userEmail, options);
  }
  
  /**
   * Approve invoice
   */
  async approveInvoice(invoiceId: string, userEmail: string) {
    await this.bigqueryService.approveInvoice(invoiceId, userEmail);
    return { status: 'success', message: 'Invoice approved' };
  }
  
  /**
   * Reject invoice
   */
  async rejectInvoice(invoiceId: string, userEmail: string, reason: string) {
    await this.bigqueryService.rejectInvoice(invoiceId, userEmail, reason);
    return { status: 'success', message: 'Invoice rejected' };
  }
}
```

---

## EXPRESS API ROUTES (TypeScript)

```typescript
// src/routes/invoice.routes.ts

import { Router, Request, Response } from 'express';
import multer from 'multer';
import { InvoiceParserService } from '../services/invoice-parser.service';

const router = Router();
const upload = multer({ storage: multer.memoryStorage() });
const invoiceService = new InvoiceParserService();

// POST /api/invoices/upload - Upload single invoice
router.post('/upload', upload.single('file'), async (req: Request, res: Response) => {
  try {
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
  } catch (error) {
    res.status(500).json({ 
      status: 'error', 
      message: error instanceof Error ? error.message : 'Upload failed' 
    });
  }
});

// GET /api/invoices - List invoices
router.get('/', async (req: Request, res: Response) => {
  try {
    const userEmail = (req as any).user?.email;
    const result = await invoiceService.listInvoices(userEmail, {
      page: parseInt(req.query.page as string) || 1,
      limit: parseInt(req.query.limit as string) || 50,
      status: req.query.status as any,
      search: req.query.search as string,
    });
    res.json(result);
  } catch (error) {
    res.status(500).json({ status: 'error', message: 'Failed to list invoices' });
  }
});

// GET /api/invoices/:id/download - Get signed URL
router.get('/:invoiceId/download', async (req: Request, res: Response) => {
  try {
    const url = await invoiceService.getDownloadUrl(req.params.invoiceId);
    if (!url) {
      return res.status(404).json({ status: 'error', message: 'PDF not found' });
    }
    res.json({ status: 'success', downloadUrl: url, expiresIn: 3600 });
  } catch (error) {
    res.status(500).json({ status: 'error', message: 'Download failed' });
  }
});

// POST /api/invoices/:id/approve
router.post('/:invoiceId/approve', async (req: Request, res: Response) => {
  try {
    const userEmail = (req as any).user?.email;
    const result = await invoiceService.approveInvoice(req.params.invoiceId, userEmail);
    res.json(result);
  } catch (error) {
    res.status(500).json({ status: 'error', message: 'Approval failed' });
  }
});

// POST /api/invoices/:id/reject
router.post('/:invoiceId/reject', async (req: Request, res: Response) => {
  try {
    const { reason } = req.body;
    if (!reason) {
      return res.status(400).json({ status: 'error', message: 'Reason required' });
    }
    const userEmail = (req as any).user?.email;
    const result = await invoiceService.rejectInvoice(req.params.invoiceId, userEmail, reason);
    res.json(result);
  } catch (error) {
    res.status(500).json({ status: 'error', message: 'Rejection failed' });
  }
});

export default router;
```

---

## PROJECT STRUCTURE

```
src/
├── config/
│   └── index.ts                    # All secrets and configuration
├── types/
│   └── invoice.types.ts            # TypeScript interfaces
├── services/
│   ├── gcs.service.ts              # GCS upload + signed URLs
│   ├── document-ai.service.ts      # Document AI OCR
│   ├── gemini.service.ts           # Gemini semantic extraction
│   ├── bigquery.service.ts         # BigQuery storage
│   └── invoice-parser.service.ts   # Main 4-layer pipeline
├── routes/
│   └── invoice.routes.ts           # Express API routes
└── index.ts                        # Express app entry
```

---

## COMPLETE FLOW

```
1. User uploads PDF
         ↓
2. Multer receives file buffer
         ↓
3. InvoiceParserService.parseInvoice()
         ↓
   ┌────────────────────────────────────────┐
   │  Layer 0: Upload to GCS               │
   │  └── gs://payouts-invoices/invoices/  │
   │                                        │
   │  Layer 1: Document AI OCR             │
   │  └── Extract text and entities        │
   │                                        │
   │  Layer 2: RAG Context (optional)      │
   │  └── Historical vendor patterns       │
   │                                        │
   │  Layer 3: Gemini Semantic Extraction  │
   │  └── AI reasoning + payment detection │
   │                                        │
   │  Layer 4: Validation                  │
   │  └── Math check, date validation      │
   └────────────────────────────────────────┘
         ↓
4. Store in BigQuery `invoices` table
         ↓
5. Generate signed URL for viewing
         ↓
6. Return to frontend:
   - invoiceId
   - extractedData (vendor, amount, dates, payment type)
   - downloadUrl (signed URL to view PDF)
   - confidence score
```

---

## START IMPLEMENTATION

1. Install npm packages
2. Create `src/config/index.ts` with secrets
3. Create `src/types/invoice.types.ts`
4. Create services: GCS, Document AI, Gemini, BigQuery
5. Create `InvoiceParserService` with 4-layer pipeline
6. Create Express routes
7. Build React frontend components
8. Test full flow: upload → AI parse → view PDF → approve/reject
