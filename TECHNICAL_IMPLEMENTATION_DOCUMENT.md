# Enterprise Invoice Extraction System
## Technical Implementation Document (TID)

**Version:** 1.0  
**Last Updated:** November 25, 2025  
**Document Type:** System Architecture & Implementation Reference

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Technology Stack](#2-technology-stack)
3. [Google Cloud Platform Services](#3-google-cloud-platform-services)
4. [System Architecture](#4-system-architecture)
5. [Backend Services](#5-backend-services)
6. [API Endpoints Reference](#6-api-endpoints-reference)
7. [Database Schema (BigQuery)](#7-database-schema-bigquery)
8. [AI Models & Intelligence Layer](#8-ai-models--intelligence-layer)
9. [Frontend Features](#9-frontend-features)
10. [Authentication & Security](#10-authentication--security)
11. [Third-Party Integrations](#11-third-party-integrations)
12. [Data Flows](#12-data-flows)
13. [File Storage](#13-file-storage)
14. [Environment Variables & Secrets](#14-environment-variables--secrets)

---

# 1. Executive Summary

## What We Built
An AI-first enterprise invoice extraction and vendor management system that automates:
- Invoice data extraction from PDFs, images, and emails
- Vendor matching and resolution using semantic AI
- Two-way synchronization with NetSuite ERP
- Gmail integration for automatic invoice scanning
- Universal CSV import for vendor data
- Bill lifecycle tracking (creation → approval → payment)

## Core Capabilities
| Capability | Description |
|------------|-------------|
| **4-Layer AI Extraction** | Document AI → Multi-Currency Detector → Vertex AI RAG → Gemini Pro |
| **Gmail Integration** | OAuth 2.0, automatic invoice detection, PDF rendering, SSE streaming |
| **NetSuite Sync** | OAuth 1.0a, bills, vendors, payments, approval tracking |
| **Vendor Matching** | 3-step semantic resolution with "Supreme Judge" AI |
| **Self-Learning** | RAG feedback loop, AI learns from corrections |
| **Zero Junk Tolerance** | Anti-hallucination rules, amount validation, deduplication |

---

# 2. Technology Stack

## Backend
| Component | Technology | Version/Details |
|-----------|------------|-----------------|
| **Runtime** | Python | 3.11 |
| **Web Framework** | Flask | Production-ready |
| **WSGI Server** | Gunicorn | 23.0.0 with gevent workers |
| **Worker Type** | gevent | Async support for SSE streams |

## Python Dependencies
```
bcrypt              # Password hashing for API keys
cryptography        # Token encryption (Fernet)
flask               # Web framework
gevent              # Async workers
google-api-python-client  # Google APIs
google-auth         # GCP authentication
google-auth-oauthlib      # OAuth flows
google-cloud-bigquery     # BigQuery client
google-cloud-discoveryengine  # Vertex AI Search
google-cloud-documentai   # Document AI client
google-cloud-storage      # GCS client
google-genai        # Gemini AI SDK
gunicorn            # Production server
openai              # OpenRouter compatibility
pillow              # Image processing
playwright          # HTML to PDF/screenshots
python-dotenv       # Environment variables
reportlab           # PDF generation
requests            # HTTP client
requests-oauthlib   # OAuth 1.0a for NetSuite
sift-stack-py       # Fraud detection (optional)
trafilatura         # HTML text extraction
werkzeug            # WSGI utilities
```

## Frontend
| Component | Technology |
|-----------|------------|
| **Template Engine** | Jinja2 (via Flask) |
| **Styling** | Custom CSS with animations |
| **JavaScript** | Vanilla JS (ES6+) |
| **Real-time Updates** | Server-Sent Events (SSE) |
| **UI Pattern** | Card-based, responsive |

---

# 3. Google Cloud Platform Services

## Project Configuration
| Setting | Value |
|---------|-------|
| **Project ID** | `<PROJECT_ID>` |
| **Project Number** | `437918215047` |
| **Region** | `us-central1` |
| **Location** | `global` (for Vertex AI Search) |

## 3.1 Document AI
**Purpose:** Extract structured data from invoice documents (PDF, PNG, JPEG)

| Setting | Value |
|---------|-------|
| **Processor Type** | Invoice Parser |
| **Processor ID** | `<SET_IN_REPLIT_SECRETS>` |
| **Location** | `us` |
| **Processor Path** | `projects/<PROJECT_ID>/locations/us/processors/<SET_IN_REPLIT_SECRETS>` |

**Extracted Entities:**
- Invoice number, date, due date
- Vendor name, address, tax ID
- Line items (description, quantity, price, total)
- Subtotal, tax, total amount
- Currency, payment terms

## 3.2 Vertex AI Search (RAG)
**Purpose:** Semantic search for vendor matching, invoice learning, and context retrieval

| Setting | Value |
|---------|-------|
| **Data Store ID** | `invoices-ds` |
| **Collection** | `default_collection` |
| **Serving Config** | `projects/437918215047/locations/global/collections/default_collection/dataStores/invoices-ds/servingConfigs/default_search` |

**Data Stores:**
| Data Store | Purpose |
|------------|---------|
| `invoices-ds` | Invoice extraction history, vendor matching context |
| `vendor-mappings-ds` | CSV mapping patterns for learning |

**Stored Documents:**
- Past invoice extractions with corrections
- Rejected entities (for learning what NOT to match)
- Vendor aliases and name variations
- CSV column mapping history

## 3.3 BigQuery
**Purpose:** Primary data warehouse for vendors, invoices, events, and logs

| Setting | Value |
|---------|-------|
| **Dataset** | `vendors_ai` |
| **Location** | `us-central1` |

**Tables:** (See Section 7 for full schemas)
- `global_vendors` - Master vendor database
- `invoices` - All extracted invoices
- `netsuite_events` - Bill lifecycle events
- `netsuite_sync_log` - Sync operation logs
- `gmail_scan_checkpoints` - Resumable scan state
- `ai_feedback_log` - Human corrections for learning
- `api_keys` - Agent API authentication
- `agent_actions` - Pending approval actions

## 3.4 Google Cloud Storage (GCS)
**Purpose:** Permanent storage for invoice files and email snapshots

| Setting | Value |
|---------|-------|
| **Bucket Name** | `payouts-invoices` |
| **Upload Path** | `uploads/` |
| **Supported Types** | PDF, PNG, JPEG, HTML snapshots |

**File Naming Convention:**
```
gs://payouts-invoices/uploads/{timestamp}_{original_filename}
gs://payouts-invoices/uploads/{invoice_id}_email_snapshot.html
```

## 3.5 Gmail API
**Purpose:** OAuth access to user's Gmail for invoice scanning

| Setting | Value |
|---------|-------|
| **Scopes** | `gmail.readonly`, `gmail.modify`, `userinfo.email`, `openid` |
| **OAuth Type** | Web application |
| **Callback URL** | `https://{domain}/api/ap-automation/gmail/callback` |

**Search Queries (Multi-language):**
```
English: invoice OR receipt OR bill OR payment OR statement
Hebrew: חשבונית OR קבלה OR חשבון
German: Rechnung OR Quittung OR Zahlung
Spanish: factura OR recibo OR pago
French: facture OR reçu OR paiement
```

## 3.6 Gemini AI
**Purpose:** Semantic reasoning, entity classification, vendor matching

| Model | Purpose | Context Window |
|-------|---------|----------------|
| **Gemini 3 Pro** (OpenRouter) | Primary extraction, Supreme Judge | 1M tokens |
| **Gemini 2.0 Flash** | Fast classification, CSV mapping | 128K tokens |
| **Gemini 1.5 Pro** | Fallback extraction | 128K tokens |

**3-Tier Fallback Chain:**
1. **Primary:** OpenRouter Gemini 3 Pro (`google/gemini-3-pro-preview`)
2. **Fallback 1:** Google AI Studio (direct API key)
3. **Fallback 2:** Replit AI Integrations

---

# 4. System Architecture

## 4.1 High-Level Architecture
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Invoice   │  │    Gmail    │  │   Vendor    │  │  NetSuite   │        │
│  │   Upload    │  │    Import   │  │    CSV      │  │  Dashboard  │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLASK API SERVER                                   │
│                        (Gunicorn + gevent workers)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         API ENDPOINTS                                │   │
│  │  /api/invoices/*  /api/vendors/*  /api/netsuite/*  /api/gmail/*    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE LAYER (26 Services)                        │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │  DocumentAI   │  │ VertexSearch  │  │    Gemini     │                   │
│  │   Service     │  │   Service     │  │   Service     │                   │
│  └───────────────┘  └───────────────┘  └───────────────┘                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │   BigQuery    │  │    Gmail      │  │   NetSuite    │                   │
│  │   Service     │  │   Service     │  │   Service     │                   │
│  └───────────────┘  └───────────────┘  └───────────────┘                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │ VendorMatcher │  │  CSVMapper    │  │  PDFGenerator │                   │
│  │   Service     │  │   Service     │  │   Service     │                   │
│  └───────────────┘  └───────────────┘  └───────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GOOGLE CLOUD PLATFORM                                 │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│  │ Document  │  │  Vertex   │  │  BigQuery │  │   Cloud   │                │
│  │    AI     │  │ AI Search │  │           │  │  Storage  │                │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NETSUITE ERP                                       │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │    Vendors    │  │     Bills     │  │   Payments    │                   │
│  └───────────────┘  └───────────────┘  └───────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 4.2 Invoice Processing Pipeline
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Upload    │────▶│ Document AI │────▶│ Multi-Curr  │────▶│ Vertex RAG  │
│   File      │     │  Extraction │     │  Detector   │     │   Context   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Store     │◀────│   Vendor    │◀────│  Supreme    │◀────│  Gemini AI  │
│  BigQuery   │     │   Matching  │     │   Judge     │     │  Reasoning  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

## 4.3 Gmail Import Pipeline
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   OAuth     │────▶│   Search    │────▶│   Filter    │
│   Login     │     │   Emails    │     │  Gatekeeper │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
            │ PDF Attach  │           │ HTML Email  │           │  Skip Non-  │
            │  Download   │           │  Snapshot   │           │  Invoice    │
            └─────────────┘           └─────────────┘           └─────────────┘
                    │                         │
                    ▼                         ▼
            ┌─────────────┐           ┌─────────────┐
            │ Document AI │           │  Chain of   │
            │  Extract    │           │  Thought AI │
            └─────────────┘           └─────────────┘
                    │                         │
                    └────────────┬────────────┘
                                 ▼
                         ┌─────────────┐
                         │   Vendor    │
                         │  Matching   │
                         └─────────────┘
                                 │
                                 ▼
                         ┌─────────────┐
                         │ Store + GCS │
                         │  + BigQuery │
                         └─────────────┘
```

---

# 5. Backend Services

## 5.1 Service Architecture
All services are located in `/services/` directory.

### Core Services

| Service | File | Purpose |
|---------|------|---------|
| **BigQueryService** | `bigquery_service.py` | All database operations, table management |
| **DocumentAIService** | `document_ai_service.py` | Invoice parsing via Document AI |
| **VertexSearchService** | `vertex_search_service.py` | RAG queries, document storage |
| **GeminiService** | `gemini_service.py` | AI reasoning with 3-tier fallback |
| **GmailService** | `gmail_service.py` | OAuth, email search, attachment extraction |
| **NetSuiteService** | `netsuite_service.py` | OAuth 1.0a, REST API operations |

### AI Intelligence Services

| Service | File | Purpose |
|---------|------|---------|
| **VendorMatcher** | `vendor_matcher.py` | 3-step semantic vendor matching |
| **SemanticEntityClassifier** | `semantic_entity_classifier.py` | Entity type classification |
| **SemanticVendorResolver** | `semantic_vendor_resolver.py` | True vendor identity resolution |
| **VendorCSVMapper** | `vendor_csv_mapper.py` | AI-powered CSV column mapping |
| **VertexVendorMappingSearch** | `vertex_vendor_mapping_search.py` | RAG for CSV mapping patterns |

### Utility Services

| Service | File | Purpose |
|---------|------|---------|
| **SecureTokenStorage** | `token_storage.py` | Encrypted OAuth token storage |
| **PDFInvoiceGenerator** | `pdf_generator.py` | Create PDF invoices |
| **ScreenshotService** | `screenshot_service.py` | Playwright web screenshots |
| **InvoiceComposer** | `invoice_composer.py` | Smart invoice generation |
| **RetryUtils** | `retry_utils.py` | Exponential backoff utilities |

### Agent & Automation Services

| Service | File | Purpose |
|---------|------|---------|
| **AgentAuthService** | `agent_auth_service.py` | API key generation and validation |
| **AgentSearchService** | `agent_search_service.py` | Unified search interface |
| **IssueDetector** | `issue_detector.py` | Compliance issue detection |
| **ActionManager** | `action_manager.py` | Pending action management |
| **SyncManager** | `sync_manager.py` | NetSuite sync orchestration |
| **AuditSyncManager** | `audit_sync_manager.py` | Poll NetSuite for real data |
| **NetSuiteEventTracker** | `netsuite_event_tracker.py` | Event logging to BigQuery |

---

## 5.2 Service Details

### BigQueryService
**File:** `services/bigquery_service.py`

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `ensure_table_exists()` | Create tables with schema if missing |
| `ensure_invoices_table_exists()` | Create/update invoices table |
| `store_invoice()` | Save invoice with validation |
| `get_invoice()` | Retrieve invoice by ID |
| `merge_vendors()` | Upsert vendor data with deduplication |
| `get_vendors()` | Paginated vendor retrieval |
| `search_vendors()` | Text search across vendors |
| `create_gmail_scan_checkpoint()` | Start resumable scan |
| `update_gmail_scan_checkpoint()` | Update scan progress |
| `store_ai_feedback()` | Log human corrections |
| `check_invoice_exists()` | Deduplication check |

### GeminiService
**File:** `services/gemini_service.py`

**3-Tier Fallback Architecture:**
```python
def get_gemini_response(prompt):
    # Tier 1: OpenRouter Gemini 3 Pro
    try:
        return openrouter_client.generate(model="google/gemini-3-pro-preview", ...)
    except:
        pass
    
    # Tier 2: Google AI Studio
    try:
        return genai_client.generate(model="gemini-1.5-pro", ...)
    except:
        pass
    
    # Tier 3: Replit AI Integrations
    return replit_ai.generate(...)
```

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `extract_invoice_data()` | AI extraction from text |
| `validate_entity()` | Entity classification |
| `supreme_judge_matching()` | Vendor matching decision |
| `map_csv_columns()` | CSV to schema mapping |

### VendorMatcher
**File:** `services/vendor_matcher.py`

**3-Step Matching Pipeline:**
```
Step 0: Hard Tax ID Match (BigQuery SQL)
    ↓ No match?
Step 1: Semantic Candidate Retrieval (Vertex AI Search)
    ↓ Top 5 candidates
Step 2: Supreme Judge (Gemini AI Decision)
    ↓ Final verdict
Result: MATCH | NEW_VENDOR | AMBIGUOUS
```

**Evidence Hierarchy:**
| Tier | Confidence | Evidence Types |
|------|------------|----------------|
| 🥇 Gold | 0.95-1.0 | Tax ID, IBAN, unique corporate domain |
| 🥈 Silver | 0.75-0.90 | Semantic name match, address, phone |
| 🥉 Bronze | 0.50-0.70 | Generic name match, partial match |

### NetSuiteService
**File:** `services/netsuite_service.py`

**Authentication:** OAuth 1.0a with HMAC-SHA256 signature

**Configuration:**
| Setting | Environment Variable |
|---------|---------------------|
| Account ID | `NETSUITE_ACCOUNT_ID` |
| Consumer Key | `NETSUITE_CONSUMER_KEY` |
| Consumer Secret | `NETSUITE_CONSUMER_SECRET` |
| Token ID | `NETSUITE_TOKEN_ID` |
| Token Secret | `NETSUITE_TOKEN_SECRET` |

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `create_vendor()` | Create vendor in NetSuite |
| `update_vendor()` | Update existing vendor |
| `create_bill()` | Create vendor bill |
| `update_bill()` | Update bill details |
| `get_bill_status()` | Check approval/payment status |
| `get_vendor()` | Retrieve vendor by ID |
| `search_vendors()` | Search NetSuite vendors |

### GmailService
**File:** `services/gmail_service.py`

**OAuth Scopes:**
- `gmail.readonly` - Read emails
- `gmail.modify` - Mark as read
- `userinfo.email` - Get user email
- `openid` - OpenID authentication

**Key Methods:**
| Method | Purpose |
|--------|---------|
| `get_authorization_url()` | Generate OAuth URL |
| `exchange_code_for_token()` | OAuth callback handler |
| `search_emails()` | Search with multi-language queries |
| `get_email_content()` | Extract body and attachments |
| `download_attachment()` | Get PDF/image attachments |
| `render_html_to_pdf()` | Convert email to PDF |
| `render_html_to_image()` | Screenshot email content |

---

# 6. API Endpoints Reference

## 6.1 Invoice Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/upload` | Upload and process invoice file |
| `POST` | `/process` | Process invoice from GCS URI |
| `GET` | `/api/invoices/list` | List all invoices (paginated) |
| `GET` | `/api/invoices/<id>` | Get invoice by ID |
| `GET` | `/api/invoices/<id>/download` | Get signed URL for file |
| `POST` | `/api/invoices/<id>/approve` | Approve extraction |
| `POST` | `/api/invoices/<id>/reject` | Reject with reason |
| `POST` | `/api/invoices/<id>/update-vendor` | Link vendor to invoice |
| `POST` | `/api/invoices/<id>/link-vendor` | Associate vendor ID |
| `GET` | `/api/invoices/gcs/signed-url` | Get signed URL by GCS URI |
| `GET` | `/api/invoices/review` | List pending review invoices |
| `GET` | `/api/invoice/<id>/timeline` | Get bill lifecycle events |

## 6.2 Vendor Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/vendors/list` | List vendors (paginated) |
| `GET` | `/api/vendors/search` | Search vendors by name |
| `POST` | `/api/vendors/add` | Add new vendor |
| `POST` | `/api/vendors/search-similar` | Find similar vendors |
| `POST` | `/api/vendors/create-from-invoice` | Create vendor from invoice data |
| `POST` | `/api/vendor/match` | Run vendor matching |
| `POST` | `/api/vendors/csv/analyze` | Analyze CSV structure |
| `POST` | `/api/vendors/csv/import` | Import vendors from CSV |
| `POST` | `/api/vendors/csv/sync-netsuite` | Sync imported vendors to NetSuite |

## 6.3 Gmail Integration Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/ap-automation/gmail/auth` | Start OAuth flow |
| `GET` | `/api/ap-automation/gmail/callback` | OAuth callback |
| `GET` | `/api/ap-automation/gmail/status` | Check connection status |
| `POST` | `/api/ap-automation/gmail/disconnect` | Disconnect Gmail |
| `GET` | `/api/ap-automation/gmail/import/stream` | SSE streaming import |
| `POST` | `/api/ap-automation/gmail/import` | Non-streaming import |
| `GET` | `/api/ap-automation/gmail/scans/resumable` | List resumable scans |
| `POST` | `/api/ap-automation/gmail/scans/<id>/pause` | Pause running scan |

## 6.4 NetSuite Integration Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/netsuite/test` | Test connection |
| `GET` | `/api/netsuite/status` | Get sync status |
| `POST` | `/api/netsuite/vendor/check` | Check if vendor exists |
| `POST` | `/api/netsuite/vendor/create` | Create vendor in NetSuite |
| `POST` | `/api/netsuite/vendor/update` | Update vendor |
| `POST` | `/api/netsuite/vendor/<id>/create` | Create vendor by local ID |
| `POST` | `/api/netsuite/vendor/<id>/update` | Update vendor by local ID |
| `POST` | `/api/netsuite/vendors/pull` | Pull vendors from NetSuite |
| `POST` | `/api/netsuite/invoice/<id>/create` | Create bill from invoice |
| `POST` | `/api/netsuite/invoice/<id>/update` | Update existing bill |
| `POST` | `/api/netsuite/sync/vendor/<id>` | Sync single vendor |
| `POST` | `/api/netsuite/sync/invoice/<id>` | Sync single invoice |
| `POST` | `/api/netsuite/sync/bulk` | Bulk sync operation |
| `GET` | `/api/netsuite/sync/dashboard` | Sync statistics |

## 6.5 NetSuite Events & Audit Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/netsuite/events` | List all events |
| `GET` | `/api/netsuite/events/stats` | Event statistics |
| `GET` | `/api/netsuite/events/supported` | Supported event types |
| `POST` | `/api/netsuite/events/log` | Log custom event |
| `GET` | `/api/netsuite/events/dashboard` | Events dashboard page |
| `GET` | `/api/netsuite/bill/<id>/approval` | Get approval status |
| `POST` | `/api/netsuite/bills/sync-approvals` | Sync approval statuses |
| `GET` | `/api/netsuite/payments/status/<id>` | Get payment status |
| `GET` | `/api/netsuite/payments/statistics` | Payment statistics |
| `GET` | `/api/netsuite/bills/audit-trail` | Complete audit trail |
| `GET` | `/api/netsuite/invoice/<id>/truth` | Real NetSuite data |
| `POST` | `/api/netsuite/sync/audit` | Full audit sync |

## 6.6 Agent API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/agent/generate-key` | Generate API key |
| `POST` | `/api/agent/search` | Unified search |
| `GET` | `/api/agent/vendor/<id>` | Get vendor details |
| `GET` | `/api/agent/invoice/<id>` | Get invoice details |
| `GET` | `/api/agent/client/<id>/summary` | Client summary |
| `GET` | `/api/agent/issues` | List compliance issues |
| `POST` | `/api/agent/issues/<id>/resolve` | Resolve issue |
| `POST` | `/api/agent/vendor/send-email` | Send vendor email |
| `POST` | `/api/agent/client/notify` | Notify client |
| `POST` | `/api/agent/actions/create` | Create pending action |
| `GET` | `/api/agent/actions/pending` | List pending actions |
| `POST` | `/api/agent/actions/<id>/approve` | Approve action |

## 6.7 Invoice Composer Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/invoice/search-vendors` | Vendor autocomplete |
| `POST` | `/api/invoice/magic-fill` | AI fill invoice fields |
| `POST` | `/api/invoice/validate` | Validate invoice data |
| `POST` | `/api/invoice/generate` | Generate PDF invoice |
| `GET` | `/download/invoice/<filename>` | Download generated PDF |
| `GET` | `/view/invoice/<filename>` | View PDF in browser |

## 6.8 Utility Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/` | Main UI page |
| `GET` | `/api` | API info |
| `GET` | `/health` | Health check |
| `GET` | `/netsuite-dashboard` | NetSuite dashboard page |
| `GET` | `/api/ai/feedback/patterns` | AI learning patterns |
| `POST` | `/api/repair/vendor/<id>/netsuite/<ns_id>` | Repair vendor link |

---

# 7. Database Schema (BigQuery)

## Dataset: `vendors_ai`

### 7.1 global_vendors
**Purpose:** Master vendor database

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `vendor_id` | STRING | REQUIRED | Unique identifier (UUID format) |
| `global_name` | STRING | REQUIRED | Official company name |
| `normalized_name` | STRING | NULLABLE | Lowercase, cleaned name |
| `emails` | STRING | REPEATED | Contact email addresses |
| `domains` | STRING | REPEATED | Web domains |
| `countries` | STRING | REPEATED | ISO country codes |
| `custom_attributes` | JSON | NULLABLE | Additional fields from CSV |
| `source_system` | STRING | NULLABLE | Origin (csv_import, manual, etc.) |
| `netsuite_internal_id` | STRING | NULLABLE | NetSuite vendor ID |
| `last_updated` | TIMESTAMP | NULLABLE | Last modification time |
| `created_at` | TIMESTAMP | NULLABLE | Creation time |

### 7.2 invoices
**Purpose:** All extracted invoices

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `invoice_id` | STRING | REQUIRED | Invoice number or generated ID |
| `vendor_id` | STRING | NULLABLE | Linked vendor ID |
| `vendor_name` | STRING | NULLABLE | Extracted vendor name |
| `client_id` | STRING | NULLABLE | Client/tenant ID |
| `amount` | FLOAT64 | NULLABLE | Total amount |
| `currency` | STRING | NULLABLE | ISO currency code |
| `invoice_date` | DATE | NULLABLE | Invoice date |
| `status` | STRING | NULLABLE | pending, approved, rejected |
| `netsuite_bill_id` | STRING | NULLABLE | NetSuite bill internal ID |
| `netsuite_sync_status` | STRING | NULLABLE | synced, pending, failed |
| `netsuite_sync_date` | TIMESTAMP | NULLABLE | Last sync time |
| `metadata` | JSON | NULLABLE | Full extraction data |
| `gcs_uri` | STRING | NULLABLE | GCS file path |
| `file_type` | STRING | NULLABLE | pdf, png, jpeg, html |
| `file_size` | INT64 | NULLABLE | File size in bytes |
| `created_at` | TIMESTAMP | NULLABLE | Creation time |
| `last_updated` | TIMESTAMP | NULLABLE | Last modification |

### 7.3 netsuite_events
**Purpose:** Bill lifecycle tracking (create, approve, pay)

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `event_id` | STRING | REQUIRED | Unique event ID |
| `timestamp` | TIMESTAMP | REQUIRED | Event time |
| `direction` | STRING | REQUIRED | inbound, outbound |
| `event_type` | STRING | REQUIRED | BILL_CREATE, BILL_APPROVAL, etc. |
| `event_category` | STRING | REQUIRED | Category grouping |
| `status` | STRING | REQUIRED | success, failed, pending |
| `entity_type` | STRING | NULLABLE | invoice, bill, vendor |
| `entity_id` | STRING | NULLABLE | Invoice/vendor ID |
| `netsuite_id` | STRING | NULLABLE | NetSuite internal ID |
| `action` | STRING | NULLABLE | create, update, approve |
| `request_data` | JSON | NULLABLE | API request body |
| `response_data` | JSON | NULLABLE | API response |
| `error_message` | STRING | NULLABLE | Error details |
| `duration_ms` | INT64 | NULLABLE | API call duration |
| `user` | STRING | NULLABLE | User who triggered |
| `metadata` | JSON | NULLABLE | Additional context |

### 7.4 netsuite_sync_log
**Purpose:** Sync operation logging

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `id` | STRING | REQUIRED | Log entry ID |
| `timestamp` | TIMESTAMP | REQUIRED | Log time |
| `entity_type` | STRING | NULLABLE | vendor, invoice |
| `entity_id` | STRING | NULLABLE | Local entity ID |
| `action` | STRING | NULLABLE | create, update, sync |
| `status` | STRING | NULLABLE | success, failed |
| `netsuite_id` | STRING | NULLABLE | NetSuite ID |
| `error_message` | STRING | NULLABLE | Error details |
| `request_data` | JSON | NULLABLE | Request payload |
| `response_data` | JSON | NULLABLE | Response payload |
| `duration_ms` | INT64 | NULLABLE | Call duration |

### 7.5 gmail_scan_checkpoints
**Purpose:** Resumable Gmail scan state

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `scan_id` | STRING | REQUIRED | Unique scan ID |
| `client_email` | STRING | REQUIRED | Gmail account |
| `scan_type` | STRING | NULLABLE | full, incremental |
| `status` | STRING | NULLABLE | running, paused, completed |
| `days_range` | INT64 | NULLABLE | Days to scan back |
| `total_emails` | INT64 | NULLABLE | Total emails found |
| `processed_count` | INT64 | NULLABLE | Emails processed |
| `extracted_count` | INT64 | NULLABLE | Invoices extracted |
| `duplicate_count` | INT64 | NULLABLE | Duplicates skipped |
| `failed_count` | INT64 | NULLABLE | Failed extractions |
| `last_message_id` | STRING | NULLABLE | Last processed email |
| `last_page_token` | STRING | NULLABLE | Gmail pagination token |
| `started_at` | TIMESTAMP | NULLABLE | Scan start time |
| `updated_at` | TIMESTAMP | NULLABLE | Last update |
| `completed_at` | TIMESTAMP | NULLABLE | Completion time |
| `processed_message_ids` | STRING | REPEATED | All processed IDs |
| `error_message` | STRING | NULLABLE | Error if failed |

### 7.6 ai_feedback_log
**Purpose:** Human corrections for AI learning

| Column | Type | Mode | Description |
|--------|------|------|-------------|
| `feedback_id` | STRING | REQUIRED | Unique feedback ID |
| `invoice_id` | STRING | NULLABLE | Related invoice |
| `feedback_type` | STRING | NULLABLE | approval, rejection, correction |
| `original_extraction` | JSON | NULLABLE | AI's original output |
| `corrected_data` | JSON | NULLABLE | Human corrections |
| `rejection_reason` | STRING | NULLABLE | Why rejected |
| `vendor_name_original` | STRING | NULLABLE | AI vendor name |
| `vendor_name_corrected` | STRING | NULLABLE | Corrected name |
| `amount_original` | FLOAT64 | NULLABLE | AI amount |
| `amount_corrected` | FLOAT64 | NULLABLE | Corrected amount |
| `created_at` | TIMESTAMP | NULLABLE | Feedback time |
| `created_by` | STRING | NULLABLE | User ID |
| `applied_to_learning` | BOOL | NULLABLE | If used for training |

### 7.7 api_keys
**Purpose:** Agent API authentication

| Column | Type | Description |
|--------|------|-------------|
| `api_key_hash` | STRING | bcrypt hash of API key |
| `client_id` | STRING | Client identifier |
| `description` | STRING | Key description |
| `created_at` | TIMESTAMP | Creation time |
| `active` | BOOL | If key is active |

### 7.8 agent_actions
**Purpose:** Pending approval actions

| Column | Type | Description |
|--------|------|-------------|
| `action_id` | STRING | Unique action ID |
| `action_type` | STRING | email, update, create |
| `status` | STRING | pending_approval, approved, rejected |
| `priority` | STRING | high, medium, low |
| `vendor_id` | STRING | Related vendor |
| `vendor_email` | STRING | Vendor email |
| `client_id` | STRING | Client ID |
| `issue_id` | STRING | Related issue |
| `email_subject` | STRING | Email subject |
| `email_body` | STRING | Email content |
| `created_at` | TIMESTAMP | Creation time |
| `approved_at` | TIMESTAMP | Approval time |

---

# 8. AI Models & Intelligence Layer

## 8.1 Chain of Thought Extraction
**For text-based emails (no PDF attachment)**

```
Step 1: Entity Classification
├── PROCESSOR: Payment processor (Stripe, PayPal, Wise) → Extract underlying vendor
└── VENDOR: Direct vendor (Flexera, AWS) → Use directly

Step 2: OCR/Text Cleanup
└── Fix common errors: "ofAugustActivity" → "of August Activity"

Step 3: Mathematical Verification
├── Tax = Total - Subtotal
├── Verify line item totals
└── Extract fees vs. actual amounts

Step 4: Confidence Scoring
└── Real scores based on data quality (not fake 85%)

Step 5: Buyer Extraction
└── Find buyer from greetings/payer fields
```

## 8.2 Supreme Judge Vendor Matching
**AI-First Semantic Reasoning Rules:**

| Rule | Example |
|------|---------|
| Corporate Hierarchy | "Slack" → "Salesforce" (parent company) |
| Brand vs. Legal Entity | "GitHub" → "Microsoft Corporation" |
| Geographic Subsidiaries | "Uber BV" (NL) == "Uber Technologies Inc" (USA) |
| Typos & OCR Errors | "G0ogle" == "Google", "Microsft" == "Microsoft" |
| Multilingual Names | "חברת חשמל" (Hebrew) == "Israel Electric Corp" |
| False Friend Detection | "Apple Landscaping" ≠ "Apple Inc." |
| Franchise Logic | "McDonald's (Branch)" → "McDonald's HQ" |

## 8.3 Semantic Entity Classification
**Entity Types:**
| Type | Example | Action |
|------|---------|--------|
| VENDOR | Flexera, AWS, Replit | ✅ Store |
| BANK | Chase, Wells Fargo | ❌ Reject |
| PAYMENT_PROCESSOR | Stripe, PayPal | ⚠️ Extract underlying vendor |
| GOVERNMENT_ENTITY | IRS, HMRC | ❌ Reject |
| INDIVIDUAL_PERSON | John Smith (freelancer) | ✅ Store as vendor |

## 8.4 Zero Junk Tolerance Rules
```python
# Anti-Hallucination
- Never generate fake UUIDs as invoice numbers
- Use "N/A" for missing invoice IDs

# Amount Validation
- Reject invoices with amount = 0
- Reject amounts that don't match line items

# Vendor Validation
- Reject "Unknown" vendor names
- Require at least partial vendor identification

# Payment Processor Filter
- Stripe/PayPal/Wise notifications are NOT invoices
- Extract the real vendor from processor emails

# Cross-Session Deduplication
- With invoice number: dedup key = inv_id|vendor|amount
- Without invoice number: dedup key = vendor|amount|date|subject_hash
```

---

# 9. Frontend Features

## 9.1 Main Interface Tabs

| Tab | Features |
|-----|----------|
| **📤 Invoice Upload** | Drag & drop, file browser, real-time progress |
| **📧 Gmail** | OAuth connect, scan controls, invoice cards |
| **📁 CSV Import** | Upload, AI mapping preview, import progress |
| **🏢 Vendors** | Paginated list, search, NetSuite sync status |
| **🔗 NetSuite** | Connection status, sync dashboard, bulk actions |

## 9.2 Gmail Invoice Cards
Each extracted invoice displays:

```
┌─────────────────────────────────────────────────────────────────┐
│ [Vendor Name]                                    USD 50.26      │
│ Type: Invoice | Language: en                     Invoice #12345 │
│ Email Date: Nov 25, 2025                                        │
├─────────────────────────────────────────────────────────────────┤
│ 📧 Email Subject: Your invoice #12345                           │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────┐  ┌─────────────────────┐               │
│ │ 🏢 Vendor Info      │  │ 💼 Buyer Info       │               │
│ │ Name: Acme Corp     │  │ Name: Your Company  │               │
│ │ Email: ar@acme.com  │  │                     │               │
│ └─────────────────────┘  └─────────────────────┘               │
├─────────────────────────────────────────────────────────────────┤
│ 💰 Financial Breakdown                                          │
│ Subtotal: $45.00    Tax: $5.26    Total: $50.26                │
├─────────────────────────────────────────────────────────────────┤
│ 📋 Line Items (1)                                               │
│ ┌──────────────────────────────────────────────────────────┐   │
│ │ Description         │ Qty │ Unit Price │ Tax  │ Total   │   │
│ │ Software License    │ 1   │ $45.00     │ $5.26│ $50.26  │   │
│ └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│ 🤖 AI Reasoning: Clear invoice with amount $50.26...           │
├─────────────────────────────────────────────────────────────────┤
│ 🔍 Vendor Matching                              [✅ Matched]    │
│ Method: AI Semantic    Confidence: 100%                         │
│ Matched to: Acme Corp V2899 | NetSuite ID: 423                 │
│ Reasoning: Exact name match + domain match                      │
├─────────────────────────────────────────────────────────────────┤
│ 📋 NetSuite Actions                        [✅ Bill updated]    │
│ ✅ Vendor synced to NetSuite (ID: 423)                         │
│ [📝 Create Bill]  [🔄 Update Bill]                              │
├─────────────────────────────────────────────────────────────────┤
│ 📊 Bill Lifecycle Timeline         [Approvals & Payments]       │
│ ┌──────────────────────────────────────────────────────────┐   │
│ │ 🔄 Nov 25, 2025 2:30 PM - Bill Updated (ID: 6656)        │   │
│ │ 📝 Nov 25, 2025 2:25 PM - Bill Created (ID: 6656)        │   │
│ └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│ [📄 View Source]  [📋 View JSON]  [✅ Approve]  [❌ Reject]     │
└─────────────────────────────────────────────────────────────────┘
```

## 9.3 Real-Time Progress (SSE)
**Server-Sent Events for:**
- Invoice processing steps
- Gmail scan progress
- CSV import progress
- Vendor matching progress

**Progress Bar States:**
| State | Color | Description |
|-------|-------|-------------|
| Processing | Blue | In progress |
| Success | Green | Completed |
| Warning | Orange | Partial success |
| Error | Red | Failed |

## 9.4 Vendor Matching Badges
| Badge | Color | Meaning |
|-------|-------|---------|
| ✅ Matched | Green | High confidence match |
| 🆕 New Vendor | Blue | No match, create new |
| ⚠️ Ambiguous | Orange | Multiple possible matches |

---

# 10. Authentication & Security

## 10.1 OAuth Flows

### Gmail OAuth 2.0
```
1. User clicks "Connect Gmail"
2. Redirect to: /api/ap-automation/gmail/auth
3. Google OAuth consent screen
4. Callback to: /api/ap-automation/gmail/callback
5. Token encrypted and stored (Fernet encryption)
6. Session token returned to browser (httpOnly cookie)
```

### NetSuite OAuth 1.0a
```
- Uses: HMAC-SHA256 signature
- Token-based: Consumer key/secret + Token ID/secret
- Every request signed with timestamp + nonce
```

## 10.2 Token Storage
**SecureTokenStorage class:**
- Encryption: Fernet (AES-128-CBC)
- Key storage: `secure_tokens/.key` (chmod 600)
- Token files: `secure_tokens/{session_token}.enc`
- Auto-cleanup: Tokens older than 30 days

## 10.3 API Key Authentication
**For Agent API endpoints:**
```
Header: X-API-Key: sk_xxxxxxxxxxxxx
```
- Keys generated with: `secrets.token_urlsafe(32)`
- Stored as: bcrypt hash in BigQuery
- Validated with: cache (1 hour TTL)

## 10.4 Security Best Practices
- No secrets in code or logs
- All GCS URLs are signed (time-limited)
- OAuth tokens encrypted at rest
- Session tokens are opaque (no user data)
- HTTPS enforced in production

---

# 11. Third-Party Integrations

## 11.1 NetSuite ERP
**Type:** Two-way sync

**Entities Synced:**
| Entity | Direction | Operations |
|--------|-----------|------------|
| Vendors | ↔️ Bidirectional | Create, Update, Pull |
| Bills | → Outbound | Create, Update |
| Payments | ← Inbound | Status polling |
| Approvals | ← Inbound | Status polling |

**API Base URL:** `https://{account_id}.suitetalk.api.netsuite.com/services/rest/record/v1/`

## 11.2 OpenRouter
**Purpose:** Primary AI model access

**Configuration:**
| Setting | Value |
|---------|-------|
| Model | `google/gemini-3-pro-preview` |
| Context | 1M tokens |
| API Base | `https://openrouter.ai/api/v1` |

## 11.3 Google AI Studio
**Purpose:** Fallback AI model

**Models Used:**
- `gemini-1.5-pro` (extraction)
- `gemini-2.0-flash-exp` (fast classification)

## 11.4 Playwright
**Purpose:** HTML to PDF/image conversion

**Use Cases:**
- Render HTML emails as PDFs for Document AI
- Take screenshots of web receipts
- Generate email snapshots for audit trail

---

# 12. Data Flows

## 12.1 Invoice Upload Flow
```
User uploads file
    ↓
Store in GCS: gs://payouts-invoices/uploads/{file}
    ↓
Document AI: Extract entities
    ↓
Multi-Currency: Detect and verify currencies
    ↓
Vertex RAG: Get vendor context from history
    ↓
Gemini: Semantic validation and extraction
    ↓
Vendor Matcher: Find matching vendor
    ↓
Store in BigQuery: invoices table
    ↓
Return results to UI
```

## 12.2 Gmail Import Flow
```
User authenticates via OAuth
    ↓
Search emails with multi-language queries
    ↓
For each email:
    ├── Has PDF attachment?
    │   └── Download → Document AI → Extract
    └── Text-only email?
        └── Chain of Thought AI → Extract
    ↓
Vendor Matching for each invoice
    ↓
Generate email snapshot HTML → Store in GCS
    ↓
Store invoice in BigQuery
    ↓
Stream results via SSE
```

## 12.3 NetSuite Sync Flow
```
User clicks "Create Bill"
    ↓
Validate vendor has NetSuite ID
    ↓
Build bill payload from invoice data
    ↓
POST to NetSuite REST API
    ↓
Log event in netsuite_events table
    ↓
Update invoice with netsuite_bill_id
    ↓
Return success to UI
```

## 12.4 Vendor CSV Import Flow
```
User uploads CSV file
    ↓
Analyze: Detect columns, sample data
    ↓
Vertex RAG: Check for similar past mappings
    ↓
Gemini: AI column mapping with Chain of Thought
    ↓
Show mapping preview to user
    ↓
User confirms → Transform data
    ↓
Entity Classification: Filter non-vendors
    ↓
Merge into BigQuery with deduplication
    ↓
Return import statistics
```

---

# 13. File Storage

## 13.1 Google Cloud Storage

**Bucket:** `payouts-invoices`

**Structure:**
```
gs://payouts-invoices/
├── uploads/
│   ├── {timestamp}_{original_filename}.pdf
│   ├── {timestamp}_{original_filename}.png
│   ├── {invoice_id}_email_snapshot.html
│   └── ...
└── processed/
    └── (future: processed outputs)
```

**File Types:**
| Type | Source | Stored As |
|------|--------|-----------|
| PDF | Direct upload, Gmail attachment | Original PDF |
| PNG/JPEG | Direct upload, Gmail attachment | Original image |
| HTML | Text-only emails | Email snapshot |

**Access:**
- Files are private (no public access)
- Access via signed URLs (1-24 hour expiry)
- Permanent retention (no auto-delete)

## 13.2 Local File Storage

**Token Storage:** `secure_tokens/`
- Encrypted OAuth tokens
- Encryption key

**Uploads (temporary):** `uploads/`
- Temporary storage during processing
- Moved to GCS after processing

---

# 14. Environment Variables & Secrets

## 14.1 Required Secrets

| Secret | Purpose |
|--------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | GCP service account JSON |
| `GOOGLE_GEMINI_API_KEY` | Gemini AI API key |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret |
| `NETSUITE_ACCOUNT_ID` | NetSuite account (e.g., 11236545_SB1) |
| `NETSUITE_CONSUMER_KEY` | NetSuite OAuth consumer key |
| `NETSUITE_CONSUMER_SECRET` | NetSuite OAuth consumer secret |
| `NETSUITE_TOKEN_ID` | NetSuite OAuth token ID |
| `NETSUITE_TOKEN_SECRET` | NetSuite OAuth token secret |
| `VERTEX_AI_SEARCH_DATA_STORE_ID` | Vertex AI Search data store |
| `OPENROUTERA` | OpenRouter API key (Gemini 3 Pro) |

## 14.2 Configuration Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_CLOUD_PROJECT_ID` | `<PROJECT_ID>` | GCP project |
| `GOOGLE_CLOUD_PROJECT_NUMBER` | `437918215047` | GCP project number |
| `GCS_BUCKET_NAME` | `payouts-invoices` | Storage bucket |
| `REGION` | `us-central1` | GCP region |
| `DOCAI_PROCESSOR_ID` | `<SET_IN_REPLIT_SECRETS>` | Document AI processor |
| `DOCAI_LOCATION` | `us` | Document AI location |

## 14.3 Service Account Files

| File | Purpose |
|------|---------|
| `vertex-runner.json` | Vertex AI Search access |
| `documentai-access.json` | Document AI access |

---

# Appendix A: File Structure

```
/
├── app.py                      # Main Flask application (8000+ lines)
├── config.py                   # Configuration class
├── invoice_processor.py        # Invoice processing logic
├── main.py                     # Entry point
├── start.sh                    # Startup script
├── pyproject.toml              # Python dependencies
│
├── services/                   # Backend services (26 files)
│   ├── bigquery_service.py
│   ├── document_ai_service.py
│   ├── gemini_service.py
│   ├── gmail_service.py
│   ├── netsuite_service.py
│   ├── vendor_matcher.py
│   ├── vertex_search_service.py
│   └── ...
│
├── templates/                  # Jinja2 templates
│   └── index.html              # Main UI
│
├── static/                     # Frontend assets
│   ├── script.js               # Main JavaScript (6800+ lines)
│   ├── style.css               # CSS styles
│   └── simple_invoice_actions.js
│
├── utils/                      # Utility functions
│
├── secure_tokens/              # Encrypted OAuth tokens
│
└── uploads/                    # Temporary file storage
```

---

# Appendix B: Event Types

## NetSuite Events Tracked

| Event Type | Description |
|------------|-------------|
| `BILL_CREATE` | New bill created in NetSuite |
| `BILL_UPDATE` | Bill details updated |
| `BILL_APPROVAL` | Bill approved by approver |
| `BILL_REJECTION` | Bill rejected |
| `BILL_PENDING` | Bill pending approval |
| `PAYMENT_COMPLETED` | Bill paid |
| `PAYMENT_SCHEDULED` | Payment scheduled |
| `VENDOR_CREATE` | New vendor created |
| `VENDOR_UPDATE` | Vendor updated |
| `VENDOR_SYNC` | Vendor synced from NetSuite |

---

**Document End**

*This document describes the complete implementation of the Enterprise Invoice Extraction System as built through November 2025.*
