# Enterprise Invoice Extraction System

## Recent Changes

### November 25, 2025
- **OpenRouter Gemini 3 Pro Integration**: Added flagship model with 1M context window
  - Integrated OpenRouter API with `google/gemini-3-pro-preview` model
  - Uses `OPENROUTERA` secret for API authentication
  - 3-tier fallback chain: **Gemini 3 Pro (PRIMARY)** → AI Studio → Replit AI Integrations
  - Best-in-class reasoning for complex invoice extraction and vendor matching
- **Chain of Thought Semantic Extraction**: Complete rewrite of text-first extraction with true AI reasoning
  - **Step 1: Entity Classification** - Distinguishes PROCESSOR (PBA, Stripe) from VENDOR (Flexera, Wise)
  - **Step 2: OCR/Text Cleanup** - Fixes errors like "ofAugustActivity" → "of August Activity"
  - **Step 3: Mathematical Verification** - Calculates Tax = Total - Subtotal, extracts fees
  - **Step 4: Honest Confidence Scoring** - Real scores based on data quality (no fake 85%)
  - **Step 5: Buyer Extraction** - Finds buyer from greetings/payer fields
  - UI displays Chain of Thought: Processor, Vendor, Buyer, Math, OCR Fixes
- **Improved Smart Deduplication**: Fixed false negative deduplication issue when vendor is "Unknown"
  - Added email subject hash to deduplication key when vendor cannot be identified
  - Prevents false duplicates across different emails with the same invoice number
  - Uses MD5 hash of email subject for differentiation (UNK_HASH format)

### November 24, 2025
- **Fixed Critical Bug**: Resolved vendor_id NULL issue in invoice storage despite successful vendor matching (95% confidence)
  - Enhanced Supreme Judge AI prompt to correctly extract and return candidate_id as selected_vendor_id
  - Added explicit instructions and examples for proper vendor_id extraction from matched candidates
  - Verified fix: Invoices now correctly store vendor_id when matches are found

## Overview
This project is an AI-first enterprise invoice extraction and vendor management system. It leverages semantic intelligence to process invoices, manage vendor data, and continuously learn. The system aims to automate and improve the accuracy of financial data extraction and vendor information management. Key capabilities include a 4-layer hybrid invoice processing architecture (Google Document AI, Multi-Currency Detector, Vertex AI Search RAG, Gemini 1.5 Pro) with a self-learning feedback loop, AI-powered CSV import for vendor data with RAG and smart deduplication into BigQuery, secure Gmail integration for invoice scanning, a semantic vendor matching engine ("Supreme Judge" AI reasoning), and an interactive web UI for uploads and data browsing. The system is designed for high accuracy and continuous improvement through AI.

## User Preferences
I prefer simple language and clear explanations. I want iterative development with frequent updates on progress. Ask before making major changes to the architecture or core functionalities. I prefer detailed explanations for complex AI decisions, especially regarding data extraction and mapping.

## System Architecture

### UI/UX Decisions
The web interface (`templates/index.html`) supports drag & drop for uploads, real-time progress feedback via Server-Sent Events (SSE), a card-based vendor database browser with search and pagination, and professional CSS with hover effects, animations, and color-coded badges.

### Technical Implementations
The system is built on a Flask API server (`app.py`) utilizing Google Cloud Services.

#### Invoice Processing Pipeline (Self-Improving with RAG + Multi-Currency Intelligence)
This pipeline uses Document AI for initial extraction, a Multi-Currency Detector for forensic analysis of currencies and exchange rates, Vertex AI Search (RAG) for vendor history and past invoice extraction learning, and Gemini 1.5 Pro for semantic reasoning and multi-currency verification. It incorporates AI-first semantic intelligence features like visual supremacy protocol, enhanced RTL support, superior date logic, receipt vs invoice classification, and mathematical verification.

#### Vendor Management Pipeline (with RAG Learning Loop)
This involves AI-powered CSV mapping using Gemini AI with Vertex AI Search RAG to analyze and map columns to a standardized schema, Chain of Thought mapping for rationale, data transformation, and BigQuery integration for smart deduplication and storage of custom CSV columns in a JSON field.

#### AI-First Semantic Entity Validation (Product 7)
A pure AI-driven validation system to prevent non-vendors (banks, payment processors, government entities) from polluting the vendor database:
1.  **SemanticEntityClassifier (Gemini 1.5)**: Classifies entities as VENDOR, BANK, PAYMENT_PROCESSOR, GOVERNMENT_ENTITY, or INDIVIDUAL_PERSON using pure semantic understanding of business purpose - NO hardcoded keywords or domain blacklists.
2.  **Multi-Path Integration**: Validation runs on ALL vendor ingest paths (invoice uploads, CSV imports) before database writes.
3.  **Supreme Judge Entity Validation**: Enhanced Supreme Judge prompt validates entity types and honors classifier verdicts.
4.  **RAG Learning Loop**: Rejected entities stored in Vertex Search for continuous learning - system remembers and reuses past rejections.
5.  **BigQuery Fallback**: Resilient vendor matching with fallback to BigQuery LIKE search when Vertex AI Search is empty/misconfigured.

This validation system is automatically integrated into both invoice upload and CSV import pipelines, with rejection statistics returned in API responses.

#### Vendor Matching Engine (Product 4) — Semantic Vendor Resolution
A 3-step AI-first semantic matching system to link invoices to vendor IDs:

**Step 0: Hard Tax ID Match** — Fast, exact match on tax registration IDs using BigQuery SQL (Gold Tier Evidence).

**Step 1: Semantic Candidate Retrieval** — Finds top 5 semantically similar vendors using Vertex AI Search RAG, with automatic BigQuery fallback when Vertex Search fails (404 errors or empty results).

**Step 2: The Supreme Judge (Gemini 1.5 Pro)** — Global Entity Resolution Engine with AI-first semantic intelligence:

**Evidence Hierarchy (Gold/Silver/Bronze Tiers)**:
- 🥇 **Gold Tier** (0.95-1.0 confidence): Tax ID match, IBAN match, unique corporate domain match
- 🥈 **Silver Tier** (0.75-0.90 confidence): Semantic name match, address proximity, phone match
- 🥉 **Bronze Tier** (0.50-0.70 confidence): Generic business name match, partial name match

**Semantic Reasoning Rules** (NO keyword matching):
1. **Corporate Hierarchy & Acquisitions**: "Slack" → "Salesforce" (parent/child relationship detection)
2. **Brand vs. Legal Entity**: "GitHub" → "Microsoft Corporation", "YouTube" → "Google LLC"
3. **Geographic Subsidiaries**: "Uber BV" (Netherlands) == "Uber Technologies Inc" (USA)
4. **Typos & OCR Errors**: "G0ogle" == "Google", "Microsft" == "Microsoft" (AI tolerance)
5. **Multilingual Names**: "חברת חשמל" (Hebrew) == "Israel Electric Corp" (translation understanding)
6. **False Friend Detection**: "Apple Landscaping" ≠ "Apple Inc." (industry validation)
7. **Franchise Logic**: "McDonald's (Branch)" → "McDonald's HQ" (headquarters matching)
8. **Data Evolution**: Self-healing database updates (new aliases, addresses, domains)

This matching system is automatically integrated into the invoice upload pipeline, providing `validated_data` and `vendor_match` results in the UI, with visual indicators and action buttons. The system handles freelancers/contractors as valid vendors (not rejected as INDIVIDUAL_PERSON).

#### Permanent Invoice Storage System (Product 9)
A comprehensive file storage and metadata tracking system for all processed invoices:

**Storage Architecture**:
- **Google Cloud Storage (GCS)**: Permanent storage of original invoice files (PDF, PNG, JPEG) in the `payouts-invoices` bucket under `uploads/` path
- **BigQuery Metadata Tracking**: Extended `vendors_ai.invoices` table with GCS storage columns:
  - `gcs_uri` (STRING): Full GCS URI (format: `gs://bucket/path/file.pdf`)
  - `file_type` (STRING): File type (pdf, png, jpeg)
  - `file_size` (INT64): File size in bytes

**Integration Points**:
1. **Invoice Upload Endpoint** (`/api/invoices/upload`): Automatically saves uploaded files to GCS and stores metadata in BigQuery with vendor matching results
2. **Gmail Import** (both streaming and non-streaming): Downloads attachments/screenshots, processes them, stores permanently in GCS, and saves complete metadata to BigQuery
3. **Download Endpoint** (`/api/invoices/<invoice_id>/download`): Generates time-limited signed URLs (default 1 hour, max 24 hours) for secure file access

**Key Features**:
- Files are NEVER deleted after processing - permanent retention in GCS
- Complete metadata chain: GCS URI → BigQuery → Signed URL for downloads
- Automatic schema migration with fallback handling for existing tables
- Supports all file types processed by Document AI (PDF, PNG, JPEG)
- Secure access via GCS signed URLs with configurable expiration

**API Response Example**:
```json
{
  "success": true,
  "invoice_id": "INV-2025-001",
  "download_url": "https://storage.googleapis.com/...",
  "file_type": "pdf",
  "file_size": 1024567,
  "expires_in": 3600
}
```

#### Real-Time Progress Tracking System
A comprehensive system using Server-Sent Events (SSE) provides granular, step-by-step feedback for Invoice Processing (7 steps), CSV Import (7 steps), Vendor Matching (4 steps), and Gmail Filtering Funnel. This includes CSS infrastructure for progress bars and status displays, JavaScript helper functions for dynamic updates, and backend SSE endpoints for all major workflows. An automatic fallback system is implemented for Gemini service rate limits, switching between a user's API key and Replit AI Integrations to ensure zero-downtime.

### Feature Specifications
-   **Multi-Language Support**: For invoice extraction and CSV mapping (40+ languages).
-   **Secure OAuth**: For Gmail integration, configured for Replit environment.
-   **API Endpoints**: `/api/vendors/list`, `/api/vendors/csv/analyze`, `/api/vendors/csv/import`, `/api/vendor/match`.
-   **Gmail Elite Gatekeeper**: A 3-stage filtering system with multi-language queries and Gemini Flash AI for semantic filtering.

### System Design Choices
-   **Modularity**: Structured into logical components.
-   **Configuration**: Environment variables for sensitive info.
-   **Asynchronous Processing**: Gunicorn with gevent workers for long-running AI processes and SSE.

## External Dependencies

-   **Google Cloud Services**:
    -   **Google Document AI**: Invoice layout and structure extraction.
    -   **Vertex AI Search**: RAG knowledge base for invoice context and CSV mapping patterns.
    -   **Gemini 1.5 Pro**: Semantic validation, reasoning, and AI-powered CSV column mapping.
    -   **BigQuery**: Vendor master data storage (`vendors_ai.global_vendors`).
    -   **Google Cloud Storage (GCS)**: Invoice storage (`payouts-invoices` bucket).
    -   **Gmail API**: Integration for scanning and importing invoices from emails.
-   **Python Libraries**: Flask (web framework), Gunicorn (production server), OAuthlib.