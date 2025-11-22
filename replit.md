# Enterprise Invoice Extraction System

## Overview
Enterprise invoice extraction and vendor management system with AI-First semantic intelligence:

### Invoice Processing (3-Layer Hybrid Architecture with Self-Learning RAG)
- **Layer 1**: Google Document AI for layout/structure extraction
- **Layer 2**: Vertex AI Search (RAG) for vendor context AND past invoice extraction retrieval (self-learning)
- **Layer 3**: Gemini 1.5 Pro for semantic validation with historical context
- **Feedback Loop**: Successful extractions (confidence > 0.7) automatically stored to RAG knowledge base

### Vendor Database Management (AI-Powered CSV Import with RAG)
- **Self-Improving Universal CSV Mapper**: Gemini AI + Vertex AI Search RAG analyzes ANY vendor CSV (SAP, Oracle, QuickBooks, Excel) and automatically maps columns to standardized schema
- **Vertex AI Search RAG Knowledge Base**: Stores successful mappings and retrieves similar past mappings to improve accuracy over time (zero-shot → few-shot → many-shot learning)
- **Multi-Language Support**: Handles German (Firma_Name), Spanish (Empresa), Hebrew (ספק), and 40+ languages
- **Smart Deduplication**: BigQuery MERGE operations prevent duplicates
- **Dynamic Schema**: Custom CSV columns stored in JSON field for flexibility

## Architecture

### Invoice Extraction Pipeline (Self-Improving with RAG)
1. **Document AI Invoice Processor** - Extracts structured data with bounding boxes and confidence scores
2. **Vertex AI Search (RAG)** - Dual lookup: (a) Vendor history and canonical IDs, (b) Similar past invoice extractions
3. **Gemini 1.5 Pro** - Semantic reasoning with historical context from past successful extractions
4. **Feedback Loop** - Store successful extraction to RAG knowledge base for future learning

### Vendor Management Pipeline (with RAG Learning Loop)
1. **Vertex AI Search RAG Query** - Search for similar CSV mappings from past uploads
2. **CSV Upload & Analysis** - AI analyzes headers with historical context to understand schema
3. **Chain of Thought Mapping** - Gemini explains WHY each column maps to which field, using past successful mappings
4. **Data Transformation** - Normalizes emails, countries, domains into arrays
5. **BigQuery Merge** - Smart deduplication using MERGE operations on vendor_id
6. **Feedback Loop** - Store successful mappings back to Vertex AI Search for future learning

## Project Structure
```
/
├── app.py                      # Flask API server with invoice & vendor endpoints
├── config.py                   # Configuration and environment setup
├── invoice_processor.py        # Main invoice processing pipeline
├── services/
│   ├── document_ai_service.py          # Document AI integration
│   ├── vertex_search_service.py        # Vertex AI Search (RAG) for invoices
│   ├── vertex_vendor_mapping_search.py # Vertex AI Search (RAG) for vendor CSV mappings
│   ├── gemini_service.py               # Gemini semantic validation (invoices)
│   ├── vendor_csv_mapper.py            # AI-powered CSV column mapping with RAG
│   ├── bigquery_service.py             # BigQuery vendor database operations
│   ├── gmail_service.py                # Gmail OAuth & invoice import
│   └── token_storage.py                # Secure OAuth token management
├── utils/
│   ├── date_normalizer.py      # Global date format handling
│   ├── vendor_extractor.py     # Vendor name extraction
│   └── result_formatter.py     # Result formatting utilities
└── templates/
    └── index.html              # Web UI for uploads & Gmail scanning

## Google Cloud Configuration
- **Project ID**: invoicereader-477008
- **GCS Bucket**: payouts-invoices
- **Document AI Processor**: 919c19aabdb1802d (us region)
- **Vertex Search Datastore (Invoice RAG)**: invoices-ds
- **Vertex Search Datastore (Vendor Mapping RAG)**: vendor_csv_mappings
- **BigQuery Dataset**: vendors_ai
- **BigQuery Table**: global_vendors (vendor master data with dynamic custom_attributes JSON column)
- **Service Accounts**: 
  - `vertex-runner` for Vertex AI Search, Gemini, and BigQuery
  - `documentai-access` for Document AI

## Environment Variables
See `.env` for required configuration including API keys, processor IDs, and service account paths.

## Recent Changes
- 2025-11-22: **BREAKTHROUGH: Self-Improving Invoice Extraction with Vertex AI Search RAG** - Enhanced 3-layer pipeline with learning system:
  - Enhanced Vertex AI Search to store successful invoice extractions to knowledge base
  - Added dual RAG lookup in Layer 2: vendor info + similar past invoice extractions
  - Modified Gemini prompt to include historical context from past successful extractions
  - Implemented feedback loop: extractions with confidence > 0.7 automatically stored to RAG
  - System learns from each invoice: improves accuracy for familiar vendors and document patterns
  - Stores metadata: vendor name, document type, currency, confidence score, line items, totals
  - RAG context shows past extraction examples to maintain consistency and improve accuracy
  - **Benefits for Gmail scanning**: Dramatically reduced false positives (junk) and false negatives (missed invoices)
  - Non-blocking design: extraction continues even if RAG storage fails
- 2025-11-22: **BREAKTHROUGH: Self-Improving Vendor CSV Mapping with Vertex AI Search RAG** - Implemented learning system for vendor CSV import:
  - Created Vertex AI Search datastore `vendor_csv_mappings` as knowledge base for past successful mappings
  - Enhanced VendorCSVMapper to query RAG before analysis (retrieves top 3 similar past mappings)
  - Modified Gemini prompt to include historical context with proven column mappings
  - Implemented feedback loop: successful imports are stored back to Vertex AI Search
  - System now learns from each upload: zero-shot → few-shot → many-shot learning capability
  - Each stored mapping includes: CSV fingerprint, detected language, source system, confidence scores, upload count, success rate
  - RAG context shows past mappings with example column assignments to improve future accuracy
  - New service: `services/vertex_vendor_mapping_search.py` for RAG operations
  - Integration points: `vendor_csv_mapper.py` (query RAG + store mappings), `app.py` (trigger feedback loop after import)
- 2025-11-22: **NEW FEATURE: Universal AI Vendor CSV Import** - Built complete vendor management system:
  - AI-First CSV column mapping with Chain of Thought reasoning (Gemini 2.0 Flash)
  - Multi-language support (German Firma_Name, Spanish Empresa, Hebrew ספק, 40+ languages)
  - Semantic column understanding (not just keyword matching)
  - BigQuery integration with smart deduplication (MERGE operations on vendor_id)
  - Dynamic schema support (custom_attributes JSON column for proprietary fields)
  - 2-step process: Analyze CSV → Review AI mapping → Import to BigQuery
  - Confidence scoring for each column mapping
  - API endpoints: /api/vendors/csv/analyze, /api/vendors/csv/import, /api/vendors/search
- 2025-11-22: **MAJOR UPGRADE: AI-First Semantic Intelligence** - Completely overhauled Gemini extraction prompt:
  - Implemented Chain of Thought reasoning (auditReasoning field forces AI to explain decisions BEFORE extraction)
  - Added visual supremacy protocol: Image pixels > OCR text (critical for RTL languages)
  - Enhanced RTL language support (Hebrew/Arabic): Auto-detection and correction of reversed OCR text
  - Superior date logic: Distinguishes documentDate vs paymentDate vs dueDate (critical for receipts)
  - Receipt vs Invoice classification: "Request for payment" vs "Proof of payment" logic
  - Subscription detection: servicePeriodStart/End date extraction
  - Global date format resolution: MM/DD vs DD/MM based on vendor country context
  - Enhanced vendor matching with RAG database context and reasoning
  - Mathematical verification with detailed warning flags
  - Added new fields: auditReasoning, isRTL, isSubscription, detectedCountry, paymentDate, servicePeriodStart/End
  - Backward compatibility maintained for legacy field names (issueDate, reasoning)
- 2025-11-22: **Fixed SSE Connection Timeout** - Switched from Flask dev server to Gunicorn with gevent async workers, 300s timeout, and proper SSE headers for long-running AI processing
- 2025-11-22: **CRITICAL OAuth Fix** - Applied comprehensive Replit-specific OAuth configuration to prevent "State mismatch" errors:
  - Set static SECRET_KEY (removed os.urandom() fallback) to survive server restarts across Gunicorn workers
  - Added OAUTHLIB_INSECURE_TRANSPORT='1' for Replit's HTTP/HTTPS proxy compatibility
  - Implemented ProxyFix middleware (x_proto=1, x_host=1) to handle HTTP/HTTPS confusion on Replit's internal routing
  - Configured SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='None' for secure iframe/proxy cookie handling
  - Set PERMANENT_SESSION_LIFETIME=300 (5 minutes) for OAuth session timeout
  - Implemented dynamic redirect URI detection to automatically use correct URLs for dev vs production environments
  - Google Cloud Console configured with both dev and production authorized JavaScript origins and redirect URIs
- 2025-11-22: Enhanced invoice display to show ALL semantic data (vendor info, buyer info, payment terms, financial breakdown, line items with tax, AI reasoning, confidence scores)
- 2025-11-22: Fixed field access bug (camelCase vs snake_case) in Gemini response parsing
- 2025-11-21: Initial project setup with hybrid architecture implementation
- 2025-11-21: Added web interface with drag & drop invoice upload on port 5000
- 2025-11-21: Fixed Google Cloud Storage authentication using service account credentials
- 2025-11-21: Updated Flask app to serve web UI and handle file uploads properly

## Key Features

### Invoice Extraction (Self-Improving with RAG)
- **Web Interface**: Drag & drop UI for uploading invoices (port 5000)
- **Self-Learning System**: Automatically learns from successful extractions to improve accuracy over time
- **Vertex AI Search RAG**: Queries knowledge base for similar past invoice extractions before processing
- **Historical Context**: AI uses proven extraction patterns from past invoices for familiar vendors
- Multi-region invoice support (200+ countries, 40+ languages)
- Automated OCR error correction using RAG context
- **AI-First Intelligence**: Chain of Thought reasoning for Hebrew/Arabic RTL, date ambiguity, receipt vs invoice classification
- Python code execution for line item math verification
- Global date format normalization (MM/DD vs DD/MM)
- Currency standardization to ISO 4217
- Real-time processing feedback with visual status indicators
- **Learning Feedback Loop**: Successful extractions (confidence > 0.7) stored to Vertex AI Search for future use

### Gmail Integration
- OAuth 2.0 secure authentication
- 3-stage smart filtering: time-based scanning → semantic filtering → AI extraction
- Server-Sent Events (SSE) for real-time progress monitoring
- Auto-reconnect on connection timeout

### Vendor CSV Import (Self-Improving with RAG)
- **Self-Learning Universal AI Mapper**: Upload ANY vendor CSV from ANY system (SAP, Oracle, QuickBooks, Excel)
- **Vertex AI Search RAG**: Queries knowledge base for similar past CSV mappings before analysis
- **Historical Context**: AI uses proven mappings from past uploads to improve accuracy
- **Multi-Language Support**: German (Firma_Name), Spanish (Empresa), Hebrew (ספק), Arabic, Chinese, etc.
- **Chain of Thought Mapping**: AI explains WHY each column maps to which field, informed by past successes
- **Smart Deduplication**: BigQuery MERGE prevents duplicates
- **Dynamic Schema**: Custom columns stored in JSON (e.g., "Payment Terms", "Credit Limit")
- **Confidence Scoring**: AI rates mapping certainty (1.0 = perfect, 0.4 = weak)
- **Learning Feedback Loop**: Successful imports are automatically stored to Vertex AI Search for future use
- **3-Step Process**: 
  1. RAG Query → Retrieve similar past mappings from Vertex AI Search
  2. Analyze → AI generates column mapping with reasoning + historical context
  3. Import → Transform & merge into BigQuery → Store mapping back to RAG

## Web UI
The web interface (templates/index.html) provides:
- Drag & drop file upload area
- Visual progress indicators during 3-layer processing
- Formatted display of extracted invoice data (vendor, amounts, line items)
- Math verification results
- Support for PDF, PNG, JPG, TIFF files up to 16MB
