# Deployment Configuration
## AP Automation System - Google Cloud Run Deployment

**Version:** 1.0  
**Date:** November 2025  
**Target:** Google Cloud Run

---

## Table of Contents
1. [Dockerfile](#1-dockerfile)
2. [requirements.txt](#2-requirementstxt)
3. [OpenAPI Specification](#3-openapi-specification-openapiyaml)
4. [Deployment Instructions](#4-deployment-instructions)

---

## 1. Dockerfile

```dockerfile
# =============================================================================
# AP Automation System - Production Dockerfile
# Base: Python 3.11 Slim | Target: Google Cloud Run (Port 8080)
# =============================================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# Set working directory
WORKDIR /app

# Install system dependencies for:
# - Playwright (browser automation)
# - Document AI (protobuf, grpc)
# - General utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials
    build-essential \
    gcc \
    g++ \
    # Playwright browser dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    # Font rendering
    fonts-liberation \
    fonts-noto-color-emoji \
    # PDF processing
    poppler-utils \
    # Networking
    curl \
    wget \
    ca-certificates \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for efficiency)
RUN playwright install chromium \
    && playwright install-deps chromium

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose Cloud Run standard port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/agent/status || exit 1

# Run with Gunicorn + Gevent workers
# - Workers: 2 (Cloud Run recommends 1-4 based on CPU)
# - Worker class: gevent (async I/O for AI API calls)
# - Timeout: 300s (for long-running AI processing)
CMD exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --worker-class gevent \
    --worker-connections 1000 \
    --timeout 300 \
    --graceful-timeout 300 \
    --keep-alive 75 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance \
    app:app
```

---

## 2. requirements.txt

```txt
# =============================================================================
# AP Automation System - Python Dependencies
# Generated: November 2025 | Python 3.11
# =============================================================================

# -----------------------------------------------------------------------------
# Core Framework
# -----------------------------------------------------------------------------
Flask==3.0.0
gunicorn==21.2.0
gevent==24.2.1
greenlet==3.0.3
Werkzeug==3.0.1
python-dotenv==1.0.0

# -----------------------------------------------------------------------------
# Google Cloud Services
# -----------------------------------------------------------------------------
# BigQuery
google-cloud-bigquery==3.14.1
google-cloud-bigquery-storage==2.24.0

# Document AI
google-cloud-documentai==2.29.0

# Vertex AI Search (Discovery Engine)
google-cloud-discoveryengine==0.11.11

# Cloud Storage
google-cloud-storage==2.14.0

# Authentication
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.118.0

# Gemini AI (Google GenAI SDK)
google-genai==0.5.1

# -----------------------------------------------------------------------------
# LangChain & LangGraph (Agent Framework)
# -----------------------------------------------------------------------------
langchain==0.1.20
langchain-core==0.1.52
langchain-openai==0.1.6
langgraph==0.0.55
langgraph-checkpoint-sqlite==0.0.1
langsmith==0.1.40

# -----------------------------------------------------------------------------
# OpenAI SDK (for OpenRouter)
# -----------------------------------------------------------------------------
openai==1.12.0

# -----------------------------------------------------------------------------
# Web Scraping & Browser Automation
# -----------------------------------------------------------------------------
playwright==1.41.2
trafilatura==1.6.4
beautifulsoup4==4.12.3
lxml==5.1.0

# -----------------------------------------------------------------------------
# PDF & Document Processing
# -----------------------------------------------------------------------------
reportlab==4.1.0
Pillow==10.2.0
PyPDF2==3.0.1

# -----------------------------------------------------------------------------
# HTTP & API
# -----------------------------------------------------------------------------
requests==2.31.0
requests-oauthlib==1.3.1
httpx==0.26.0
aiohttp==3.9.3

# -----------------------------------------------------------------------------
# Data Processing
# -----------------------------------------------------------------------------
pandas==2.2.0
numpy==1.26.4

# -----------------------------------------------------------------------------
# Security
# -----------------------------------------------------------------------------
bcrypt==4.1.2
cryptography==42.0.2
Flask-Login==0.6.3
Flask-WTF==1.2.1

# -----------------------------------------------------------------------------
# Protocol Buffers & gRPC (for Google Cloud)
# -----------------------------------------------------------------------------
protobuf==4.25.2
grpcio==1.60.1
grpcio-status==1.60.1

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
python-dateutil==2.8.2
pytz==2024.1
tenacity==8.2.3
pydantic==2.6.1
typing-extensions==4.9.0
```

---

## 3. OpenAPI Specification (openapi.yaml)

```yaml
openapi: 3.0.3
info:
  title: AP Automation API
  description: |
    Enterprise Invoice Extraction & Vendor Management API.
    
    Features:
    - AI-powered invoice parsing (Document AI + Gemini)
    - Semantic vendor matching (Vertex AI Search RAG)
    - LangGraph conversational agent
    - Gmail & NetSuite integration
  version: 1.0.0
  contact:
    name: Payouts.com Engineering
    email: engineering@payouts.com

servers:
  - url: https://ap-automation-xxxxx-uc.a.run.app
    description: Production (Google Cloud Run)
  - url: http://localhost:8080
    description: Local Development

tags:
  - name: Agent
    description: LangGraph AI Agent endpoints
  - name: Invoices
    description: Invoice upload and processing

paths:
  # =========================================================================
  # POST /api/agent/chat - The Chat Agent
  # =========================================================================
  /api/agent/chat:
    post:
      tags:
        - Agent
      summary: Chat with the AI Agent
      description: |
        Send a message to the LangGraph-powered AI agent.
        The agent can search vendors, query invoices, scan Gmail, 
        and create NetSuite bills based on natural language requests.
      operationId: agentChat
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ChatRequest'
            examples:
              search_vendors:
                summary: Search for vendors
                value:
                  message: "Show me all vendors from AWS"
                  thread_id: "thread_abc123"
              scan_gmail:
                summary: Scan Gmail for invoices
                value:
                  message: "Scan my Gmail for invoices from the last 7 days"
              create_bill:
                summary: Create a NetSuite bill
                value:
                  message: "Create a bill for invoice INV-2024-001 from Amazon for $1,500"
      responses:
        '200':
          description: Agent response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ChatResponse'
              example:
                success: true
                response: "<table><tr><th>Vendor</th><th>Amount</th></tr><tr><td>AWS</td><td>$1,500</td></tr></table>"
                tools_used:
                  - search_database_first
                  - get_vendor_details
                thread_id: "thread_abc123"
                tokens_used: 1245
        '400':
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '401':
          description: Unauthorized - authentication required
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '429':
          description: Rate limit exceeded
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
      security:
        - sessionAuth: []

  # =========================================================================
  # POST /api/invoices/upload - File Upload
  # =========================================================================
  /api/invoices/upload:
    post:
      tags:
        - Invoices
      summary: Upload and process an invoice
      description: |
        Upload a PDF or image file to be processed through the 4-layer
        hybrid AI pipeline:
        1. Document AI (layout extraction)
        2. Multi-Currency Detector
        3. Vertex AI Search (RAG context)
        4. Gemini Pro (semantic reasoning)
        
        Returns extracted invoice data with vendor matching results.
      operationId: uploadInvoice
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/InvoiceUploadRequest'
      responses:
        '200':
          description: Invoice processed successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/InvoiceUploadResponse'
              example:
                success: true
                invoice_id: "inv_2024_abc123"
                extracted_data:
                  vendor_name: "Amazon Web Services"
                  invoice_number: "INV-2024-12345"
                  invoice_date: "2024-11-15"
                  due_date: "2024-12-15"
                  total_amount: 1500.00
                  currency: "USD"
                  tax_amount: 0.00
                  line_items:
                    - description: "EC2 Instance - m5.large"
                      quantity: 1
                      unit_price: 1200.00
                      amount: 1200.00
                    - description: "S3 Storage"
                      quantity: 1
                      unit_price: 300.00
                      amount: 300.00
                vendor_match:
                  verdict: "MATCH"
                  vendor_id: "vendor_aws_001"
                  confidence: 0.95
                  method: "SEMANTIC_MATCH"
                gcs_uri: "gs://payouts-invoices/invoices/inv_2024_abc123.pdf"
                processing_time_ms: 4523
        '400':
          description: Invalid file format or missing file
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
              example:
                success: false
                error: "Invalid file format. Supported: PDF, PNG, JPEG"
                error_code: "INVALID_FILE_FORMAT"
        '413':
          description: File too large
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: Processing error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
      security:
        - sessionAuth: []

  # =========================================================================
  # GET /api/agent/status - Connection Check
  # =========================================================================
  /api/agent/status:
    get:
      tags:
        - Agent
      summary: Check system status and connections
      description: |
        Health check endpoint that returns the status of all external
        service connections (BigQuery, Gmail, NetSuite, AI models).
        
        Used for:
        - Kubernetes/Cloud Run health probes
        - Client-side connection status display
        - Debugging integration issues
      operationId: getAgentStatus
      responses:
        '200':
          description: System status
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                success: true
                status: "healthy"
                version: "1.0.0"
                timestamp: "2024-11-27T10:30:00Z"
                services:
                  bigquery:
                    connected: true
                    latency_ms: 45
                  gmail:
                    connected: true
                    authenticated_user: "user@company.com"
                  netsuite:
                    connected: true
                    account_id: "TSTDRV1234567"
                  gemini:
                    connected: true
                    model: "gemini-2.5-pro"
                  vertex_search:
                    connected: true
                    data_store_id: "vendor-knowledge-base"
                stats:
                  vendor_count: 738
                  invoice_count: 156
                  pending_approvals: 12
        '503':
          description: Service unavailable
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StatusResponse'
              example:
                success: false
                status: "degraded"
                services:
                  bigquery:
                    connected: true
                  gmail:
                    connected: false
                    error: "Token expired"
                  netsuite:
                    connected: false
                    error: "Connection timeout"

# =============================================================================
# Components
# =============================================================================
components:
  schemas:
    # -------------------------------------------------------------------------
    # Chat Endpoint Schemas
    # -------------------------------------------------------------------------
    ChatRequest:
      type: object
      required:
        - message
      properties:
        message:
          type: string
          description: User message to the AI agent
          minLength: 1
          maxLength: 5000
          example: "Show me all pending invoices over $1,000"
        thread_id:
          type: string
          description: Optional thread ID for conversation continuity
          example: "thread_abc123"
        context:
          type: object
          description: Optional context data (current vendor, invoice, etc.)
          properties:
            current_vendor_id:
              type: string
            current_invoice_id:
              type: string

    ChatResponse:
      type: object
      properties:
        success:
          type: boolean
          example: true
        response:
          type: string
          description: HTML-formatted response from the agent
          example: "<table>...</table>"
        tools_used:
          type: array
          items:
            type: string
          description: List of tools invoked during processing
          example: ["search_database_first", "get_invoice_details"]
        thread_id:
          type: string
          description: Thread ID for conversation continuity
          example: "thread_abc123"
        tokens_used:
          type: integer
          description: Total tokens consumed
          example: 1245
        action_buttons:
          type: array
          items:
            $ref: '#/components/schemas/ActionButton'
          description: Optional action buttons for the UI

    ActionButton:
      type: object
      properties:
        label:
          type: string
          example: "Approve Invoice"
        action:
          type: string
          enum: [approve, reject, create_bill, sync_netsuite]
        data:
          type: object
          additionalProperties: true

    # -------------------------------------------------------------------------
    # Invoice Upload Schemas
    # -------------------------------------------------------------------------
    InvoiceUploadRequest:
      type: object
      required:
        - file
      properties:
        file:
          type: string
          format: binary
          description: Invoice file (PDF, PNG, or JPEG)
        vendor_hint:
          type: string
          description: Optional vendor name hint for matching
          example: "AWS"
        auto_create_bill:
          type: boolean
          default: false
          description: Automatically create NetSuite bill if match found

    InvoiceUploadResponse:
      type: object
      properties:
        success:
          type: boolean
        invoice_id:
          type: string
          description: Unique invoice identifier
          example: "inv_2024_abc123"
        extracted_data:
          $ref: '#/components/schemas/ExtractedInvoiceData'
        vendor_match:
          $ref: '#/components/schemas/VendorMatchResult'
        gcs_uri:
          type: string
          description: Google Cloud Storage URI for the stored file
          example: "gs://payouts-invoices/invoices/inv_2024_abc123.pdf"
        processing_time_ms:
          type: integer
          description: Total processing time in milliseconds
          example: 4523

    ExtractedInvoiceData:
      type: object
      properties:
        vendor_name:
          type: string
          example: "Amazon Web Services"
        invoice_number:
          type: string
          example: "INV-2024-12345"
        invoice_date:
          type: string
          format: date
          example: "2024-11-15"
        due_date:
          type: string
          format: date
          example: "2024-12-15"
        total_amount:
          type: number
          format: float
          example: 1500.00
        currency:
          type: string
          example: "USD"
        tax_amount:
          type: number
          format: float
          example: 0.00
        tax_id:
          type: string
          example: "US123456789"
        line_items:
          type: array
          items:
            $ref: '#/components/schemas/LineItem'

    LineItem:
      type: object
      properties:
        description:
          type: string
          example: "EC2 Instance - m5.large"
        quantity:
          type: number
          example: 1
        unit_price:
          type: number
          format: float
          example: 1200.00
        amount:
          type: number
          format: float
          example: 1200.00

    VendorMatchResult:
      type: object
      properties:
        verdict:
          type: string
          enum: [MATCH, NEW_VENDOR, AMBIGUOUS, INVALID_VENDOR]
          example: "MATCH"
        vendor_id:
          type: string
          nullable: true
          example: "vendor_aws_001"
        confidence:
          type: number
          format: float
          minimum: 0
          maximum: 1
          example: 0.95
        method:
          type: string
          enum: [TAX_ID_HARD_MATCH, SEMANTIC_MATCH, NEW_VENDOR]
          example: "SEMANTIC_MATCH"
        reasoning:
          type: string
          example: "Email domain @aws.amazon.com matches vendor record"

    # -------------------------------------------------------------------------
    # Status Endpoint Schemas
    # -------------------------------------------------------------------------
    StatusResponse:
      type: object
      properties:
        success:
          type: boolean
        status:
          type: string
          enum: [healthy, degraded, unhealthy]
          example: "healthy"
        version:
          type: string
          example: "1.0.0"
        timestamp:
          type: string
          format: date-time
          example: "2024-11-27T10:30:00Z"
        services:
          type: object
          properties:
            bigquery:
              $ref: '#/components/schemas/ServiceStatus'
            gmail:
              $ref: '#/components/schemas/ServiceStatus'
            netsuite:
              $ref: '#/components/schemas/ServiceStatus'
            gemini:
              $ref: '#/components/schemas/ServiceStatus'
            vertex_search:
              $ref: '#/components/schemas/ServiceStatus'
        stats:
          type: object
          properties:
            vendor_count:
              type: integer
              example: 738
            invoice_count:
              type: integer
              example: 156
            pending_approvals:
              type: integer
              example: 12

    ServiceStatus:
      type: object
      properties:
        connected:
          type: boolean
          example: true
        latency_ms:
          type: integer
          example: 45
        error:
          type: string
          nullable: true
        authenticated_user:
          type: string
          nullable: true
        account_id:
          type: string
          nullable: true
        model:
          type: string
          nullable: true
        data_store_id:
          type: string
          nullable: true

    # -------------------------------------------------------------------------
    # Error Schema
    # -------------------------------------------------------------------------
    ErrorResponse:
      type: object
      properties:
        success:
          type: boolean
          example: false
        error:
          type: string
          description: Human-readable error message
          example: "Invalid file format"
        error_code:
          type: string
          description: Machine-readable error code
          example: "INVALID_FILE_FORMAT"
        details:
          type: object
          additionalProperties: true
          description: Additional error context

  # ---------------------------------------------------------------------------
  # Security Schemes
  # ---------------------------------------------------------------------------
  securitySchemes:
    sessionAuth:
      type: apiKey
      in: cookie
      name: session
      description: Flask session cookie authentication

    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Optional JWT authentication for API clients
```

---

## 4. Deployment Instructions

### Build and Push to Google Container Registry

```bash
# Set project ID
export PROJECT_ID=your-project-id
export REGION=us-central1
export SERVICE_NAME=ap-automation

# Build Docker image
docker build -t gcr.io/$PROJECT_ID/$SERVICE_NAME:latest .

# Push to GCR
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME:latest
```

### Deploy to Cloud Run

```bash
# Deploy with required environment variables
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
  --platform managed \
  --region $REGION \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT_NUMBER=123456789012" \
  --set-secrets "OPENROUTERA=openrouter-api-key:latest" \
  --set-secrets "GOOGLE_GEMINI_API_KEY=gemini-api-key:latest" \
  --set-secrets "GOOGLE_APPLICATION_CREDENTIALS_JSON=service-account-json:latest" \
  --set-secrets "GMAIL_CLIENT_ID=gmail-client-id:latest" \
  --set-secrets "GMAIL_CLIENT_SECRET=gmail-client-secret:latest" \
  --set-secrets "NETSUITE_ACCOUNT_ID=netsuite-account-id:latest" \
  --set-secrets "NETSUITE_CONSUMER_KEY=netsuite-consumer-key:latest" \
  --set-secrets "NETSUITE_CONSUMER_SECRET=netsuite-consumer-secret:latest" \
  --set-secrets "NETSUITE_TOKEN_ID=netsuite-token-id:latest" \
  --set-secrets "NETSUITE_TOKEN_SECRET=netsuite-token-secret:latest" \
  --set-secrets "VERTEX_AI_SEARCH_DATA_STORE_ID=vertex-search-id:latest" \
  --allow-unauthenticated
```

### Create Secrets in Secret Manager

```bash
# Create each secret (run once)
echo -n "sk-or-v1-xxx" | gcloud secrets create openrouter-api-key --data-file=-
echo -n "<YOUR_API_KEY>" | gcloud secrets create gemini-api-key --data-file=-
# ... repeat for all secrets
```

### Verify Deployment

```bash
# Get service URL
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'

# Test health endpoint
curl https://ap-automation-xxxxx-uc.a.run.app/api/agent/status
```

---

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENROUTERA` | OpenRouter API key for Gemini access | Yes |
| `GOOGLE_GEMINI_API_KEY` | Google AI Studio API key (fallback) | Yes |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Service account JSON (base64 or raw) | Yes |
| `GOOGLE_CLOUD_PROJECT_NUMBER` | GCP project number | Yes |
| `DOCAI_PROCESSOR_ID` | Document AI processor ID | Yes |
| `DOCAI_LOCATION` | Document AI location (us/eu) | Yes |
| `VERTEX_AI_SEARCH_DATA_STORE_ID` | Vertex AI Search data store ID | Yes |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID | Yes |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret | Yes |
| `NETSUITE_ACCOUNT_ID` | NetSuite account ID | Yes |
| `NETSUITE_CONSUMER_KEY` | NetSuite OAuth consumer key | Yes |
| `NETSUITE_CONSUMER_SECRET` | NetSuite OAuth consumer secret | Yes |
| `NETSUITE_TOKEN_ID` | NetSuite OAuth token ID | Yes |
| `NETSUITE_TOKEN_SECRET` | NetSuite OAuth token secret | Yes |
| `LANGCHAIN_API_KEY` | LangSmith tracing key | Optional |
| `LANGCHAIN_PROJECT` | LangSmith project name | Optional |

---

*Deployment configuration generated for Payouts.com AP Automation Migration*
