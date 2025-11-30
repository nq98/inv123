# BUILD INVOICE UPLOADER - COMPLETE IMPLEMENTATION PROMPT

## AI-SEMANTIC-FIRST Invoice Parser with 4-Layer Pipeline

---

## CORE PHILOSOPHY: AI-SEMANTIC-FIRST

This system uses **AI-Semantic-First** architecture - meaning AI reasoning and semantic understanding take priority over traditional rule-based extraction. The AI doesn't just OCR text; it **understands** the document like a human would.

### AI-Semantic-First Principles:

1. **Visual Supremacy** - Trust what the AI SEES over regex patterns
2. **Semantic Understanding** - AI interprets meaning, not just text
3. **Context Awareness** - Uses RAG for historical vendor patterns
4. **Multi-Language Native** - 40+ languages without configuration
5. **Self-Learning** - Improves from corrections via feedback loop
6. **Confidence Scoring** - AI reports how certain it is

### Why AI-Semantic-First?

Traditional invoice parsing uses regex patterns and templates. This fails when:
- Invoice formats vary (every vendor is different)
- Languages change (Hebrew, German, Chinese invoices)
- Amounts appear in multiple places (which is the TOTAL?)
- Dates use different formats (US vs EU vs ISO)

**AI-Semantic-First solves all of these** by having Gemini AI actually UNDERSTAND the invoice like a human accountant would.

---

## PROJECT OVERVIEW

Build an Invoice Management feature for the AP Automation tab that allows users to:
1. Upload single or bulk invoice PDFs
2. AI extracts all invoice data using 4-layer semantic pipeline
3. Store original PDFs in Google Cloud Storage
4. View PDFs via signed URLs (1-hour expiry)
5. Store extracted data in BigQuery
6. Approve/reject invoices with workflow
7. Detect payment types (Wire, ACH, Card, PayPal, Venmo, Crypto)
8. Export to CSV

---

## AVAILABLE SECRETS (Already Configured)

Use these exact secret names - they are already set up:

### Google Cloud Services
```
GOOGLE_CLOUD_PROJECT_ID          → Project ID
GCS_BUCKET_NAME                  → 'payouts-invoices' (invoice storage)
Processor_ID                     → Document AI processor ID
VERTEX_AI_SEARCH_COLLECTION_ID   → Vertex AI Search collection
VERTEX_AI_SEARCH_DATA_STORE_ID   → RAG datastore
GOOGLE_GEMINI_API_KEY            → Gemini 1.5 Pro API key
GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON → Service account (older format)
GOOGLE_APPLICATION_CREDENTIALS_JSON → Service account JSON
```

### AI Services
```
AI_INTEGRATIONS_GEMINI_BASE_URL  → Gemini base URL
AI_INTEGRATIONS_GEMINI_API_KEY   → Gemini via integrations
LANGCHAIN_API_KEY                → LangChain tracing
```

### Database
```
DATABASE_URL                     → PostgreSQL connection
PGDATABASE, PGHOST, PGPORT, PGUSER, PGPASSWORD → PostgreSQL details
```

---

## TECH STACK

```
Frontend:  React + TypeScript + Tailwind CSS
Backend:   Express + TypeScript
Database:  PostgreSQL (Drizzle ORM) + BigQuery
Storage:   Google Cloud Storage (GCS)
AI:        Document AI + Gemini 1.5 Pro + Vertex AI Search
```

---

## FILE STRUCTURE TO CREATE

```
server/
├── services/
│   ├── invoice-parser.service.ts    # Main 4-layer AI pipeline
│   ├── gcs.service.ts               # GCS upload + signed URLs
│   ├── document-ai.service.ts       # Document AI OCR
│   ├── gemini.service.ts            # Gemini semantic extraction
│   └── bigquery.service.ts          # BigQuery storage
├── routes/
│   └── invoice.routes.ts            # Express API routes
└── types/
    └── invoice.types.ts             # TypeScript interfaces

client/src/
├── components/invoices/
│   ├── InvoiceUpload.tsx            # Drag & drop upload
│   ├── InvoiceList.tsx              # Table with filters
│   ├── InvoiceDetail.tsx            # Detail view + approve/reject
│   └── PaymentTypeBadge.tsx         # Color-coded payment badges
└── pages/
    └── APAutomation.tsx             # Add invoices tab
```

---

## STEP 1: INSTALL PACKAGES

```bash
npm install @google-cloud/documentai @google-cloud/storage @google-cloud/bigquery
npm install @google/generative-ai multer uuid date-fns
npm install -D @types/multer @types/uuid
```

---

## STEP 2: TYPE DEFINITIONS

Create `server/types/invoice.types.ts`:

```typescript
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
  
  // AI
  extractionConfidence: number;
  rawExtraction: Record<string, unknown> | null;
  
  // User
  userEmail: string;
  createdAt: string;
  updatedAt: string;
}

export interface LineItem {
  description: string;
  quantity?: number;
  unitPrice?: number;
  amount: number;
}

export type Currency = 'USD' | 'EUR' | 'GBP' | 'CAD' | 'AUD' | 'JPY' | 'CNY' | 'INR' | 'ILS' | 'MXN' | 'BRL';
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
  description: string | null;
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

export interface ListInvoicesResponse {
  invoices: Invoice[];
  total: number;
  page: number;
  limit: number;
}
```

---

## STEP 3: GCS SERVICE (Upload + Signed URLs)

Create `server/services/gcs.service.ts`:

```typescript
import { Storage, Bucket } from '@google-cloud/storage';
import { format } from 'date-fns';

export class GCSService {
  private storage: Storage;
  private bucket: Bucket;
  private bucketName: string;
  
  constructor() {
    // Use secrets
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON 
      || process.env.GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON;
    const projectId = process.env.GOOGLE_CLOUD_PROJECT_ID;
    this.bucketName = process.env.GCS_BUCKET_NAME || 'payouts-invoices';
    
    const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
    
    this.storage = credentials
      ? new Storage({ credentials, projectId })
      : new Storage({ projectId });
    
    this.bucket = this.storage.bucket(this.bucketName);
    console.log(`✅ GCS initialized: ${this.bucketName}`);
  }
  
  /**
   * Upload invoice PDF to GCS
   * Returns: gs://payouts-invoices/invoices/{email}/{date}/{filename}
   */
  async uploadInvoice(
    buffer: Buffer,
    filename: string,
    userEmail: string,
    mimeType: string = 'application/pdf'
  ): Promise<string> {
    const datePath = format(new Date(), 'yyyy/MM/dd');
    const safeEmail = userEmail.replace('@', '_at_').replace(/\./g, '_');
    const uniqueFilename = `${Date.now()}_${filename}`;
    const gcsPath = `invoices/${safeEmail}/${datePath}/${uniqueFilename}`;
    
    const file = this.bucket.file(gcsPath);
    
    await file.save(buffer, {
      contentType: mimeType,
      metadata: {
        uploadedBy: userEmail,
        uploadedAt: new Date().toISOString(),
        originalFilename: filename,
      },
    });
    
    const gcsUri = `gs://${this.bucketName}/${gcsPath}`;
    console.log(`📤 Uploaded to GCS: ${gcsUri}`);
    return gcsUri;
  }
  
  /**
   * Generate signed URL for viewing/downloading PDF
   * Default: 1 hour expiry
   */
  async getSignedUrl(gcsUri: string, expirationSeconds: number = 3600): Promise<string> {
    // Parse gs://bucket/path format
    if (!gcsUri.startsWith('gs://')) {
      throw new Error('Invalid GCS URI format');
    }
    
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
    
    // Determine content type for proper viewing
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
    
    console.log(`🔗 Generated signed URL (expires in ${expirationSeconds}s)`);
    return url;
  }
}
```

---

## STEP 4: DOCUMENT AI SERVICE (Layer 1 - OCR)

Create `server/services/document-ai.service.ts`:

```typescript
import { DocumentProcessorServiceClient } from '@google-cloud/documentai';

interface DocumentAIResult {
  text: string;
  entities: Record<string, Array<{ value: string; confidence: number }>>;
  pages: number;
}

export class DocumentAIService {
  private client: DocumentProcessorServiceClient;
  private processorName: string;
  
  constructor() {
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON
      || process.env.GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON;
    const projectId = process.env.GOOGLE_CLOUD_PROJECT_ID;
    const processorId = process.env.Processor_ID;
    const location = 'us';
    
    const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
    
    this.client = credentials
      ? new DocumentProcessorServiceClient({ credentials })
      : new DocumentProcessorServiceClient();
    
    this.processorName = `projects/${projectId}/locations/${location}/processors/${processorId}`;
    console.log(`✅ Document AI initialized: ${processorId}`);
  }
  
  /**
   * LAYER 1: Extract text and entities using Document AI OCR
   */
  async processDocument(content: Buffer, mimeType: string): Promise<DocumentAIResult> {
    console.log('📄 LAYER 1: Document AI - OCR Extraction...');
    
    try {
      const [result] = await this.client.processDocument({
        name: this.processorName,
        rawDocument: {
          content: content.toString('base64'),
          mimeType,
        },
      });
      
      const document = result.document;
      if (!document) {
        console.warn('⚠️ Document AI returned empty result');
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
    } catch (error) {
      console.error('❌ Document AI error:', error);
      // Return empty result on error - Gemini will handle extraction
      return { text: '', entities: {}, pages: 0 };
    }
  }
}
```

---

## STEP 5: GEMINI SERVICE (Layer 3 - AI-SEMANTIC-FIRST Core)

**This is the HEART of AI-Semantic-First architecture.**

Gemini doesn't just extract text - it UNDERSTANDS the invoice semantically:
- Knows that "TOTAL" at the bottom is more important than line item amounts
- Understands that the company logo/header is the VENDOR
- Recognizes payment instructions in any language
- Detects Wire/ACH/PayPal/Crypto from contextual clues

Create `server/services/gemini.service.ts`:

```typescript
import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';
import { ExtractedInvoiceData, Currency, PaymentType } from '../types/invoice.types';

export class GeminiService {
  private model: GenerativeModel;
  
  constructor() {
    // Use secrets - try multiple sources
    const apiKey = process.env.GOOGLE_GEMINI_API_KEY 
      || process.env.AI_INTEGRATIONS_GEMINI_API_KEY;
    
    if (!apiKey) {
      throw new Error('Gemini API key not found');
    }
    
    const genAI = new GoogleGenerativeAI(apiKey);
    this.model = genAI.getGenerativeModel({ model: 'gemini-1.5-pro' });
    console.log('✅ Gemini AI initialized');
  }
  
  /**
   * LAYER 3: Semantic extraction using Gemini AI
   * AI-First approach with multi-language support
   */
  async extractInvoiceData(
    documentText: string,
    documentAIEntities: Record<string, any[]> = {},
    ragContext: string = ''
  ): Promise<ExtractedInvoiceData> {
    console.log('🧠 LAYER 3: Gemini AI - Semantic Extraction...');
    
    const prompt = `You are an expert invoice parser with AI-first semantic intelligence. Extract all invoice data from this document.

DOCUMENT TEXT:
${documentText.substring(0, 10000)}

${Object.keys(documentAIEntities).length > 0 ? `
DOCUMENT AI ENTITIES (for reference):
${JSON.stringify(documentAIEntities, null, 2).substring(0, 2000)}
` : ''}

${ragContext ? `HISTORICAL CONTEXT:\n${ragContext}` : ''}

## EXTRACTION RULES (AI-First Semantic Intelligence)

### Visual Supremacy
- Trust what you SEE in the document over patterns
- The largest/boldest amount is usually the TOTAL
- Company at TOP is usually the VENDOR (issuer)
- Company in "Bill To" is the BUYER (ignore for vendor name)

### Multi-Language Support
- Handle invoices in ANY language (40+ supported)
- Detect language automatically
- Parse dates in local formats

### Date Parsing (handle ALL formats)
- US: MM/DD/YYYY
- EU: DD/MM/YYYY or DD.MM.YYYY
- ISO: YYYY-MM-DD
- Written: "November 20, 2024", "20 Nov 2024", "20.11.2024"
- Return in ISO format: YYYY-MM-DD

### Currency Detection
- Look for symbols: $, €, £, ¥, ₪, ₹, R$
- Look for codes: USD, EUR, GBP, ILS, INR
- Default to USD if unclear

### Payment Type Detection (IMPORTANT)
Detect payment method from invoice text:
- **Wire**: Bank wire, SWIFT code, routing number, international transfer, "wire transfer"
- **ACH**: ACH transfer, direct debit, US bank account, "ACH payment"
- **Card**: Credit card, Visa, Mastercard, Amex, card number
- **PayPal**: PayPal email, paypal.me link, "pay via PayPal"
- **Venmo**: Venmo username, @venmo handle
- **Crypto**: Bitcoin, Ethereum, wallet address, BTC, ETH, crypto payment
- **Check**: Mail check, "send check to", check payment

### Line Items
- Extract each line item with description and amount
- Include quantity and unit price if visible

### Receipt vs Invoice
- Receipts: Past payment, "PAID", "Thank you for your payment"
- Invoices: Future payment, due date, "Please pay by"

## OUTPUT FORMAT

Return ONLY a valid JSON object with this exact structure:

{
    "vendorName": "Company Name (issuer of invoice)",
    "invoiceNumber": "INV-12345 or null",
    "invoiceDate": "YYYY-MM-DD or null",
    "dueDate": "YYYY-MM-DD or null",
    "amount": 1234.56,
    "subtotal": 1100.00,
    "taxAmount": 134.56,
    "currency": "USD",
    "paymentType": "Wire" | "ACH" | "Card" | "PayPal" | "Venmo" | "Crypto" | "Check" | null,
    "description": "Brief description of invoice",
    "lineItems": [
        {
            "description": "Item description",
            "quantity": 1,
            "unitPrice": 100.00,
            "amount": 100.00
        }
    ],
    "confidence": 0.95
}

CRITICAL: Return ONLY valid JSON. No markdown, no explanation, no code blocks.`;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      let text = response.text();
      
      // Clean JSON from response
      if (text.includes('```json')) {
        text = text.split('```json')[1].split('```')[0];
      } else if (text.includes('```')) {
        text = text.split('```')[1].split('```')[0];
      }
      
      // Remove any leading/trailing whitespace
      text = text.trim();
      
      // Try to find JSON object
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        text = jsonMatch[0];
      }
      
      const parsed = JSON.parse(text);
      
      console.log(`✅ Extracted: ${parsed.vendorName}`);
      console.log(`   Amount: ${parsed.currency} ${parsed.amount}`);
      console.log(`   Payment Type: ${parsed.paymentType || 'Not detected'}`);
      console.log(`   Confidence: ${(parsed.confidence * 100).toFixed(1)}%`);
      
      return parsed as ExtractedInvoiceData;
      
    } catch (error) {
      console.error('❌ Gemini extraction error:', error);
      throw new Error('Failed to extract invoice data from AI response');
    }
  }
}
```

---

## STEP 6: BIGQUERY SERVICE (Storage)

Create `server/services/bigquery.service.ts`:

```typescript
import { BigQuery } from '@google-cloud/bigquery';
import { Invoice, InvoiceStatus } from '../types/invoice.types';

export class BigQueryService {
  private client: BigQuery;
  private datasetId: string;
  private tableId: string;
  private fullTableId: string;
  
  constructor() {
    const credentialsJson = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON
      || process.env.GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON;
    const projectId = process.env.GOOGLE_CLOUD_PROJECT_ID;
    
    const credentials = credentialsJson ? JSON.parse(credentialsJson) : undefined;
    
    this.client = credentials
      ? new BigQuery({ credentials, projectId })
      : new BigQuery({ projectId });
    
    this.datasetId = 'vendors_ai';
    this.tableId = 'invoices';
    this.fullTableId = `${projectId}.${this.datasetId}.${this.tableId}`;
    
    console.log(`✅ BigQuery initialized: ${this.fullTableId}`);
  }
  
  /**
   * Ensure invoices table exists with correct schema
   */
  async ensureTable(): Promise<void> {
    const schema = [
      { name: 'invoice_id', type: 'STRING', mode: 'REQUIRED' },
      { name: 'invoice_number', type: 'STRING' },
      { name: 'vendor_name', type: 'STRING' },
      { name: 'vendor_id', type: 'STRING' },
      { name: 'amount', type: 'FLOAT64' },
      { name: 'currency', type: 'STRING' },
      { name: 'tax_amount', type: 'FLOAT64' },
      { name: 'subtotal', type: 'FLOAT64' },
      { name: 'invoice_date', type: 'DATE' },
      { name: 'due_date', type: 'DATE' },
      { name: 'payment_type', type: 'STRING' },
      { name: 'status', type: 'STRING' },
      { name: 'approved_by', type: 'STRING' },
      { name: 'approved_at', type: 'TIMESTAMP' },
      { name: 'rejected_by', type: 'STRING' },
      { name: 'rejected_at', type: 'TIMESTAMP' },
      { name: 'rejection_reason', type: 'STRING' },
      { name: 'gcs_uri', type: 'STRING' },
      { name: 'original_filename', type: 'STRING' },
      { name: 'extraction_confidence', type: 'FLOAT64' },
      { name: 'raw_extraction', type: 'JSON' },
      { name: 'user_email', type: 'STRING' },
      { name: 'created_at', type: 'TIMESTAMP' },
      { name: 'updated_at', type: 'TIMESTAMP' },
    ];
    
    try {
      await this.client.dataset(this.datasetId).table(this.tableId).get();
      console.log(`✅ Table ${this.tableId} exists`);
    } catch (error: any) {
      if (error.code === 404) {
        console.log(`📝 Creating table ${this.tableId}...`);
        await this.client.dataset(this.datasetId).createTable(this.tableId, { schema });
        console.log(`✅ Created table ${this.tableId}`);
      } else {
        throw error;
      }
    }
  }
  
  /**
   * Insert new invoice
   */
  async insertInvoice(invoice: Partial<Invoice>): Promise<void> {
    await this.ensureTable();
    
    const row = {
      invoice_id: invoice.invoiceId,
      invoice_number: invoice.invoiceNumber || null,
      vendor_name: invoice.vendorName,
      vendor_id: invoice.vendorId || null,
      amount: invoice.amount,
      currency: invoice.currency || 'USD',
      tax_amount: invoice.taxAmount || null,
      subtotal: invoice.subtotal || null,
      invoice_date: invoice.invoiceDate || null,
      due_date: invoice.dueDate || null,
      payment_type: invoice.paymentType || null,
      status: invoice.status || 'pending',
      gcs_uri: invoice.gcsUri,
      original_filename: invoice.originalFilename,
      extraction_confidence: invoice.extractionConfidence || 0,
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
    userEmail?: string,
    options: {
      page?: number;
      limit?: number;
      status?: InvoiceStatus;
      paymentType?: string;
      search?: string;
      sortBy?: string;
      sortOrder?: 'asc' | 'desc';
    } = {}
  ): Promise<{ invoices: any[]; total: number }> {
    const { 
      page = 1, 
      limit = 50, 
      status, 
      paymentType,
      search,
      sortBy = 'created_at',
      sortOrder = 'desc'
    } = options;
    
    const offset = (page - 1) * limit;
    
    let whereClause = 'WHERE 1=1';
    const params: Record<string, any> = {};
    
    if (userEmail) {
      whereClause += ' AND user_email = @userEmail';
      params.userEmail = userEmail;
    }
    if (status) {
      whereClause += ' AND status = @status';
      params.status = status;
    }
    if (paymentType) {
      whereClause += ' AND payment_type = @paymentType';
      params.paymentType = paymentType;
    }
    if (search) {
      whereClause += ' AND (LOWER(vendor_name) LIKE @search OR LOWER(invoice_number) LIKE @search)';
      params.search = `%${search.toLowerCase()}%`;
    }
    
    // Validate sort column
    const validSortColumns = ['created_at', 'invoice_date', 'amount', 'vendor_name', 'status'];
    const safeSort = validSortColumns.includes(sortBy) ? sortBy : 'created_at';
    const safeOrder = sortOrder === 'asc' ? 'ASC' : 'DESC';
    
    const query = `
      SELECT * FROM \`${this.fullTableId}\`
      ${whereClause}
      ORDER BY ${safeSort} ${safeOrder}
      LIMIT ${limit} OFFSET ${offset}
    `;
    
    const [rows] = await this.client.query({ query, params });
    
    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total FROM \`${this.fullTableId}\`
      ${whereClause}
    `;
    const [countRows] = await this.client.query({ query: countQuery, params });
    
    return {
      invoices: rows,
      total: Number(countRows[0]?.total) || 0,
    };
  }
  
  /**
   * Get single invoice
   */
  async getInvoice(invoiceId: string): Promise<any | null> {
    const query = `
      SELECT * FROM \`${this.fullTableId}\`
      WHERE invoice_id = @invoiceId
      LIMIT 1
    `;
    
    const [rows] = await this.client.query({ query, params: { invoiceId } });
    return rows.length > 0 ? rows[0] : null;
  }
  
  /**
   * Approve invoice
   */
  async approveInvoice(invoiceId: string, userEmail: string): Promise<void> {
    const query = `
      UPDATE \`${this.fullTableId}\`
      SET 
        status = 'approved',
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
      SET 
        status = 'rejected',
        rejected_by = @userEmail,
        rejected_at = CURRENT_TIMESTAMP(),
        rejection_reason = @reason,
        updated_at = CURRENT_TIMESTAMP()
      WHERE invoice_id = @invoiceId
    `;
    
    await this.client.query({ query, params: { invoiceId, userEmail, reason } });
    console.log(`❌ Rejected invoice ${invoiceId}: ${reason}`);
  }
  
  /**
   * Get summary statistics
   */
  async getSummary(userEmail?: string): Promise<any> {
    let whereClause = 'WHERE 1=1';
    const params: Record<string, any> = {};
    
    if (userEmail) {
      whereClause += ' AND user_email = @userEmail';
      params.userEmail = userEmail;
    }
    
    const query = `
      SELECT
        COUNT(*) as total,
        COUNTIF(status = 'pending') as pending,
        COUNTIF(status = 'approved') as approved,
        COUNTIF(status = 'rejected') as rejected,
        COUNTIF(status = 'paid') as paid,
        SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) as pending_amount,
        SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END) as approved_amount
      FROM \`${this.fullTableId}\`
      ${whereClause}
    `;
    
    const [rows] = await this.client.query({ query, params });
    return rows[0] || {};
  }
}
```

---

## STEP 7: INVOICE PARSER SERVICE (Main Pipeline)

Create `server/services/invoice-parser.service.ts`:

```typescript
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
   * 
   * Layer 1: Document AI OCR
   * Layer 2: RAG Context (optional)
   * Layer 3: Gemini Semantic Extraction
   * Layer 4: Validation
   */
  async parseInvoice(
    buffer: Buffer,
    filename: string,
    mimeType: string,
    userEmail: string
  ): Promise<UploadResponse> {
    const invoiceId = this.generateInvoiceId();
    
    console.log(`\n${'='.repeat(60)}`);
    console.log(`🧾 PROCESSING INVOICE: ${filename}`);
    console.log(`   Invoice ID: ${invoiceId}`);
    console.log(`   User: ${userEmail}`);
    console.log(`${'='.repeat(60)}\n`);
    
    try {
      // LAYER 0: Upload to GCS
      console.log('📤 Uploading to Google Cloud Storage...');
      const gcsUri = await this.gcsService.uploadInvoice(buffer, filename, userEmail, mimeType);
      
      // LAYER 1: Document AI OCR
      const docAIResult = await this.docAIService.processDocument(buffer, mimeType);
      
      // LAYER 2: RAG Context (optional - add Vertex AI Search here)
      const ragContext = ''; // TODO: Add historical context from Vertex AI Search
      
      // LAYER 3: Gemini Semantic Extraction
      const extractedData = await this.geminiService.extractInvoiceData(
        docAIResult.text,
        docAIResult.entities,
        ragContext
      );
      
      // LAYER 4: Validation
      console.log('✅ LAYER 4: Validation...');
      const validatedData = this.validateExtraction(extractedData);
      
      // Store in BigQuery
      console.log('💾 Storing in BigQuery...');
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
      console.log(`   Invoice ID: ${invoiceId}`);
      console.log(`   Vendor: ${validatedData.vendorName}`);
      console.log(`   Amount: ${validatedData.currency} ${validatedData.amount}`);
      console.log(`   Payment Type: ${validatedData.paymentType || 'Not detected'}`);
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
   * Bulk upload multiple invoices
   */
  async parseInvoicesBulk(
    files: Array<{ buffer: Buffer; filename: string; mimeType: string }>,
    userEmail: string
  ): Promise<{
    status: 'success' | 'error';
    total: number;
    processed: number;
    failed: number;
    results: UploadResponse[];
  }> {
    console.log(`\n📦 BULK UPLOAD: ${files.length} files\n`);
    
    const results: UploadResponse[] = [];
    let processed = 0;
    let failed = 0;
    
    for (const file of files) {
      try {
        const result = await this.parseInvoice(
          file.buffer,
          file.filename,
          file.mimeType,
          userEmail
        );
        results.push(result);
        
        if (result.status === 'success') {
          processed++;
        } else {
          failed++;
        }
      } catch (error) {
        failed++;
        results.push({
          status: 'error',
          invoiceId: '',
          error: error instanceof Error ? error.message : 'Unknown error',
        });
      }
    }
    
    return {
      status: failed === files.length ? 'error' : 'success',
      total: files.length,
      processed,
      failed,
      results,
    };
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
  private validateExtraction(extracted: ExtractedInvoiceData): ExtractedInvoiceData {
    // Math validation: subtotal + tax should equal total
    if (extracted.subtotal && extracted.taxAmount) {
      const calculated = extracted.subtotal + extracted.taxAmount;
      const difference = Math.abs(calculated - extracted.amount);
      
      if (difference > 0.01) {
        console.warn(`⚠️ Math mismatch: ${extracted.subtotal} + ${extracted.taxAmount} = ${calculated} (expected ${extracted.amount})`);
      } else {
        console.log('✅ Math validation passed');
      }
    }
    
    // Ensure confidence is between 0 and 1
    extracted.confidence = Math.max(0, Math.min(1, extracted.confidence || 0.5));
    
    return extracted;
  }
  
  /**
   * Get signed URL for invoice download
   */
  async getDownloadUrl(invoiceId: string): Promise<string | null> {
    const invoice = await this.bigqueryService.getInvoice(invoiceId);
    if (!invoice?.gcs_uri) {
      console.warn(`Invoice ${invoiceId} not found or has no GCS URI`);
      return null;
    }
    return this.gcsService.getSignedUrl(invoice.gcs_uri);
  }
  
  /**
   * List invoices
   */
  async listInvoices(userEmail?: string, options?: any) {
    return this.bigqueryService.listInvoices(userEmail, options);
  }
  
  /**
   * Get single invoice
   */
  async getInvoice(invoiceId: string) {
    return this.bigqueryService.getInvoice(invoiceId);
  }
  
  /**
   * Approve invoice
   */
  async approveInvoice(invoiceId: string, userEmail: string) {
    await this.bigqueryService.approveInvoice(invoiceId, userEmail);
    return { status: 'success', message: 'Invoice approved', invoiceId };
  }
  
  /**
   * Reject invoice
   */
  async rejectInvoice(invoiceId: string, userEmail: string, reason: string) {
    await this.bigqueryService.rejectInvoice(invoiceId, userEmail, reason);
    return { status: 'success', message: 'Invoice rejected', invoiceId };
  }
  
  /**
   * Get summary statistics
   */
  async getSummary(userEmail?: string) {
    return this.bigqueryService.getSummary(userEmail);
  }
}
```

---

## STEP 8: EXPRESS API ROUTES

Create `server/routes/invoice.routes.ts`:

```typescript
import { Router, Request, Response } from 'express';
import multer from 'multer';
import { format } from 'date-fns';
import { InvoiceParserService } from '../services/invoice-parser.service';

const router = Router();
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 } // 50MB limit
});

const invoiceService = new InvoiceParserService();

// Helper to get user email from request
const getUserEmail = (req: Request): string => {
  return (req as any).user?.email || req.headers['x-user-email'] as string || 'unknown@example.com';
};

/**
 * POST /api/invoices/upload
 * Upload and parse single invoice PDF
 */
router.post('/upload', upload.single('file'), async (req: Request, res: Response) => {
  try {
    const file = req.file;
    
    if (!file) {
      return res.status(400).json({ status: 'error', message: 'No file provided' });
    }
    
    // Validate file type
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.mimetype)) {
      return res.status(400).json({ 
        status: 'error', 
        message: 'Invalid file type. Allowed: PDF, PNG, JPG' 
      });
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
    console.error('Upload error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: error instanceof Error ? error.message : 'Upload failed' 
    });
  }
});

/**
 * POST /api/invoices/upload/bulk
 * Upload and parse multiple invoice PDFs
 */
router.post('/upload/bulk', upload.array('files[]', 50), async (req: Request, res: Response) => {
  try {
    const files = req.files as Express.Multer.File[];
    
    if (!files || files.length === 0) {
      return res.status(400).json({ status: 'error', message: 'No files provided' });
    }
    
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    const validFiles = files
      .filter(f => allowedTypes.includes(f.mimetype))
      .map(f => ({
        buffer: f.buffer,
        filename: f.originalname,
        mimeType: f.mimetype,
      }));
    
    if (validFiles.length === 0) {
      return res.status(400).json({ status: 'error', message: 'No valid files provided' });
    }
    
    const userEmail = getUserEmail(req);
    const result = await invoiceService.parseInvoicesBulk(validFiles, userEmail);
    
    res.json(result);
    
  } catch (error) {
    console.error('Bulk upload error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: error instanceof Error ? error.message : 'Bulk upload failed' 
    });
  }
});

/**
 * GET /api/invoices
 * List invoices with filters and pagination
 */
router.get('/', async (req: Request, res: Response) => {
  try {
    const userEmail = getUserEmail(req);
    
    const result = await invoiceService.listInvoices(userEmail, {
      page: parseInt(req.query.page as string) || 1,
      limit: parseInt(req.query.limit as string) || 50,
      status: req.query.status as any,
      paymentType: req.query.paymentType as string,
      search: req.query.search as string,
      sortBy: req.query.sortBy as string,
      sortOrder: req.query.sortOrder as 'asc' | 'desc',
    });
    
    res.json({
      status: 'success',
      ...result,
      page: parseInt(req.query.page as string) || 1,
      limit: parseInt(req.query.limit as string) || 50,
    });
    
  } catch (error) {
    console.error('List invoices error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to list invoices' 
    });
  }
});

/**
 * GET /api/invoices/summary
 * Get invoice summary statistics
 */
router.get('/summary', async (req: Request, res: Response) => {
  try {
    const userEmail = getUserEmail(req);
    const summary = await invoiceService.getSummary(userEmail);
    
    res.json({
      status: 'success',
      summary,
    });
    
  } catch (error) {
    console.error('Summary error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to get summary' 
    });
  }
});

/**
 * GET /api/invoices/export
 * Export invoices to CSV
 */
router.get('/export', async (req: Request, res: Response) => {
  try {
    const userEmail = getUserEmail(req);
    
    const { invoices } = await invoiceService.listInvoices(userEmail, {
      limit: 10000,
      status: req.query.status as any,
    });
    
    // Build CSV
    const headers = [
      'Invoice ID', 'Invoice Number', 'Vendor', 'Amount', 'Currency',
      'Invoice Date', 'Due Date', 'Status', 'Payment Type', 'Created'
    ];
    
    const rows = invoices.map((inv: any) => [
      inv.invoice_id,
      inv.invoice_number || '',
      (inv.vendor_name || '').replace(/,/g, ';'),
      inv.amount,
      inv.currency,
      inv.invoice_date || '',
      inv.due_date || '',
      inv.status,
      inv.payment_type || '',
      inv.created_at,
    ]);
    
    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const filename = `invoices_${format(new Date(), 'yyyyMMdd')}.csv`;
    
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename=${filename}`);
    res.send(csv);
    
  } catch (error) {
    console.error('Export error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Export failed' 
    });
  }
});

/**
 * GET /api/invoices/:invoiceId
 * Get single invoice details
 */
router.get('/:invoiceId', async (req: Request, res: Response) => {
  try {
    const { invoiceId } = req.params;
    const invoice = await invoiceService.getInvoice(invoiceId);
    
    if (!invoice) {
      return res.status(404).json({ status: 'error', message: 'Invoice not found' });
    }
    
    // Get download URL
    let downloadUrl = null;
    if (invoice.gcs_uri) {
      try {
        downloadUrl = await invoiceService.getDownloadUrl(invoiceId);
      } catch (e) {
        console.warn('Could not generate download URL:', e);
      }
    }
    
    res.json({
      status: 'success',
      invoice: {
        ...invoice,
        downloadUrl,
      },
    });
    
  } catch (error) {
    console.error('Get invoice error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to get invoice' 
    });
  }
});

/**
 * GET /api/invoices/:invoiceId/download
 * Get signed URL for PDF download
 */
router.get('/:invoiceId/download', async (req: Request, res: Response) => {
  try {
    const { invoiceId } = req.params;
    const url = await invoiceService.getDownloadUrl(invoiceId);
    
    if (!url) {
      return res.status(404).json({ status: 'error', message: 'PDF not found' });
    }
    
    res.json({
      status: 'success',
      downloadUrl: url,
      expiresIn: 3600,
    });
    
  } catch (error) {
    console.error('Download error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to get download URL' 
    });
  }
});

/**
 * POST /api/invoices/:invoiceId/approve
 * Approve invoice for payment
 */
router.post('/:invoiceId/approve', async (req: Request, res: Response) => {
  try {
    const { invoiceId } = req.params;
    const userEmail = getUserEmail(req);
    
    const result = await invoiceService.approveInvoice(invoiceId, userEmail);
    res.json(result);
    
  } catch (error) {
    console.error('Approve error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to approve invoice' 
    });
  }
});

/**
 * POST /api/invoices/:invoiceId/reject
 * Reject invoice
 */
router.post('/:invoiceId/reject', async (req: Request, res: Response) => {
  try {
    const { invoiceId } = req.params;
    const { reason } = req.body;
    
    if (!reason) {
      return res.status(400).json({ status: 'error', message: 'Rejection reason required' });
    }
    
    const userEmail = getUserEmail(req);
    const result = await invoiceService.rejectInvoice(invoiceId, userEmail, reason);
    res.json(result);
    
  } catch (error) {
    console.error('Reject error:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Failed to reject invoice' 
    });
  }
});

export default router;
```

---

## STEP 9: REGISTER ROUTES

In your main Express app (e.g., `server/index.ts`):

```typescript
import invoiceRoutes from './routes/invoice.routes';

// Register invoice routes
app.use('/api/invoices', invoiceRoutes);
```

---

## STEP 10: FRONTEND - INVOICE UPLOAD COMPONENT

Create `client/src/components/invoices/InvoiceUpload.tsx`:

```tsx
import React, { useState, useCallback } from 'react';

interface UploadResult {
  status: 'success' | 'error';
  invoiceId?: string;
  extractedData?: {
    vendorName: string;
    amount: number;
    currency: string;
    paymentType?: string;
  };
  downloadUrl?: string;
  confidence?: number;
  error?: string;
}

export const InvoiceUpload: React.FC = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState<UploadResult | null>(null);
  
  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      await uploadFiles(files);
    }
  }, []);
  
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await uploadFiles(Array.from(files));
    }
  };
  
  const uploadFiles = async (files: File[]) => {
    setIsUploading(true);
    setResult(null);
    
    try {
      if (files.length === 1) {
        // Single file upload
        setProgress('Uploading invoice...');
        const formData = new FormData();
        formData.append('file', files[0]);
        
        setProgress('AI is extracting invoice data...');
        const response = await fetch('/api/invoices/upload', {
          method: 'POST',
          body: formData,
        });
        
        const data = await response.json();
        setResult(data);
        
      } else {
        // Bulk upload
        setProgress(`Uploading ${files.length} invoices...`);
        const formData = new FormData();
        files.forEach(file => formData.append('files[]', file));
        
        const response = await fetch('/api/invoices/upload/bulk', {
          method: 'POST',
          body: formData,
        });
        
        const data = await response.json();
        setResult({
          status: data.status,
          extractedData: {
            vendorName: `${data.processed} of ${data.total} processed`,
            amount: 0,
            currency: '',
          },
        });
      }
    } catch (error) {
      setResult({ status: 'error', error: 'Upload failed' });
    } finally {
      setIsUploading(false);
      setProgress('');
    }
  };
  
  const getPaymentTypeBadge = (type?: string) => {
    const colors: Record<string, string> = {
      Wire: 'bg-blue-100 text-blue-800',
      ACH: 'bg-green-100 text-green-800',
      Card: 'bg-purple-100 text-purple-800',
      PayPal: 'bg-indigo-100 text-indigo-800',
      Venmo: 'bg-teal-100 text-teal-800',
      Crypto: 'bg-orange-100 text-orange-800',
      Check: 'bg-gray-100 text-gray-800',
    };
    
    if (!type) return null;
    
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors[type] || 'bg-gray-100'}`}>
        {type}
      </span>
    );
  };
  
  return (
    <div className="p-6">
      <h2 className="text-xl font-semibold mb-4">Upload Invoice</h2>
      
      {/* Drop Zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <div className="text-4xl mb-4">📄</div>
        <p className="text-lg font-medium mb-2">
          Drag & drop invoice PDFs here
        </p>
        <p className="text-gray-500 mb-4">or</p>
        <label className="cursor-pointer bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600">
          Select Files
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
        </label>
        <p className="text-sm text-gray-400 mt-4">
          Supports PDF, PNG, JPG (max 50MB each)
        </p>
      </div>
      
      {/* Progress */}
      {isUploading && (
        <div className="mt-6 p-4 bg-blue-50 rounded-lg">
          <div className="flex items-center">
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 border-t-transparent mr-3"></div>
            <span>{progress}</span>
          </div>
        </div>
      )}
      
      {/* Result */}
      {result && (
        <div className={`mt-6 p-4 rounded-lg ${
          result.status === 'success' ? 'bg-green-50' : 'bg-red-50'
        }`}>
          {result.status === 'success' ? (
            <div>
              <div className="flex items-center mb-2">
                <span className="text-green-600 text-xl mr-2">✓</span>
                <span className="font-medium">Invoice Parsed Successfully</span>
              </div>
              <div className="ml-7 space-y-1 text-sm">
                <p><strong>Vendor:</strong> {result.extractedData?.vendorName}</p>
                <p>
                  <strong>Amount:</strong> {result.extractedData?.currency} {result.extractedData?.amount?.toLocaleString()}
                </p>
                {result.extractedData?.paymentType && (
                  <p>
                    <strong>Payment Type:</strong> {getPaymentTypeBadge(result.extractedData.paymentType)}
                  </p>
                )}
                <p><strong>Confidence:</strong> {((result.confidence || 0) * 100).toFixed(1)}%</p>
                {result.downloadUrl && (
                  <a 
                    href={result.downloadUrl} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    📄 View PDF
                  </a>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center">
              <span className="text-red-600 text-xl mr-2">✗</span>
              <span>{result.error || 'Upload failed'}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

---

## COMPLETE FLOW DIAGRAM - AI-SEMANTIC-FIRST PIPELINE

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI-SEMANTIC-FIRST                            │
│   "The AI understands invoices like a human accountant would"       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    USER UPLOADS PDF                                  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 0: Google Cloud Storage                                      │
│  ────────────────────────────────                                   │
│  • Upload PDF to gs://payouts-invoices/invoices/{email}/{date}/     │
│  • Store original file permanently                                   │
│  • Return gcsUri for later retrieval                                │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Document AI (OCR)                                         │
│  ──────────────────────────                                         │
│  • Extract all text from PDF                                        │
│  • Detect tables and structure                                      │
│  • Extract entities (dates, amounts, etc.)                          │
│  • Uses: Processor_ID secret                                        │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: Vertex AI Search (RAG) - Optional                         │
│  ──────────────────────────────────────────                         │
│  • Query historical invoice patterns                                │
│  • Get vendor history and typical values                            │
│  • Uses: VERTEX_AI_SEARCH_DATA_STORE_ID                             │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: Gemini AI (Semantic Extraction)                           │
│  ────────────────────────────────────────                           │
│  • AI-first semantic understanding                                  │
│  • Multi-language support (40+ languages)                           │
│  • Extract: vendor, amount, dates, line items                       │
│  • Detect payment type: Wire, ACH, Card, PayPal, Venmo, Crypto     │
│  • Uses: GOOGLE_GEMINI_API_KEY                                      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: Validation                                                │
│  ───────────────────                                                │
│  • Math check: subtotal + tax = total                               │
│  • Date format validation                                           │
│  • Confidence scoring                                               │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STORAGE: BigQuery                                                   │
│  ────────────────────                                               │
│  • Store extracted data in vendors_ai.invoices table                │
│  • Link to GCS via gcs_uri column                                   │
│  • Track status: pending → approved/rejected → paid                 │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RESPONSE TO FRONTEND                                                │
│  ────────────────────                                               │
│  • invoiceId                                                        │
│  • extractedData (vendor, amount, dates, payment type)              │
│  • downloadUrl (signed URL to view PDF - 1 hour expiry)             │
│  • confidence score                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## IMPLEMENTATION CHECKLIST

- [ ] Install npm packages
- [ ] Create `server/types/invoice.types.ts`
- [ ] Create `server/services/gcs.service.ts`
- [ ] Create `server/services/document-ai.service.ts`
- [ ] Create `server/services/gemini.service.ts`
- [ ] Create `server/services/bigquery.service.ts`
- [ ] Create `server/services/invoice-parser.service.ts`
- [ ] Create `server/routes/invoice.routes.ts`
- [ ] Register routes in Express app
- [ ] Create `client/src/components/invoices/InvoiceUpload.tsx`
- [ ] Create `client/src/components/invoices/InvoiceList.tsx`
- [ ] Add to AP Automation tab
- [ ] Test single upload
- [ ] Test bulk upload
- [ ] Test PDF viewing via signed URL
- [ ] Test approve/reject workflow
- [ ] Test CSV export

---

## START NOW

Begin with Step 1 (install packages), then proceed step by step. The 4-layer AI pipeline will automatically:
1. Store PDFs in Google Cloud Storage
2. Extract text with Document AI
3. Parse with Gemini AI (semantic understanding)
4. Store in BigQuery
5. Provide signed URLs for PDF viewing

All secrets are already configured - just use the exact variable names shown above.
