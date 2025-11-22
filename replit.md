# Enterprise Invoice Extraction System

## Overview
This project is an AI-first enterprise invoice extraction and vendor management system. It leverages semantic intelligence to process invoices, manage vendor data, and continuously learn from new information. The system aims to automate and improve the accuracy of financial data extraction and vendor information management.

Key capabilities include:
- **Invoice Processing**: A 4-layer hybrid architecture (Google Document AI, Multi-Currency Detector, Vertex AI Search RAG, Gemini 1.5 Pro) with a self-learning feedback loop for high-accuracy invoice data extraction.
- **Vendor Database Management**: AI-powered CSV import with a self-improving universal mapper and RAG for intelligent column mapping, multi-language support, and smart deduplication into a BigQuery vendor master database.
- **Gmail Integration**: Secure OAuth-based integration with "Elite Gatekeeper" 3-stage filtering for scanning and processing invoices from emails.
- **Vendor Matching Engine**: Semantic invoice-to-vendor matching with "Supreme Judge" AI reasoning for handling name variations, typos, multilingual names, and mergers/acquisitions.
- **Interactive Web UI**: A user-friendly interface for invoice uploads, CSV imports, and browsing vendor data.

## User Preferences
I prefer simple language and clear explanations. I want iterative development with frequent updates on progress. Ask before making major changes to the architecture or core functionalities. I prefer detailed explanations for complex AI decisions, especially regarding data extraction and mapping.

## System Architecture

### UI/UX Decisions
The system features a web interface (`templates/index.html`) designed for ease of use:
- **Drag & Drop**: For invoice and CSV file uploads.
- **Real-time Feedback**: Server-Sent Events (SSE) provide live progress updates for long-running AI processes.
- **Vendor Database Browser**: A card-based UI with search and pagination for displaying vendor details, including expandable semantic data like emails, domains, countries, and custom attributes.
- **Professional CSS**: Incorporates hover effects, smooth animations, and color-coded badges for an enhanced user experience.

### Technical Implementations
The system is built on a Flask API server (`app.py`) and utilizes several Google Cloud services:

#### Invoice Processing Pipeline (Self-Improving with RAG + Multi-Currency Intelligence)
1.  **Document AI Invoice Processor**: Extracts structured data, including bounding boxes and confidence scores.
2.  **Multi-Currency Detector (Layer 1.5)**: Forensic analysis of currency symbols (₪, $, €, £), exchange rate detection (e.g., "1 USD = 3.27 ILS"), currency hierarchy identification (base currency vs settlement currency), and cross-currency math verification.
3.  **Vertex AI Search (RAG)**: Performs dual lookups: (a) Vendor history and canonical IDs, and (b) Similar past invoice extractions including multi-currency patterns, storing successful extractions (confidence > 0.7) for future learning.
4.  **Gemini 1.5 Pro**: Provides semantic reasoning with forensic accountant protocol for multi-currency scenarios, incorporating historical context from past successful extractions, implementing Chain of Thought reasoning, and step-by-step currency conversion verification.
5.  **AI-First Semantic Intelligence**: Features include multi-currency forensic analysis, visual supremacy protocol (image pixels > OCR text), enhanced RTL language support, superior date logic (documentDate vs paymentDate vs dueDate), receipt vs invoice classification, subscription detection, global date format resolution, and mathematical verification across currencies.

#### Vendor Management Pipeline (with RAG Learning Loop)
1.  **AI-Powered CSV Mapping**: Utilizes Gemini AI with Vertex AI Search RAG to analyze and automatically map columns from various vendor CSV formats (SAP, Oracle, QuickBooks, Excel) to a standardized schema.
2.  **Vertex AI Search RAG**: Stores successful CSV mappings and retrieves similar past mappings to improve accuracy over time (zero-shot → few-shot → many-shot learning).
3.  **Chain of Thought Mapping**: Gemini explains the rationale behind column mappings, leveraging historical context.
4.  **Data Transformation**: Normalizes data such as emails, countries, and domains.
5.  **BigQuery Integration**: Smart deduplication via `MERGE` operations on `vendor_id` and storage of dynamic custom CSV columns in a JSON field (`global_vendors` table).

#### Vendor Matching Engine (Product 4) - NEW (Nov 22, 2025)
A 3-step semantic matching system that links invoices to the correct vendor ID in the database:

1.  **Step 0: Hard Tax ID Match (BigQuery SQL)**
    - Fast exact match on tax registration IDs (VAT, EIN, GST, CNPJ, etc.)
    - Returns 100% confidence match instantly
    - Searches in `custom_attributes.tax_id` JSON field
    - Normalizes IDs by removing spaces, dashes, and standardizing case

2.  **Step 1: Semantic Candidate Retrieval (Vertex AI Search RAG)**
    - Finds top 5 semantically similar vendors by name, domain, address
    - Uses Vertex AI Search for fuzzy matching across vendor database
    - Returns candidates with similarity scores for judgment

3.  **Step 2: The Supreme Judge (Gemini 1.5 Pro)**
    - Comprehensive semantic reasoning to decide: MATCH, NEW_VENDOR, or AMBIGUOUS
    - **Hierarchy of Identifiers**: Tax ID > Bank Account > Corporate Domain > Name+Address
    - **Semantic Flexibility**: Handles fuzzy names, typos, multilingual names (e.g., "חברת חשמל" = "Israel Electric Corp"), acquisitions (e.g., "Slack" → "Salesforce")
    - **False Friend Detection**: Distinguishes between entities with same name (e.g., "Apple Landscaping" ≠ "Apple Inc.")
    - **Parent/Child Logic**: Detects subsidiaries and merger relationships
    - **Risk Analysis**: Flags generic domains (@gmail.com) as higher risk
    - **Self-Healing Database**: Automatically suggests aliases, addresses, domains to add
    - Returns structured verdict with confidence score (0.0-1.0)

**API Endpoint**: `/api/vendor/match` (POST)
- **Input**: vendor_name, tax_id, address, email_domain, phone, country
- **Output**: verdict, vendor_id, confidence, reasoning, risk_analysis, database_updates, method
- **Method Values**: TAX_ID_HARD_MATCH, SEMANTIC_MATCH, or NEW_VENDOR (strictly enforced)

### Feature Specifications
-   **Multi-Language Support**: Handles over 40 languages for both invoice extraction and CSV mapping, including German, Spanish, and Hebrew.
-   **Secure OAuth**: Implemented for Gmail integration with specific configurations for Replit's environment to prevent "State mismatch" errors and ensure secure cookie handling.
-   **API Endpoints**: Key endpoints include `/api/vendors/list` (with pagination), `/api/vendors/csv/analyze`, `/api/vendors/csv/import`, and `/api/vendor/match` (semantic vendor matching).
-   **Gmail Elite Gatekeeper**: 3-stage filtering system with multi-language queries, Gemini Flash AI semantic filter with fail-safe KEEP logic, and full 4-layer invoice processing pipeline.

### System Design Choices
-   **Modularity**: The project is structured into logical components (e.g., `invoice_processor.py`, `services/`, `utils/`) for maintainability.
-   **Configuration**: Environment variables are used for sensitive information and service configurations.
-   **Asynchronous Processing**: Switched to Gunicorn with gevent workers for handling long-running AI processes and SSE connections.
-   **Automatic Fallback System (Nov 22, 2025)**: Gemini service now features automatic rate limit protection with dual-client architecture:
    - **Primary**: User's AI Studio API key (`GOOGLE_GEMINI_API_KEY`)
    - **Fallback**: Replit AI Integrations (billed to Replit credits)
    - When rate limits (429 errors) are hit, automatically switches to fallback client
    - Applies to all Gemini calls: invoice validation, email filtering, and vendor matching
    - Zero-downtime guarantee: system never fails due to quota limits

## External Dependencies

-   **Google Cloud Services**:
    -   **Google Document AI**: For initial invoice layout and structure extraction.
    -   **Vertex AI Search**: Utilized as a RAG (Retrieval Augmented Generation) knowledge base for both invoice historical context and vendor CSV mapping patterns.
    -   **Gemini 1.5 Pro**: For semantic validation, reasoning, and AI-powered CSV column mapping.
    -   **BigQuery**: Serves as the robust database for storing vendor master data in the `vendors_ai.global_vendors` table.
    -   **Google Cloud Storage (GCS)**: Used for storing invoices in the `payouts-invoices` bucket.
    -   **Gmail API**: For integrating with user Gmail accounts to scan and import invoices.
-   **Python Libraries**: Flask (for the web framework), Gunicorn (for production server), OAuthlib, etc. (implicitly used for functionality).