# Enterprise Invoice Extraction System

## Overview
This project is an AI-first enterprise invoice extraction and vendor management system. It automates and enhances the accuracy of financial data extraction and vendor information management using semantic intelligence. Key capabilities include a 4-layer hybrid invoice processing architecture (Google Document AI, Multi-Currency Detector, Vertex AI Search RAG, Gemini 1.5 Pro) with a self-learning feedback loop, AI-powered CSV import for vendor data with RAG and smart deduplication, secure Gmail integration for invoice scanning, and an AI-first semantic vendor matching engine. The system is designed for high accuracy, continuous improvement through AI, and includes a new "Subscription Pulse" feature for SaaS spend management and Shadow IT discovery.

## User Preferences
I prefer simple language and clear explanations. I want iterative development with frequent updates on progress. Ask before making major changes to the architecture or core functionalities. I prefer detailed explanations for complex AI decisions, especially regarding data extraction and mapping.

## System Architecture

### UI/UX Decisions
The web interface supports drag & drop for uploads, real-time progress feedback via Server-Sent Events (SSE), a card-based vendor database browser with search and pagination, and professional CSS with hover effects, animations, and color-coded badges.

### Technical Implementations
The system is built on a Flask API server utilizing Google Cloud Services.

#### Invoice Processing Pipeline (Self-Improving with RAG + Multi-Currency Intelligence)
This pipeline uses Document AI for initial extraction, a Multi-Currency Detector, Vertex AI Search (RAG) for vendor history and past invoice extraction learning, and Gemini 1.5 Pro for semantic reasoning and multi-currency verification. It incorporates AI-first semantic intelligence features like visual supremacy protocol, enhanced RTL support, superior date logic, receipt vs invoice classification, and mathematical verification.

#### Vendor Management Pipeline (with RAG Learning Loop)
This involves AI-powered CSV mapping using Gemini AI with Vertex AI Search RAG to analyze and map columns to a standardized schema, Chain of Thought mapping for rationale, data transformation, and BigQuery integration for smart deduplication and storage of custom CSV columns in a JSON field.

#### AI-First Semantic Entity Validation
A pure AI-driven validation system prevents non-vendors (banks, payment processors, government entities) from polluting the vendor database using a SemanticEntityClassifier (Gemini 1.5). Validation runs on all vendor ingest paths, and a RAG Learning Loop stores rejected entities for continuous learning. The system handles freelancers/contractors as valid vendors.

#### Vendor Matching Engine — Semantic Vendor Resolution
A 3-step AI-first semantic matching system links invoices to vendor IDs:
1.  **Hard Tax ID Match**: Fast, exact match on tax registration IDs using BigQuery SQL.
2.  **Semantic Candidate Retrieval**: Finds top 5 semantically similar vendors using Vertex AI Search RAG, with automatic BigQuery fallback.
3.  **The Supreme Judge (Gemini 1.5 Pro)**: A Global Entity Resolution Engine using an evidence hierarchy (Gold/Silver/Bronze Tiers) and semantic reasoning rules to handle corporate hierarchy, brand vs. legal entity, geographic subsidiaries, typos, multilingual names, and false friend detection.

#### Permanent Invoice Storage System
This system uses Google Cloud Storage (GCS) for permanent storage of original invoice files (PDF, PNG, JPEG) and BigQuery for metadata tracking. Integration points include invoice upload, Gmail import, and a download endpoint for time-limited signed URLs.

#### Real-Time Progress Tracking System
A comprehensive system using Server-Sent Events (SSE) provides granular, step-by-step feedback for Invoice Processing, CSV Import, Vendor Matching, and Gmail Filtering. An automatic fallback system for Gemini service rate limits ensures zero-downtime.

#### Subscription Pulse - SaaS Spend Management & Shadow IT Discovery
A standalone product for subscription analytics, featuring a "Subscription Pulse" navigation tab. It includes a Gemini Flash-powered "Fast Lane Scanner" for email text analysis, auto-detection of recurring vs one-time purchases, "Shadow IT Detection" to identify personal account subscriptions, "Duplicate Tool Finder" for consolidating overlapping SaaS tools, and "Price Change Alerts." Data is stored in `subscription_vendors` and `subscription_events` BigQuery tables.

### Feature Specifications
-   **Multi-Language Support**: For invoice extraction and CSV mapping (40+ languages).
-   **Secure OAuth**: For Gmail integration.
-   **Gmail Elite Gatekeeper**: A 3-stage filtering system with multi-language queries and Gemini Flash AI for semantic filtering.
-   **Invoice Timeline Feature**: Visual timeline showing bill lifecycle events for each invoice, integrating with NetSuite approval status changes.

### System Design Choices
-   **Modularity**: Structured into logical components.
-   **Configuration**: Environment variables for sensitive information.
-   **Asynchronous Processing**: Gunicorn with gevent workers for long-running AI processes and SSE.

## External Dependencies

-   **Google Cloud Services**:
    -   **Google Document AI**: Invoice layout and structure extraction.
    -   **Vertex AI Search**: RAG knowledge base for invoice context and CSV mapping patterns.
    -   **Gemini 1.5 Pro / Gemini Flash / Gemini 3 Pro (via OpenRouter)**: Semantic validation, reasoning, AI-powered CSV column mapping, and email text analysis.
    -   **BigQuery**: Vendor master data storage (`vendors_ai.global_vendors`, `netsuite_events`, `subscription_vendors`, `subscription_events`).
    -   **Google Cloud Storage (GCS)**: Invoice storage (`payouts-invoices` bucket).
    -   **Gmail API**: Integration for scanning and importing invoices from emails.
-   **Python Libraries**: Flask (web framework), Gunicorn (production server), OAuthlib, LangGraph, LangChain.

#### LangGraph Agent - Omniscient Auditor for AP Automation
A LangGraph-based AI agent (`agent/` directory) provides conversational control with proactive auditor capabilities:
-   **Architecture**: StateGraph with tool-calling using Gemini 2.5 Pro via OpenRouter for superior reasoning and tool use
-   **Conversation Memory**: Uses SQLiteSaver checkpointer for persistent conversation state
    -   Frontend generates UUID `session_id` stored in localStorage
    -   Backend receives `thread_id` parameter to maintain conversation context
    -   Agent remembers entities discussed (vendors, invoices) for follow-up questions like "sync it" or "tell me more"
    -   Stored at `data/agent_memory.db`
-   **Omniscient Auditor Behavior**: Agent proactively provides comprehensive answers:
    1.  Always provides PDF links when showing invoices
    2.  Always checks NetSuite sync status when showing vendors
    3.  Notices missing invoices (>30 days) and offers to scan Gmail
    4.  Suggests fixes for failed syncs and missing data
-   **Omniscient Tools** (Priority 1 - Use for comprehensive answers):
    -   `get_vendor_full_profile`: All-in-one vendor dossier (profile + NetSuite + invoices + PDFs + alerts)
    -   `deep_search`: Semantic AI search using Vertex AI Search + BigQuery (for vague queries)
    -   `get_invoice_pdf_link`: Convert GCS URIs to clickable signed HTTPS URLs (1 hour validity)
    -   `check_netsuite_health`: Full NetSuite sync story with alerts and recommendations
-   **Database Tools**:
    -   `search_database_first`: Quick BigQuery lookup for vendors, invoices, subscriptions
    -   `get_top_vendors_by_spend`: Analytics tool for spend analysis (queries invoices table)
    -   `run_bigquery`: Execute SQL queries on data warehouse
-   **Service Tools**:
    -   `check_gmail_status`: Check if Gmail is connected, returns OAuth URL if not
    -   `search_gmail_invoices`: Search Gmail for invoice/receipt emails
    -   `search_netsuite_vendor`: Find vendors by name, email, or tax ID
    -   `create_netsuite_vendor`: Create new vendors in NetSuite
    -   `create_netsuite_bill`: Create vendor bills in NetSuite
    -   `get_bill_status`: Check bill approval status
    -   `match_vendor_to_database`: AI-powered semantic vendor matching
    -   `get_subscription_summary`: Get SaaS subscription analytics
-   **Endpoints**:
    -   `POST /api/agent/chat`: Synchronous chat with agent (accepts `thread_id` for memory)
    -   `POST /api/agent/chat/stream`: SSE streaming chat
    -   `GET /api/agent/tools`: List available tools
    -   `POST /api/agent/feedback`: Submit invoice approval/rejection feedback for AI training
-   **Feedback Loop**: User can approve/reject invoice extractions via chat widget buttons, feeding data back for continuous learning
-   **Tracing**: LangSmith integration for monitoring (LANGCHAIN_API_KEY, LANGCHAIN_PROJECT=payouts-automation)

#### Payouts AI Chat Widget - Full Interface Replacement
A self-contained, embeddable chat widget (`static/agent_widget.js`) that provides conversational access to the LangGraph Agent AND handles all file operations:
-   **Features**:
    -   Floating chat button in bottom-right corner (like Intercom/ChatGPT)
    -   Modern chat window with message history
    -   Tool call badges showing which services the agent used (e.g., "🔍 Checked NetSuite", "📧 Scanned Gmail")
    -   Quick action buttons for common queries
    -   Loading indicators during processing
    -   **HTML Rendering**: Renders clickable action buttons (e.g., "Connect Gmail") and HTML tables
    -   **File Upload (Paperclip Icon)**: Upload PDFs/CSVs directly in chat - no separate UI needed
    -   **Rich Table Rendering**: Agent returns vendor/invoice lists as scrollable HTML tables inside chat bubbles
-   **File Upload Flow**:
    1.  User clicks paperclip icon and selects PDF or CSV file
    2.  Widget shows filename indicator with X to remove
    3.  On send, widget uses FormData with multipart/form-data
    4.  API saves file to `uploads/` directory
    5.  Agent auto-detects file type and calls appropriate tool
    6.  Response includes extraction results + action buttons
-   **Invoice Card Action Handlers**: Rich invoice cards with approve/reject/create bill buttons
    -   `window.approveInvoice(invoiceId)`: Mark extraction as correct, updates BigQuery verified status
    -   `window.rejectInvoice(invoiceId)`: Mark as not an invoice, prompts for reason, adds to Vertex negative training
    -   `window.createBill(invoiceId, vendorId, amount, currency)`: Opens agent with create bill request
    -   `window.viewInvoicePdf(url)`: Opens invoice PDF in new tab
-   **Self-Contained**: Can be embedded on any page with just `<script src="/static/agent_widget.js"></script>`
-   **API Integration**: Communicates with `POST /api/agent/chat` (supports both JSON and FormData)
-   **JavaScript API**: `window.PayoutsAgentWidget.open()`, `.close()`, `.toggle()`, `.sendMessage(msg)`, `.clearSession()`
-   **Ingestion Tools** (New - for file processing):
    -   `process_uploaded_invoice`: Document AI pipeline for PDF invoices with vendor matching
    -   `import_vendor_csv`: AI-powered CSV column mapping with BigQuery import
    -   `pull_netsuite_vendors`: Sync vendors from NetSuite to local database
    -   `show_vendors_table`: Rich HTML table display for vendor listings

## Recent Changes

### November 26, 2025 - SQL Column Name Fixes
Fixed critical SQL schema mismatches in agent tools (`agent/tools.py`):
- Changed `payment_date` → `timestamp` in subscription_events queries
- Changed `subscription_type` → `event_type` in subscription_events queries
- Changed `netsuite_id` → `netsuite_internal_id` in global_vendors queries
- Fixed `check_netsuite_health` to use correct columns from netsuite_sync_log and netsuite_events tables:
  - Uses `TO_JSON_STRING()` for proper JSON column text search
  - Uses `timestamp` instead of `created_at` or `started_at`
  - Uses `entity_type` instead of `record_type`
- Added `sync_status` logic based on `netsuite_internal_id` presence
- All agent tools now correctly query data with multi-tenant isolation using `owner_email`

### BigQuery Table Schemas Reference
- **global_vendors**: vendor_id, global_name, netsuite_internal_id, emails (ARRAY), domains (ARRAY), countries (ARRAY), custom_attributes (JSON), source_system, owner_email
- **subscription_events**: event_id, vendor_id, event_type, timestamp, amount, currency, owner_email
- **invoices**: invoice_id, vendor_id, vendor_name, amount, currency, invoice_date, gcs_uri, owner_email
- **netsuite_events**: event_id, timestamp, event_type, entity_type, entity_id, netsuite_id, status, owner_email
- **netsuite_sync_log**: id, timestamp, entity_type, entity_id, action, status, netsuite_id, owner_email