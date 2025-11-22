# Enterprise Invoice Extraction System

## Overview
Enterprise invoice extraction and vendor management system with AI-First semantic intelligence:

### Invoice Processing (3-Layer Hybrid Architecture)
- **Layer 1**: Google Document AI for layout/structure extraction
- **Layer 2**: Vertex AI Search (RAG) for vendor context retrieval
- **Layer 3**: Gemini 1.5 Pro for semantic validation and math checking

### Vendor Database Management (AI-Powered CSV Import)
- **Universal CSV Mapper**: Gemini AI analyzes ANY vendor CSV (SAP, Oracle, QuickBooks, Excel) and automatically maps columns to standardized schema
- **Multi-Language Support**: Handles German (Firma_Name), Spanish (Empresa), Hebrew (ספק), and 40+ languages
- **Smart Deduplication**: BigQuery MERGE operations prevent duplicates
- **Dynamic Schema**: Custom CSV columns stored in JSON field for flexibility

## Architecture

### Invoice Extraction Pipeline
1. **Document AI Invoice Processor** - Extracts structured data with bounding boxes and confidence scores
2. **Vertex AI Search (RAG)** - Retrieves vendor history and canonical IDs from datastore
3. **Gemini 1.5 Pro** - Semantic reasoning, OCR correction, date normalization, and automated math verification

### Vendor Management Pipeline
1. **CSV Upload & Analysis** - AI analyzes headers and sample data to understand schema
2. **Chain of Thought Mapping** - Gemini explains WHY each column maps to which field
3. **Data Transformation** - Normalizes emails, countries, domains into arrays
4. **BigQuery Merge** - Smart deduplication using MERGE operations on vendor_id

## Project Structure
```
/
├── app.py                      # Flask API server with invoice & vendor endpoints
├── config.py                   # Configuration and environment setup
├── invoice_processor.py        # Main invoice processing pipeline
├── services/
│   ├── document_ai_service.py  # Document AI integration
│   ├── vertex_search_service.py # Vertex AI Search (RAG)
│   ├── gemini_service.py       # Gemini semantic validation (invoices)
│   ├── vendor_csv_mapper.py    # AI-powered CSV column mapping
│   ├── bigquery_service.py     # BigQuery vendor database operations
│   ├── gmail_service.py        # Gmail OAuth & invoice import
│   └── token_storage.py        # Secure OAuth token management
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
- **Vertex Search Datastore**: invoices-ds
- **BigQuery Dataset**: vendors_ai
- **BigQuery Table**: global_vendors (vendor master data with dynamic custom_attributes JSON column)
- **Service Accounts**: 
  - `vertex-runner` for Vertex AI Search, Gemini, and BigQuery
  - `documentai-access` for Document AI

## Environment Variables
See `.env` for required configuration including API keys, processor IDs, and service account paths.

## Recent Changes
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

### Invoice Extraction
- **Web Interface**: Drag & drop UI for uploading invoices (port 5000)
- Multi-region invoice support (200+ countries, 40+ languages)
- Automated OCR error correction using RAG context
- **AI-First Intelligence**: Chain of Thought reasoning for Hebrew/Arabic RTL, date ambiguity, receipt vs invoice classification
- Python code execution for line item math verification
- Global date format normalization (MM/DD vs DD/MM)
- Currency standardization to ISO 4217
- Real-time processing feedback with visual status indicators

### Gmail Integration
- OAuth 2.0 secure authentication
- 3-stage smart filtering: time-based scanning → semantic filtering → AI extraction
- Server-Sent Events (SSE) for real-time progress monitoring
- Auto-reconnect on connection timeout

### Vendor CSV Import
- **Universal AI Mapper**: Upload ANY vendor CSV from ANY system (SAP, Oracle, QuickBooks, Excel)
- **Multi-Language Support**: German (Firma_Name), Spanish (Empresa), Hebrew (ספק), Arabic, Chinese, etc.
- **Chain of Thought Mapping**: AI explains WHY each column maps to which field
- **Smart Deduplication**: BigQuery MERGE prevents duplicates
- **Dynamic Schema**: Custom columns stored in JSON (e.g., "Payment Terms", "Credit Limit")
- **Confidence Scoring**: AI rates mapping certainty (1.0 = perfect, 0.4 = weak)
- **2-Step Process**: 
  1. Analyze → AI generates column mapping with reasoning
  2. Import → Transform & merge into BigQuery

## Web UI
The web interface (templates/index.html) provides:
- Drag & drop file upload area
- Visual progress indicators during 3-layer processing
- Formatted display of extracted invoice data (vendor, amounts, line items)
- Math verification results
- Support for PDF, PNG, JPG, TIFF files up to 16MB
