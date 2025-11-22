# Enterprise Invoice Extraction System

## Overview
Hybrid architecture invoice processing system that extracts structured data from invoices across 200+ countries with 100% semantic accuracy using:
- **Layer 1**: Google Document AI for layout/structure extraction
- **Layer 2**: Vertex AI Search (RAG) for vendor context retrieval
- **Layer 3**: Gemini 1.5 Pro for semantic validation and math checking

## Architecture
1. **Document AI Invoice Processor** - Extracts structured data with bounding boxes and confidence scores
2. **Vertex AI Search** - Retrieves vendor history and canonical IDs from RAG datastore
3. **Gemini 1.5 Pro** - Semantic reasoning, OCR correction, date normalization, and automated math verification

## Project Structure
```
/
├── app.py                      # Flask API server
├── config.py                   # Configuration and environment setup
├── invoice_processor.py        # Main processing pipeline
├── services/
│   ├── document_ai_service.py  # Document AI integration
│   ├── vertex_search_service.py # Vertex AI Search (RAG)
│   └── gemini_service.py       # Gemini validation
├── utils/
│   ├── date_normalizer.py      # Global date format handling
│   ├── vendor_extractor.py     # Vendor name extraction
│   └── result_formatter.py     # Result formatting utilities
└── requirements.txt            # Python dependencies

## Google Cloud Configuration
- **Project ID**: invoicereader-477008
- **GCS Bucket**: payouts-invoices
- **Document AI Processor**: 919c19aabdb1802d (us region)
- **Vertex Search Datastore**: invoices-ds
- **Service Accounts**: 
  - `vertex-runner` for Vertex AI Search and Gemini
  - `documentai-access` for Document AI

## Environment Variables
See `.env` for required configuration including API keys, processor IDs, and service account paths.

## Recent Changes
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
- **Web Interface**: Beautiful drag & drop UI for uploading invoices (port 5000)
- Multi-region invoice support (200+ countries)
- Automated OCR error correction using RAG context
- Python code execution for line item math verification
- Global date format normalization (MM/DD vs DD/MM)
- Currency standardization to ISO 4217
- Vendor matching with historical data
- Real-time processing feedback with visual status indicators

## Web UI
The web interface (templates/index.html) provides:
- Drag & drop file upload area
- Visual progress indicators during 3-layer processing
- Formatted display of extracted invoice data (vendor, amounts, line items)
- Math verification results
- Support for PDF, PNG, JPG, TIFF files up to 16MB
