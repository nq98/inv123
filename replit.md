# Enterprise Invoice Extraction System

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

#### Vendor Matching Engine (Product 4)
A 3-step semantic matching system to link invoices to vendor IDs:
1.  **Hard Tax ID Match**: Fast, exact match on tax registration IDs using BigQuery SQL.
2.  **Semantic Candidate Retrieval**: Finds top 5 semantically similar vendors using Vertex AI Search RAG.
3.  **The Supreme Judge (Gemini 1.5 Pro)**: Provides comprehensive semantic reasoning to determine MATCH, NEW_VENDOR, or AMBIGUOUS, handling name variations, typos, multilingual names, and mergers/acquisitions. It includes false friend detection, parent/child logic, risk analysis, and suggests database updates.

This matching system is automatically integrated into the invoice upload pipeline, providing `validated_data` and `vendor_match` results in the UI, with visual indicators and action buttons.

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