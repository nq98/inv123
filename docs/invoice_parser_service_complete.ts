/**
 * Invoice Parser Service - Complete TypeScript Implementation
 * 4-Layer Hybrid AI Extraction Engine
 * 
 * Copy this to: src/services/invoice-parser.service.ts
 * 
 * Dependencies:
 * npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
 * npm install @google/generative-ai uuid date-fns
 */

import { v4 as uuidv4 } from 'uuid';
import { format } from 'date-fns';
import { DocumentProcessorServiceClient } from '@google-cloud/documentai';
import { Storage, Bucket } from '@google-cloud/storage';
import { BigQuery } from '@google-cloud/bigquery';
import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';

// ============================================
// TYPE DEFINITIONS
// ============================================

export interface Invoice {
  invoiceId: string;
  invoiceNumber: string | null;
  vendorName: string;
  vendorId: string | null;
  amount: number;
  currency: Currency;
  taxAmount: number | null;
  subtotal: number | null;
  invoiceDate: string | null;
  dueDate: string | null;
  scheduledDate: string | null;
  paymentType: PaymentType | null;
  paymentStatus: PaymentStatus;
  category: string | null;
  glCode: string | null;
  description: string | null;
  lineItems: LineItem[];
  status: InvoiceStatus;
  approvalStatus: ApprovalStatus | null;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectedBy: string | null;
  rejectedAt: string | null;
  rejectionReason: string | null;
  source: InvoiceSource;
  originalFilename: string | null;
  gcsPath: string | null;
  extractionConfidence: number;
  extractionMethod: string;
  rawExtraction: Record<string, unknown> | null;
  userEmail: string;
  tenantId: string | null;
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

interface DocumentAIResult {
  text: string;
  entities: Record<string, EntityValue[]>;
  tables: unknown[];
  pages: number;
}

interface EntityValue {
  value: string;
  confidence: number;
}

interface RAGContext {
  vendorHistory?: VendorHistoryItem[];
  typicalCategory?: string;
  typicalPaymentType?: PaymentType;
}

interface VendorHistoryItem {
  vendorName: string;
  invoiceNumber: string;
  amount: number;
  currency: Currency;
  category: string;
  paymentType: PaymentType;
}

// ============================================
// INVOICE PARSER SERVICE
// ============================================

export class InvoiceParserService {
  private projectId: string;
  private datasetId: string;
  private location: string;
  private processorId: string;
  private bucketName: string;
  
  private docAIClient: DocumentProcessorServiceClient | null = null;
  private storage: Storage | null = null;
  private bucket: Bucket | null = null;
  private bigquery: BigQuery | null = null;
  private geminiModel: GenerativeModel | null = null;

  constructor() {
    // Load configuration from environment
    this.projectId = process.env.GOOGLE_CLOUD_PROJECT || '';
    this.datasetId = process.env.BIGQUERY_DATASET || 'vendors_ai';
    this.location = process.env.DOCUMENT_AI_LOCATION || 'us';
    this.processorId = process.env.DOCUMENT_AI_PROCESSOR_ID || '';
    this.bucketName = process.env.GCS_BUCKET || 'payouts-invoices';
    
    this.initClients();
  }

  /**
   * Initialize all Google Cloud clients
   */
  private initClients(): void {
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
    let credentials: Record<string, unknown> | undefined;
    
    if (credentialsJson) {
      try {
        credentials = JSON.parse(credentialsJson);
      } catch (e) {
        console.error('Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON:', e);
      }
    }

    // Document AI Client
    try {
      this.docAIClient = credentials
        ? new DocumentProcessorServiceClient({ credentials })
        : new DocumentProcessorServiceClient();
      console.log('Document AI client initialized');
    } catch (e) {
      console.error('Failed to initialize Document AI:', e);
    }

    // Storage Client
    try {
      this.storage = credentials
        ? new Storage({ credentials })
        : new Storage();
      this.bucket = this.storage.bucket(this.bucketName);
      console.log('GCS client initialized');
    } catch (e) {
      console.error('Failed to initialize GCS:', e);
    }

    // BigQuery Client
    try {
      this.bigquery = credentials
        ? new BigQuery({ credentials, projectId: this.projectId })
        : new BigQuery({ projectId: this.projectId });
      console.log('BigQuery client initialized');
    } catch (e) {
      console.error('Failed to initialize BigQuery:', e);
    }

    // Gemini AI Client
    const geminiApiKey = process.env.GOOGLE_GEMINI_API_KEY;
    if (geminiApiKey) {
      try {
        const genAI = new GoogleGenerativeAI(geminiApiKey);
        this.geminiModel = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
        console.log('Gemini AI client initialized');
      } catch (e) {
        console.error('Failed to initialize Gemini:', e);
      }
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
   * Parse a single invoice using 4-layer hybrid approach
   */
  async parseInvoice(
    fileBuffer: Buffer,
    filename: string,
    mimeType: string,
    userEmail: string
  ): Promise<UploadInvoiceResponse> {
    const invoiceId = this.generateInvoiceId();
    console.log(`Starting invoice parsing for: ${filename} (${invoiceId})`);

    try {
      // Layer 1: Upload to GCS
      const gcsPath = await this.uploadToGCS(fileBuffer, filename, userEmail);

      // Layer 2: Document AI extraction
      const docAIResult = await this.extractWithDocumentAI(fileBuffer, mimeType);

      // Layer 3: Get RAG context from historical invoices
      const ragContext = await this.getRAGContext(docAIResult);

      // Layer 4: Gemini semantic reasoning
      const extractedData = await this.semanticExtraction(docAIResult, ragContext);

      // Layer 5: Validation
      const validatedData = this.validateExtraction(extractedData, docAIResult);

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
   * Upload invoice PDF to Google Cloud Storage
   */
  private async uploadToGCS(
    content: Buffer,
    filename: string,
    userEmail: string
  ): Promise<string> {
    if (!this.bucket) {
      throw new Error('GCS not initialized');
    }

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

    console.log(`Uploaded to GCS: ${gcsPath}`);
    return gcsPath;
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

  /**
   * Layer 1: Extract using Google Document AI
   */
  private async extractWithDocumentAI(
    content: Buffer,
    mimeType: string
  ): Promise<DocumentAIResult> {
    if (!this.docAIClient || !this.processorId) {
      console.warn('Document AI not available, returning empty result');
      return { text: '', entities: {}, tables: [], pages: 0 };
    }

    try {
      const processorName = `projects/${this.projectId}/locations/${this.location}/processors/${this.processorId}`;

      const [result] = await this.docAIClient.processDocument({
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

      console.log(`Document AI extracted ${Object.keys(entities).length} entity types`);
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

  /**
   * Layer 2: Get historical context from Vertex AI Search / BigQuery
   */
  private async getRAGContext(docAIResult: DocumentAIResult): Promise<RAGContext> {
    const vendorHint = this.extractVendorHint(docAIResult);
    if (!vendorHint || !this.bigquery) return {};

    try {
      const tableId = `${this.projectId}.${this.datasetId}.invoices`;
      const query = `
        SELECT vendor_name, invoice_number, amount, currency, category, payment_type
        FROM \`${tableId}\`
        WHERE LOWER(vendor_name) LIKE LOWER('%${vendorHint.substring(0, 20)}%')
        ORDER BY created_at DESC
        LIMIT 5
      `;

      const [rows] = await this.bigquery.query({ query });

      if (rows.length > 0) {
        return {
          vendorHistory: rows.map((row: any) => ({
            vendorName: row.vendor_name,
            invoiceNumber: row.invoice_number,
            amount: row.amount,
            currency: row.currency,
            category: row.category,
            paymentType: row.payment_type,
          })),
          typicalCategory: rows[0].category,
          typicalPaymentType: rows[0].payment_type,
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
   * Layer 3: Gemini AI semantic extraction
   */
  private async semanticExtraction(
    docAIResult: DocumentAIResult,
    ragContext: RAGContext
  ): Promise<ExtractedInvoiceData> {
    if (!this.geminiModel) {
      console.warn('Gemini not available, using fallback extraction');
      return this.fallbackExtraction(docAIResult);
    }

    const docText = docAIResult.text.substring(0, 8000);
    const ragInfo = ragContext.typicalCategory
      ? `Historical Context for this vendor:
- Typical Category: ${ragContext.typicalCategory}
- Typical Payment Type: ${ragContext.typicalPaymentType}
- Previous invoices found: ${ragContext.vendorHistory?.length || 0}`
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

Return ONLY valid JSON, no markdown or explanation.`;

    try {
      const result = await this.geminiModel.generateContent(prompt);
      const response = await result.response;
      let text = response.text();

      // Parse JSON from response
      if (text.includes('```json')) {
        text = text.split('```json')[1].split('```')[0];
      } else if (text.includes('```')) {
        text = text.split('```')[1].split('```')[0];
      }

      const parsed = JSON.parse(text.trim());
      console.log(`Gemini extracted invoice: ${parsed.vendorName} - ${parsed.amount}`);
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
      vendorName: this.getFirstEntity(entities, 'supplier_name') || 'Unknown Vendor',
      invoiceNumber: this.getFirstEntity(entities, 'invoice_id'),
      invoiceDate: this.getFirstEntity(entities, 'invoice_date'),
      dueDate: this.getFirstEntity(entities, 'due_date'),
      amount: this.parseAmount(this.getFirstEntity(entities, 'total_amount')),
      subtotal: null,
      taxAmount: null,
      currency: (this.getFirstEntity(entities, 'currency') as Currency) || 'USD',
      documentType: 'invoice',
      description: null,
      lineItems: [],
      paymentTerms: null,
      category: null,
      confidence: 0.5,
    };
  }

  /**
   * Get first entity value
   */
  private getFirstEntity(entities: Record<string, EntityValue[]>, key: string): string | null {
    const values = entities?.[key] || [];
    return values.length > 0 ? values[0].value : null;
  }

  /**
   * Parse amount string to number
   */
  private parseAmount(amountStr: string | null): number {
    if (!amountStr) return 0;
    const cleaned = amountStr.replace(/[$€£¥,]/g, '').trim();
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }

  /**
   * Layer 4: Validate extracted data
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
   * Store invoice in BigQuery
   */
  private async storeInvoice(
    invoiceId: string,
    data: ExtractedInvoiceData,
    gcsPath: string,
    userEmail: string,
    filename: string
  ): Promise<void> {
    if (!this.bigquery) {
      console.warn('BigQuery not available, skipping storage');
      return;
    }

    const row = {
      invoice_id: invoiceId,
      invoice_number: data.invoiceNumber,
      vendor_name: data.vendorName,
      vendor_id: null,
      amount: data.amount,
      currency: data.currency,
      tax_amount: data.taxAmount,
      subtotal: data.subtotal,
      invoice_date: data.invoiceDate,
      due_date: data.dueDate,
      scheduled_date: null,
      payment_type: null,
      payment_status: 'pending',
      category: data.category,
      gl_code: null,
      description: data.description,
      line_items: JSON.stringify(data.lineItems),
      status: 'pending',
      approval_status: null,
      approved_by: null,
      approved_at: null,
      rejected_by: null,
      rejected_at: null,
      rejection_reason: null,
      source: 'upload',
      original_filename: filename,
      gcs_path: gcsPath,
      extraction_confidence: data.confidence,
      extraction_method: '4-layer-hybrid',
      raw_extraction: JSON.stringify(data),
      user_email: userEmail,
      tenant_id: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    try {
      await this.bigquery.dataset(this.datasetId).table('invoices').insert([row]);
      console.log(`Stored invoice ${invoiceId} in BigQuery`);
    } catch (error) {
      console.error('BigQuery insert error:', error);
      throw error;
    }
  }

  /**
   * List invoices with filters and pagination
   */
  async listInvoices(
    userEmail: string,
    params: ListInvoicesParams
  ): Promise<ListInvoicesResponse> {
    if (!this.bigquery) {
      return { invoices: [], pagination: { page: 1, limit: 50, total: 0, pages: 0 }, summary: this.emptySummary() };
    }

    const {
      page = 1,
      limit = 50,
      status,
      paymentType,
      currency,
      dateFrom,
      dateTo,
      search,
      sortBy = 'createdAt',
      sortOrder = 'desc',
    } = params;

    const offset = (page - 1) * limit;
    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
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

    const whereClause = `WHERE ${conditions.join(' AND ')}`;
    const sortColumn = this.mapSortColumn(sortBy);
    const order = sortOrder.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

    const query = `
      SELECT * FROM \`${tableId}\`
      ${whereClause}
      ORDER BY ${sortColumn} ${order}
      LIMIT ${limit} OFFSET ${offset}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM \`${tableId}\`
      ${whereClause}
    `;

    try {
      const [invoiceRows] = await this.bigquery.query({ query });
      const [countRows] = await this.bigquery.query({ query: countQuery });

      const invoices = invoiceRows.map((row: any) => this.mapRowToInvoice(row));
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
    } catch (error) {
      console.error('List invoices error:', error);
      return { invoices: [], pagination: { page: 1, limit: 50, total: 0, pages: 0 }, summary: this.emptySummary() };
    }
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

  /**
   * Get single invoice by ID
   */
  async getInvoice(invoiceId: string): Promise<Invoice | null> {
    if (!this.bigquery) return null;

    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
    const query = `
      SELECT * FROM \`${tableId}\`
      WHERE invoice_id = @invoiceId
    `;

    try {
      const [rows] = await this.bigquery.query({
        query,
        params: { invoiceId },
      });

      return rows.length > 0 ? this.mapRowToInvoice(rows[0]) : null;
    } catch (error) {
      console.error('Get invoice error:', error);
      return null;
    }
  }

  /**
   * Update invoice data
   */
  async updateInvoice(
    invoiceId: string,
    data: Partial<Invoice>,
    userEmail: string
  ): Promise<{ status: string; message: string }> {
    if (!this.bigquery) {
      return { status: 'error', message: 'Database not available' };
    }

    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
    const allowedFields = [
      'vendor_name', 'invoice_number', 'amount', 'currency',
      'invoice_date', 'due_date', 'description', 'category',
      'payment_type', 'scheduled_date'
    ];

    const fieldMapping: Record<string, string> = {
      vendorName: 'vendor_name',
      invoiceNumber: 'invoice_number',
      invoiceDate: 'invoice_date',
      dueDate: 'due_date',
      paymentType: 'payment_type',
      scheduledDate: 'scheduled_date',
    };

    const setClauses: string[] = [];
    for (const [key, value] of Object.entries(data)) {
      const dbField = fieldMapping[key] || key;
      if (allowedFields.includes(dbField)) {
        if (typeof value === 'string') {
          setClauses.push(`${dbField} = '${value}'`);
        } else if (value === null) {
          setClauses.push(`${dbField} = NULL`);
        } else if (typeof value === 'number') {
          setClauses.push(`${dbField} = ${value}`);
        }
      }
    }

    if (setClauses.length === 0) {
      return { status: 'error', message: 'No valid fields to update' };
    }

    setClauses.push(`updated_at = CURRENT_TIMESTAMP()`);

    const query = `
      UPDATE \`${tableId}\`
      SET ${setClauses.join(', ')}
      WHERE invoice_id = '${invoiceId}'
    `;

    try {
      await this.bigquery.query({ query });
      return { status: 'success', message: 'Invoice updated' };
    } catch (error) {
      console.error('Update invoice error:', error);
      return { status: 'error', message: error instanceof Error ? error.message : 'Update failed' };
    }
  }

  /**
   * Approve invoice
   */
  async approveInvoice(
    invoiceId: string,
    userEmail: string,
    scheduledDate?: string,
    notes?: string
  ): Promise<{ status: string; message: string; invoiceId: string; approvedBy: string; approvedAt: string }> {
    if (!this.bigquery) {
      return { status: 'error', message: 'Database not available', invoiceId, approvedBy: '', approvedAt: '' };
    }

    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
    const scheduledSql = scheduledDate ? `, scheduled_date = '${scheduledDate}'` : '';

    const query = `
      UPDATE \`${tableId}\`
      SET status = 'approved',
          approval_status = 'approved',
          approved_by = '${userEmail}',
          approved_at = CURRENT_TIMESTAMP(),
          updated_at = CURRENT_TIMESTAMP()
          ${scheduledSql}
      WHERE invoice_id = '${invoiceId}'
    `;

    try {
      await this.bigquery.query({ query });
      return {
        status: 'success',
        message: 'Invoice approved',
        invoiceId,
        approvedBy: userEmail,
        approvedAt: new Date().toISOString(),
      };
    } catch (error) {
      console.error('Approve invoice error:', error);
      return { status: 'error', message: error instanceof Error ? error.message : 'Approval failed', invoiceId, approvedBy: '', approvedAt: '' };
    }
  }

  /**
   * Reject invoice
   */
  async rejectInvoice(
    invoiceId: string,
    userEmail: string,
    reason: string
  ): Promise<{ status: string; message: string; invoiceId: string; rejectedBy: string; rejectedAt: string }> {
    if (!this.bigquery) {
      return { status: 'error', message: 'Database not available', invoiceId, rejectedBy: '', rejectedAt: '' };
    }

    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
    const escapedReason = reason.replace(/'/g, "''");

    const query = `
      UPDATE \`${tableId}\`
      SET status = 'rejected',
          approval_status = 'rejected',
          rejected_by = '${userEmail}',
          rejected_at = CURRENT_TIMESTAMP(),
          rejection_reason = '${escapedReason}',
          updated_at = CURRENT_TIMESTAMP()
      WHERE invoice_id = '${invoiceId}'
    `;

    try {
      await this.bigquery.query({ query });
      return {
        status: 'success',
        message: 'Invoice rejected',
        invoiceId,
        rejectedBy: userEmail,
        rejectedAt: new Date().toISOString(),
      };
    } catch (error) {
      console.error('Reject invoice error:', error);
      return { status: 'error', message: error instanceof Error ? error.message : 'Rejection failed', invoiceId, rejectedBy: '', rejectedAt: '' };
    }
  }

  /**
   * Get signed URL for PDF download
   */
  async getDownloadUrl(invoiceId: string): Promise<string | null> {
    const invoice = await this.getInvoice(invoiceId);
    if (!invoice?.gcsPath || !this.bucket) return null;

    try {
      const file = this.bucket.file(invoice.gcsPath);
      const [url] = await file.getSignedUrl({
        version: 'v4',
        action: 'read',
        expires: Date.now() + 60 * 60 * 1000, // 1 hour
      });
      return url;
    } catch (error) {
      console.error('Download URL error:', error);
      return null;
    }
  }

  /**
   * Get summary statistics
   */
  async getSummaryStats(userEmail: string): Promise<InvoiceSummary> {
    if (!this.bigquery) return this.emptySummary();

    const tableId = `${this.projectId}.${this.datasetId}.invoices`;
    const query = `
      SELECT
        COUNT(CASE WHEN status = 'pending' THEN 1 END) as total_pending,
        COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) as total_due,
        COUNT(CASE WHEN status = 'pending' AND due_date < CURRENT_DATE() THEN 1 END) as overdue,
        COUNT(CASE WHEN status = 'pending' AND approval_status IS NULL THEN 1 END) as awaiting_approval,
        COALESCE(SUM(CASE WHEN status = 'paid' AND EXTRACT(MONTH FROM updated_at) = EXTRACT(MONTH FROM CURRENT_DATE()) THEN amount ELSE 0 END), 0) as paid_this_month,
        COUNT(CASE WHEN scheduled_date IS NOT NULL AND status = 'approved' THEN 1 END) as scheduled
      FROM \`${tableId}\`
      WHERE user_email = '${userEmail}'
    `;

    try {
      const [rows] = await this.bigquery.query({ query });
      const row = rows[0] || {};

      return {
        totalPending: row.total_pending || 0,
        totalDue: row.total_due || 0,
        overdue: row.overdue || 0,
        awaitingApproval: row.awaiting_approval || 0,
        paidThisMonth: row.paid_this_month || 0,
        scheduled: row.scheduled || 0,
      };
    } catch (error) {
      console.error('Summary stats error:', error);
      return this.emptySummary();
    }
  }

  /**
   * Get summary (wrapper)
   */
  async getSummary(userEmail: string): Promise<{ status: string; summary: InvoiceSummary }> {
    const summary = await this.getSummaryStats(userEmail);
    return { status: 'success', summary };
  }

  /**
   * Empty summary helper
   */
  private emptySummary(): InvoiceSummary {
    return {
      totalPending: 0,
      totalDue: 0,
      overdue: 0,
      awaitingApproval: 0,
      paidThisMonth: 0,
      scheduled: 0,
    };
  }
}

// Export default instance
export default InvoiceParserService;
