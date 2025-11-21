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
- 2025-11-21: Initial project setup with hybrid architecture implementation

## Key Features
- Multi-region invoice support (200+ countries)
- Automated OCR error correction using RAG context
- Python code execution for line item math verification
- Global date format normalization (MM/DD vs DD/MM)
- Currency standardization to ISO 4217
- Vendor matching with historical data
