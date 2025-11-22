# Enterprise Invoice Extraction System

## Overview
This project is an AI-first enterprise invoice extraction and vendor management system. It leverages semantic intelligence to process invoices, manage vendor data, and continuously learn from new information. The system aims to automate and improve the accuracy of financial data extraction and vendor information management.

Key capabilities include:
- **Invoice Processing**: A 3-layer hybrid architecture (Google Document AI, Vertex AI Search RAG, Gemini 1.5 Pro) with a self-learning feedback loop for high-accuracy invoice data extraction.
- **Vendor Database Management**: AI-powered CSV import with a self-improving universal mapper and RAG for intelligent column mapping, multi-language support, and smart deduplication into a BigQuery vendor master database.
- **Gmail Integration**: Secure OAuth-based integration for scanning and processing invoices from emails.
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

#### Invoice Processing Pipeline (Self-Improving with RAG)
1.  **Document AI Invoice Processor**: Extracts structured data, including bounding boxes and confidence scores.
2.  **Vertex AI Search (RAG)**: Performs dual lookups: (a) Vendor history and canonical IDs, and (b) Similar past invoice extractions, storing successful extractions (confidence > 0.7) for future learning.
3.  **Gemini 1.5 Pro**: Provides semantic reasoning and validation, incorporating historical context from past successful extractions and implementing Chain of Thought reasoning.
4.  **AI-First Semantic Intelligence**: Features include visual supremacy protocol (image pixels > OCR text), enhanced RTL language support, superior date logic (documentDate vs paymentDate vs dueDate), receipt vs invoice classification, subscription detection, global date format resolution, and mathematical verification.

#### Vendor Management Pipeline (with RAG Learning Loop)
1.  **AI-Powered CSV Mapping**: Utilizes Gemini AI with Vertex AI Search RAG to analyze and automatically map columns from various vendor CSV formats (SAP, Oracle, QuickBooks, Excel) to a standardized schema.
2.  **Vertex AI Search RAG**: Stores successful CSV mappings and retrieves similar past mappings to improve accuracy over time (zero-shot → few-shot → many-shot learning).
3.  **Chain of Thought Mapping**: Gemini explains the rationale behind column mappings, leveraging historical context.
4.  **Data Transformation**: Normalizes data such as emails, countries, and domains.
5.  **BigQuery Integration**: Smart deduplication via `MERGE` operations on `vendor_id` and storage of dynamic custom CSV columns in a JSON field (`global_vendors` table).

### Feature Specifications
-   **Multi-Language Support**: Handles over 40 languages for both invoice extraction and CSV mapping, including German, Spanish, and Hebrew.
-   **Secure OAuth**: Implemented for Gmail integration with specific configurations for Replit's environment to prevent "State mismatch" errors and ensure secure cookie handling.
-   **API Endpoints**: Key endpoints include `/api/vendors/list` (with pagination), `/api/vendors/csv/analyze`, and `/api/vendors/csv/import`.

### System Design Choices
-   **Modularity**: The project is structured into logical components (e.g., `invoice_processor.py`, `services/`, `utils/`) for maintainability.
-   **Configuration**: Environment variables are used for sensitive information and service configurations.
-   **Asynchronous Processing**: Switched to Gunicorn with gevent workers for handling long-running AI processes and SSE connections.

## External Dependencies

-   **Google Cloud Services**:
    -   **Google Document AI**: For initial invoice layout and structure extraction.
    -   **Vertex AI Search**: Utilized as a RAG (Retrieval Augmented Generation) knowledge base for both invoice historical context and vendor CSV mapping patterns.
    -   **Gemini 1.5 Pro**: For semantic validation, reasoning, and AI-powered CSV column mapping.
    -   **BigQuery**: Serves as the robust database for storing vendor master data in the `vendors_ai.global_vendors` table.
    -   **Google Cloud Storage (GCS)**: Used for storing invoices in the `payouts-invoices` bucket.
    -   **Gmail API**: For integrating with user Gmail accounts to scan and import invoices.
-   **Python Libraries**: Flask (for the web framework), Gunicorn (for production server), OAuthlib, etc. (implicitly used for functionality).