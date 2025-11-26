# Enterprise Invoice Extraction System

## Overview
This project is an AI-first enterprise invoice extraction and vendor management system designed to automate and enhance the accuracy of financial data extraction and vendor information management using semantic intelligence. It features a 4-layer hybrid invoice processing architecture with a self-learning feedback loop, AI-powered CSV import for vendor data with RAG and smart deduplication, secure Gmail integration for invoice scanning, and an AI-first semantic vendor matching engine. The system aims for high accuracy and continuous improvement, including a "Subscription Pulse" feature for SaaS spend management and Shadow IT discovery.

## User Preferences
I prefer simple language and clear explanations. I want iterative development with frequent updates on progress. Ask before making major changes to the architecture or core functionalities. I prefer detailed explanations for complex AI decisions, especially regarding data extraction and mapping.

## System Architecture

### UI/UX Decisions
The web interface supports drag & drop uploads, real-time progress feedback via Server-Sent Events (SSE), a card-based vendor database browser with search and pagination, and professional CSS with hover effects, animations, and color-coded badges. The system also includes an embeddable, self-contained chat widget that provides conversational access to the LangGraph Agent and handles file operations.

### Technical Implementations
The system is built on a Flask API server utilizing Google Cloud Services.

#### Invoice Processing Pipeline
This pipeline integrates Google Document AI for initial extraction, a Multi-Currency Detector, Vertex AI Search (RAG) for historical context, and Gemini 1.5 Pro for semantic reasoning and multi-currency verification. It incorporates AI-first semantic intelligence features like visual supremacy, RTL support, superior date logic, receipt vs. invoice classification, and mathematical verification.

#### Vendor Management Pipeline
This involves AI-powered CSV mapping using Gemini AI with Vertex AI Search RAG to analyze and map columns, Chain of Thought mapping, data transformation, and BigQuery integration for smart deduplication and storage of custom CSV columns.

#### AI-First Semantic Entity Validation
A pure AI-driven validation system using a SemanticEntityClassifier (Gemini 1.5) prevents non-vendors from entering the database. It operates on all vendor ingest paths and uses a RAG Learning Loop for continuous improvement.

#### Vendor Matching Engine — Semantic Vendor Resolution
A 3-step AI-first semantic matching system links invoices to vendor IDs: Hard Tax ID Match, Semantic Candidate Retrieval (Vertex AI Search RAG), and The Supreme Judge (Gemini 1.5 Pro) for global entity resolution based on an evidence hierarchy and semantic reasoning rules.

#### Permanent Invoice Storage System
Uses Google Cloud Storage (GCS) for original invoice files (PDF, PNG, JPEG) and BigQuery for metadata tracking. Integrates with invoice upload, Gmail import, and provides signed URLs for download.

#### Real-Time Progress Tracking System
A comprehensive system using Server-Sent Events (SSE) provides granular, step-by-step feedback for Invoice Processing, CSV Import, Vendor Matching, and Gmail Filtering, with automatic fallback for Gemini service rate limits.

#### Subscription Pulse - SaaS Spend Management & Shadow IT Discovery
A standalone feature for subscription analytics, offering a "Subscription Pulse" navigation tab. It includes a Gemini Flash-powered "Fast Lane Scanner" for email text analysis, auto-detection of recurring purchases, "Shadow IT Detection," "Duplicate Tool Finder," and "Price Change Alerts." Data is stored in `subscription_vendors` and `subscription_events` BigQuery tables.

### Feature Specifications
-   **Multi-Language Support**: For invoice extraction and CSV mapping (40+ languages).
-   **Secure OAuth**: For Gmail integration.
-   **Gmail Elite Gatekeeper**: A 3-stage filtering system with multi-language queries and Gemini Flash AI for semantic filtering.
-   **Invoice Timeline Feature**: Visual timeline showing bill lifecycle events, integrating with NetSuite approval status changes.

### System Design Choices
-   **Modularity**: Structured into logical components.
-   **Configuration**: Environment variables for sensitive information.
-   **Asynchronous Processing**: Gunicorn with gevent workers for long-running AI processes and SSE.

### LangGraph Agent - Omniscient Auditor for AP Automation
A LangGraph-based AI agent provides conversational control with proactive auditing capabilities. It uses a StateGraph with tool-calling via Gemini 2.5 Pro (OpenRouter) and SQLiteSaver checkpointer for persistent conversation memory. The agent proactively provides comprehensive answers, including PDF links, NetSuite sync status, and suggestions for missing invoices or failed syncs. It uses a suite of "Omniscient Tools" for comprehensive data retrieval and "Database Tools" for BigQuery interactions, alongside "Service Tools" for integrations like Gmail and NetSuite.

### Payouts AI Chat Widget
An embeddable chat widget (`static/agent_widget.js`) provides a full interface for interacting with the LangGraph Agent, including file uploads (PDFs/CSVs), rich HTML rendering of data (tables, cards), and action buttons for invoice approval/rejection and bill creation. It communicates with the agent API and handles ingestion tasks through tools like `process_uploaded_invoice` and `import_vendor_csv`.

## External Dependencies

-   **Google Cloud Services**:
    -   **Google Document AI**: Invoice layout and structure extraction.
    -   **Vertex AI Search**: RAG knowledge base for invoice context and CSV mapping patterns.
    -   **Gemini 1.5 Pro / Gemini Flash / Gemini 2.5 Pro / Gemini 3 Pro (via OpenRouter)**: Semantic validation, reasoning, AI-powered CSV column mapping, and email text analysis.
    -   **BigQuery**: Vendor master data storage (`global_vendors`, `netsuite_events`, `subscription_vendors`, `subscription_events`, `invoices`).
    -   **Google Cloud Storage (GCS)**: Invoice storage (`payouts-invoices` bucket).
    -   **Gmail API**: Integration for scanning and importing invoices from emails.
-   **Python Libraries**: Flask, Gunicorn, OAuthlib, LangGraph, LangChain.