"""
LangGraph Tools - Wraps existing services for LLM control
SEMANTIC AI FIRST: Always check database before external services
"""

import os
import json
from typing import Optional
from langchain_core.tools import tool

from services.gmail_service import GmailService
from services.netsuite_service import NetSuiteService
from services.bigquery_service import BigQueryService
from services.gemini_service import GeminiService
from services.vertex_search_service import VertexSearchService
from services.vendor_matcher import VendorMatcher


gmail_service = GmailService()
netsuite_service = NetSuiteService()
bigquery_service = BigQueryService()
gemini_service = GeminiService()
vertex_search_service = VertexSearchService()
vendor_matcher = VendorMatcher(bigquery_service, vertex_search_service, gemini_service)


def _get_gmail_connect_url():
    """Get the Gmail connect URL - uses the existing app OAuth flow"""
    domain = os.getenv('REPLIT_DEV_DOMAIN', '')
    if domain:
        return f"https://{domain}/api/ap-automation/gmail/auth"
    return "/api/ap-automation/gmail/auth"


def _check_gmail_connected():
    """Check if Gmail is connected by looking at Flask session"""
    try:
        from flask import session
        session_token = session.get('gmail_session_token')
        return session_token is not None
    except:
        return False


@tool
def check_gmail_status() -> str:
    """
    Check if Gmail is connected and get connection URL if needed.
    Use this FIRST before trying to search Gmail.
    
    Returns:
        JSON with connection status and auth URL if not connected
    """
    try:
        is_connected = _check_gmail_connected()
        
        if is_connected:
            return json.dumps({
                "connected": True,
                "message": "Gmail is connected and ready to use"
            })
        else:
            connect_url = _get_gmail_connect_url()
            return json.dumps({
                "connected": False,
                "message": "Gmail is not connected. Please click the button below to connect your Gmail account.",
                "action_required": True,
                "auth_url": connect_url,
                "html_button": f'<a href="{connect_url}" class="chat-action-btn">Connect Gmail</a>'
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def search_database_first(query: str, search_type: str = "all") -> str:
    """
    SEMANTIC AI FIRST: Search the local database before using external services.
    This tool searches BigQuery for existing invoices, vendors, and subscriptions.
    
    Use this BEFORE calling Gmail or other external services!
    
    Args:
        query: Search term (vendor name, invoice number, email, etc.)
        search_type: "vendors", "invoices", "subscriptions", or "all"
    
    Returns:
        JSON with search results from database
    """
    try:
        if not query or len(query.strip()) == 0:
            return json.dumps({"error": "Invalid or empty search query"})
        
        search_pattern = f"%{query.strip().lower()}%"
        
        results = {
            "searched_database": True,
            "query": query,
            "vendors": [],
            "invoices": [],
            "subscriptions": []
        }
        
        if search_type in ["vendors", "all"]:
            vendor_query = """
            SELECT vendor_id, global_name, normalized_name, emails, domains, netsuite_internal_id, source_system
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE LOWER(global_name) LIKE @search_pattern
               OR LOWER(normalized_name) LIKE @search_pattern
               OR LOWER(ARRAY_TO_STRING(emails, ',')) LIKE @search_pattern
               OR LOWER(ARRAY_TO_STRING(domains, ',')) LIKE @search_pattern
            LIMIT 10
            """
            try:
                vendor_results = bigquery_service.query(vendor_query, {"search_pattern": search_pattern})
                results["vendors"] = vendor_results
            except Exception as e:
                results["vendor_error"] = str(e)
        
        if search_type in ["subscriptions", "all"]:
            sub_query = """
            SELECT vendor_name, amount, currency, payment_date, subscription_type
            FROM `invoicereader-477008.vendors_ai.subscription_events`
            WHERE LOWER(vendor_name) LIKE @search_pattern
            ORDER BY payment_date DESC
            LIMIT 10
            """
            try:
                sub_results = bigquery_service.query(sub_query, {"search_pattern": search_pattern})
                results["subscriptions"] = sub_results
            except Exception as e:
                results["subscription_error"] = str(e)
        
        total_found = len(results["vendors"]) + len(results["invoices"]) + len(results["subscriptions"])
        results["total_found"] = total_found
        
        if total_found > 0:
            results["message"] = f"Found {total_found} results in the database. No external service needed."
        else:
            results["message"] = "No results found in database. You may need to search external services."
            results["suggestions"] = [
                "Use check_gmail_status to see if Gmail is connected",
                "Use search_netsuite_vendor to search NetSuite directly"
            ]
        
        return json.dumps(results, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_top_vendors_by_spend(limit: int = 10) -> str:
    """
    Get the top vendors by total payment amount from the INVOICES table.
    Use this for questions about "top vendors", "who did I pay most", "spending analysis".
    
    IMPORTANT: This queries the invoices table (actual financial data), 
    NOT the netsuite_events table (which is just API logs).
    
    Args:
        limit: Number of top vendors to return (default: 10)
    
    Returns:
        JSON with top vendors ranked by total spend
    """
    try:
        query = """
        SELECT 
            vendor_name,
            SUM(amount) as total_spend,
            COUNT(*) as invoice_count,
            MAX(invoice_date) as last_invoice_date,
            STRING_AGG(DISTINCT currency, ', ') as currencies
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE vendor_name IS NOT NULL AND amount IS NOT NULL
        GROUP BY vendor_name
        ORDER BY total_spend DESC
        LIMIT @limit
        """
        
        results = bigquery_service.query(query, {"limit": limit})
        
        if not results:
            return json.dumps({
                "message": "No invoice data found in the database yet.",
                "suggestion": "Try importing invoices from Gmail or uploading them manually first."
            })
        
        formatted = []
        for i, row in enumerate(results, 1):
            formatted.append({
                "rank": i,
                "vendor_name": row.get("vendor_name"),
                "total_spend": float(row.get("total_spend", 0)),
                "invoice_count": row.get("invoice_count"),
                "last_invoice": str(row.get("last_invoice_date")),
                "currencies": row.get("currencies")
            })
        
        total_spend = sum(r["total_spend"] for r in formatted)
        
        return json.dumps({
            "success": True,
            "top_vendors": formatted,
            "total_vendors_shown": len(formatted),
            "total_spend_shown": total_spend,
            "message": f"Top {len(formatted)} vendors by spend (from invoices table)"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def search_gmail_invoices(days: int = 30, max_results: int = 20, access_token: Optional[str] = None) -> str:
    """
    Search Gmail for invoice and receipt emails.
    IMPORTANT: Check database first with search_database_first, then use check_gmail_status before this tool!
    
    Args:
        days: Number of days to look back (default: 30)
        max_results: Maximum number of emails to return (default: 20)
        access_token: Optional Gmail access token (uses stored token if not provided)
    
    Returns:
        JSON string with list of invoice emails found, including subject, sender, date, and snippet
    """
    try:
        from flask import session
        stored_token = session.get('gmail_token') if not access_token else None
        token_to_use = access_token or (stored_token.get('token') if stored_token else None)
        
        if not token_to_use:
            auth_url, state = _get_gmail_auth_url()
            if auth_url:
                return json.dumps({
                    "error": "Gmail not connected",
                    "action_required": True,
                    "message": "I need to connect to Gmail to search your emails.",
                    "auth_url": auth_url,
                    "html_button": f'<a href="{auth_url}" target="_blank" class="chat-action-btn">Connect Gmail Now</a>'
                })
            return json.dumps({"error": "Gmail not connected and could not generate auth URL"})
        
        service = gmail_service.build_service(stored_token or {'token': token_to_use})
        if not service:
            return json.dumps({"error": "Failed to build Gmail service"})
        
        messages = gmail_service.search_invoice_emails(service, max_results=max_results, days=days)
        
        results = []
        for msg in messages[:10]:
            details = gmail_service.get_message_details(service, msg['id'])
            if details:
                metadata = gmail_service.get_email_metadata(details)
                results.append({
                    'id': metadata['id'],
                    'subject': metadata.get('subject', 'No subject'),
                    'from': metadata.get('from', 'Unknown'),
                    'date': metadata.get('date', 'Unknown'),
                    'snippet': metadata.get('snippet', '')[:200],
                    'has_attachments': len(metadata.get('attachments', [])) > 0
                })
        
        return json.dumps({
            "success": True,
            "total_found": len(messages),
            "emails": results
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def create_netsuite_bill(
    vendor_netsuite_id: str,
    invoice_number: str,
    amount: float,
    currency: str = "USD",
    memo: str = ""
) -> str:
    """
    Create a vendor bill in NetSuite.
    
    Args:
        vendor_netsuite_id: The NetSuite internal ID of the vendor
        invoice_number: The invoice number from the invoice document
        amount: The total amount of the invoice
        currency: Currency code (USD, EUR, ILS, etc.)
        memo: Optional memo/notes for the bill
    
    Returns:
        JSON string with the created bill details or error
    """
    try:
        import time
        bill_data = {
            'invoice_id': f"AGENT_{int(time.time())}",
            'vendor_netsuite_id': vendor_netsuite_id,
            'invoice_number': invoice_number,
            'total_amount': amount,
            'currency': currency,
            'memo': memo or f"Created by AI Agent - Invoice {invoice_number}",
            'line_items': [{
                'description': f"Invoice {invoice_number}",
                'amount': amount,
                'account': '351'
            }]
        }
        
        result = netsuite_service.create_vendor_bill(bill_data)
        
        if result:
            return json.dumps({
                "success": True,
                "netsuite_bill_id": result.get('id'),
                "message": f"Successfully created bill for ${amount} {currency}"
            }, indent=2)
        else:
            return json.dumps({"success": False, "error": "Failed to create bill in NetSuite"})
            
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def search_netsuite_vendor(
    name: Optional[str] = None,
    email: Optional[str] = None,
    tax_id: Optional[str] = None
) -> str:
    """
    Search for a vendor in NetSuite by name, email, or tax ID.
    
    Args:
        name: Vendor company name to search for
        email: Vendor email address to search for
        tax_id: Vendor tax/VAT ID to search for
    
    Returns:
        JSON string with vendor details if found, or not found message
    """
    try:
        result = netsuite_service.lookup_vendor_integrated(
            name=name,
            email=email,
            tax_id=tax_id
        )
        
        if result:
            return json.dumps({
                "found": True,
                "vendor": {
                    "netsuite_id": result.get('id'),
                    "name": result.get('companyName'),
                    "email": result.get('email'),
                    "tax_id": result.get('vatRegNumber')
                }
            }, indent=2)
        else:
            return json.dumps({
                "found": False,
                "message": f"No vendor found matching the criteria"
            })
            
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_bill_status(invoice_id: str) -> str:
    """
    Get the status of a bill in NetSuite by invoice ID.
    
    Args:
        invoice_id: The invoice ID to check status for
    
    Returns:
        JSON string with bill status (exists, approval_status, amount, etc.)
    """
    try:
        result = netsuite_service.get_bill_status(invoice_id)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def match_vendor_to_database(
    vendor_name: str,
    tax_id: Optional[str] = None,
    email_domain: Optional[str] = None,
    address: Optional[str] = None,
    country: Optional[str] = None
) -> str:
    """
    Use the AI-powered Supreme Judge to match a vendor name to our vendor database.
    This uses semantic matching with RAG and Gemini reasoning.
    
    Args:
        vendor_name: The vendor name from an invoice
        tax_id: Optional tax/VAT registration number
        email_domain: Optional email domain (e.g., @aws.com)
        address: Optional vendor address
        country: Optional country code (US, IL, etc.)
    
    Returns:
        JSON string with matching result including verdict, vendor_id, confidence, and reasoning
    """
    try:
        invoice_data = {
            'vendor_name': vendor_name,
            'tax_id': tax_id,
            'email_domain': email_domain,
            'address': address,
            'country': country
        }
        
        result = vendor_matcher.match_vendor(invoice_data)
        
        return json.dumps({
            "verdict": result.get('verdict'),
            "vendor_id": result.get('vendor_id'),
            "confidence": result.get('confidence'),
            "reasoning": result.get('reasoning'),
            "method": result.get('method'),
            "risk_analysis": result.get('risk_analysis')
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def run_bigquery(sql_query: str) -> str:
    """
    Execute a SQL query on BigQuery to analyze vendor data, subscriptions, or invoices.
    
    IMPORTANT: Only SELECT queries are allowed. No INSERT, UPDATE, DELETE, or DROP.
    
    Available tables:
    - vendors_ai.global_vendors: Master vendor database
    - vendors_ai.subscription_vendors: SaaS subscription vendors
    - vendors_ai.subscription_events: Subscription payment events
    - vendors_ai.netsuite_events: NetSuite sync events
    
    Args:
        sql_query: The SQL SELECT query to execute
    
    Returns:
        JSON string with query results or error
    """
    try:
        sql_upper = sql_query.upper().strip()
        if any(keyword in sql_upper for keyword in ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER']):
            return json.dumps({"error": "Only SELECT queries are allowed for safety"})
        
        results = bigquery_service.query(sql_query)
        
        return json.dumps({
            "success": True,
            "row_count": len(results),
            "results": results[:100]
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_subscription_summary() -> str:
    """
    Get a summary of all active SaaS subscriptions from Subscription Pulse.
    
    Returns:
        JSON string with subscription summary including count, total spend, and top vendors
    """
    try:
        query = """
        SELECT 
            vendor_name,
            SUM(amount) as total_spend,
            COUNT(*) as payment_count,
            MAX(payment_date) as last_payment,
            MIN(payment_date) as first_payment
        FROM `invoicereader-477008.vendors_ai.subscription_events`
        GROUP BY vendor_name
        ORDER BY total_spend DESC
        LIMIT 20
        """
        
        results = bigquery_service.query(query)
        
        total_spend = sum(r.get('total_spend', 0) for r in results)
        
        return json.dumps({
            "success": True,
            "vendor_count": len(results),
            "total_annual_spend": total_spend,
            "top_subscriptions": results
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool 
def create_netsuite_vendor(
    company_name: str,
    email: Optional[str] = None,
    tax_id: Optional[str] = None,
    phone: Optional[str] = None
) -> str:
    """
    Create a new vendor in NetSuite.
    
    Args:
        company_name: The vendor company name
        email: Vendor email address
        tax_id: Tax/VAT registration number
        phone: Phone number
    
    Returns:
        JSON string with created vendor details or error
    """
    try:
        vendor_data = {
            'name': company_name,
            'email': email,
            'tax_id': tax_id,
            'phone': phone
        }
        
        result = netsuite_service.create_vendor(vendor_data)
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


# ========== OMNISCIENT TOOLS - SEMANTIC AI FIRST ==========

@tool
def deep_search(query: str, search_type: str = "all") -> str:
    """
    Deep semantic search using Vertex AI Search - the 'Deep Swimmer' that finds connections SQL cannot.
    Use this for vague queries like "that expensive software bill" or "invoices from last month".
    
    Args:
        query: Natural language search query (e.g., "expensive software invoice", "Replit bills")
        search_type: Type of search - "vendors", "invoices", or "all" (default: "all")
    
    Returns:
        JSON with semantic search results including vendor matches, invoice data, and GCS URIs for PDFs
    """
    try:
        results = {
            "query": query,
            "search_type": search_type,
            "vendors": [],
            "invoices": [],
            "total_found": 0
        }
        
        # Search vendors using Vertex AI Search
        if search_type in ["vendors", "all"]:
            vendor_results = vertex_search_service.search_vendor(query, max_results=5)
            for r in vendor_results:
                data = r.get('data', {})
                if not data.get('is_rejected_entity'):
                    results["vendors"].append({
                        "vendor_name": data.get('vendor_name'),
                        "vendor_id": data.get('vendor_id'),
                        "netsuite_id": data.get('netsuite_id'),
                        "country": data.get('country'),
                        "last_invoice_amount": data.get('last_invoice_amount'),
                        "domains": data.get('domains')
                    })
        
        # Search invoices using Vertex AI Search
        if search_type in ["invoices", "all"]:
            invoice_results = vertex_search_service.search_similar_invoices(query, limit=5)
            for r in invoice_results:
                data = r.get('data', {})
                extracted = data.get('extracted_data', {})
                results["invoices"].append({
                    "vendor_name": data.get('vendor_name'),
                    "invoice_number": extracted.get('invoiceNumber'),
                    "date": extracted.get('documentDate'),
                    "total": extracted.get('totals', {}).get('total'),
                    "currency": data.get('currency'),
                    "document_type": data.get('document_type'),
                    "gcs_uri": data.get('gcs_uri'),
                    "confidence": data.get('confidence_score')
                })
        
        # Also search BigQuery for more structured results
        if search_type in ["invoices", "all"]:
            bq_query = """
            SELECT 
                invoice_id, vendor_name, invoice_number, invoice_date, 
                amount, currency, gcs_uri, status
            FROM `invoicereader-477008.vendors_ai.invoices`
            WHERE LOWER(vendor_name) LIKE @search_pattern 
               OR LOWER(invoice_number) LIKE @search_pattern
            ORDER BY invoice_date DESC
            LIMIT 5
            """
            search_pattern = f"%{query.lower()}%"
            try:
                bq_results = bigquery_service.query(bq_query, {"search_pattern": search_pattern})
                for row in bq_results:
                    results["invoices"].append({
                        "source": "database",
                        "invoice_id": row.get("invoice_id"),
                        "vendor_name": row.get("vendor_name"),
                        "invoice_number": row.get("invoice_number"),
                        "date": str(row.get("invoice_date")),
                        "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                        "currency": row.get("currency"),
                        "gcs_uri": row.get("gcs_uri"),
                        "status": row.get("status")
                    })
            except Exception as e:
                results["database_error"] = str(e)
        
        results["total_found"] = len(results["vendors"]) + len(results["invoices"])
        
        if results["total_found"] > 0:
            results["message"] = f"Found {results['total_found']} results using semantic search. Use get_invoice_pdf_link to get clickable PDF links."
        else:
            results["message"] = "No results found. Try a different search query or check Gmail for recent invoices."
        
        return json.dumps(results, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_invoice_pdf_link(gcs_uri: str) -> str:
    """
    Convert a GCS URI (gs://bucket/path) to a clickable HTTPS signed URL valid for 1 hour.
    ALWAYS use this when showing invoices to provide the actual PDF link.
    
    Args:
        gcs_uri: The Google Cloud Storage URI (e.g., gs://payouts-invoices/vendor/invoice.pdf)
    
    Returns:
        HTML link to view the PDF, or error if URI is invalid
    """
    try:
        if not gcs_uri or not gcs_uri.startswith('gs://'):
            return json.dumps({
                "error": "Invalid GCS URI. Must start with gs://",
                "provided": gcs_uri
            })
        
        # Parse the GCS URI
        uri_without_prefix = gcs_uri[5:]  # Remove 'gs://'
        parts = uri_without_prefix.split('/', 1)
        
        if len(parts) != 2:
            return json.dumps({"error": "Invalid GCS URI format. Expected gs://bucket/path"})
        
        bucket_name = parts[0]
        blob_name = parts[1]
        
        # Get signed URL using Google Cloud Storage
        from google.cloud import storage
        from datetime import timedelta
        from google.oauth2 import service_account
        
        # Load credentials
        sa_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON') or os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            import json as json_lib
            sa_info = json_lib.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(sa_info)
            storage_client = storage.Client(credentials=credentials, project=sa_info.get('project_id'))
        else:
            storage_client = storage.Client()
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if not blob.exists():
            return json.dumps({
                "error": "File not found in storage",
                "gcs_uri": gcs_uri
            })
        
        # Determine content type
        file_extension = blob_name.split('.')[-1].lower() if '.' in blob_name else 'pdf'
        content_type_map = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg'
        }
        content_type = content_type_map.get(file_extension, 'application/octet-stream')
        
        # Generate signed URL (1 hour validity)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET",
            response_type=content_type
        )
        
        # Extract filename for display
        filename = blob_name.split('/')[-1] if '/' in blob_name else blob_name
        
        return json.dumps({
            "success": True,
            "gcs_uri": gcs_uri,
            "download_url": signed_url,
            "expires_in": "1 hour",
            "file_type": file_extension,
            "html_link": f'<a href="{signed_url}" target="_blank" class="chat-action-btn">📄 View {filename}</a>'
        })
        
    except Exception as e:
        return json.dumps({"error": str(e), "gcs_uri": gcs_uri})


@tool
def check_netsuite_health(vendor_id: str = None, vendor_name: str = None) -> str:
    """
    The 'NetSuite Detective' - Get the FULL story of a vendor's NetSuite sync status.
    Don't just say "Synced" - tell the complete health story including last activity, balance, and any issues.
    
    Args:
        vendor_id: Optional vendor ID to check (e.g., V2099)
        vendor_name: Optional vendor name to search for
    
    Returns:
        Full health report: sync status, last activity, events history, outstanding balance, and alerts
    """
    try:
        report = {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "sync_status": None,
            "netsuite_internal_id": None,
            "last_sync": None,
            "last_activity": None,
            "recent_events": [],
            "alerts": [],
            "recommendations": []
        }
        
        # First, find the vendor in our database
        if vendor_name and not vendor_id:
            vendor_query = """
            SELECT vendor_id, global_name, netsuite_id, email, domains, sync_status
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE LOWER(global_name) LIKE @search_pattern
            LIMIT 1
            """
            results = bigquery_service.query(vendor_query, {"search_pattern": f"%{vendor_name.lower()}%"})
            if results:
                vendor = results[0]
                vendor_id = vendor.get('vendor_id')
                report["vendor_id"] = vendor_id
                report["vendor_name"] = vendor.get('global_name')
                report["netsuite_internal_id"] = vendor.get('netsuite_id')
        
        if not vendor_id:
            return json.dumps({
                "error": "Could not find vendor. Please provide vendor_id or a valid vendor_name.",
                "suggestion": "Use search_database_first to find the vendor first."
            })
        
        # Check sync log for this vendor
        sync_log_query = """
        SELECT 
            sync_type, status, started_at, completed_at, error_message,
            records_processed, records_failed
        FROM `invoicereader-477008.vendors_ai.netsuite_sync_log`
        WHERE vendor_id = @vendor_id OR vendor_name LIKE @vendor_pattern
        ORDER BY started_at DESC
        LIMIT 5
        """
        try:
            sync_logs = bigquery_service.query(sync_log_query, {
                "vendor_id": vendor_id,
                "vendor_pattern": f"%{vendor_name or ''}%"
            })
            
            if sync_logs:
                last_sync = sync_logs[0]
                report["last_sync"] = {
                    "type": last_sync.get("sync_type"),
                    "status": last_sync.get("status"),
                    "started": str(last_sync.get("started_at")),
                    "completed": str(last_sync.get("completed_at")),
                    "records_processed": last_sync.get("records_processed"),
                    "records_failed": last_sync.get("records_failed")
                }
                
                if last_sync.get("status") == "FAILED":
                    report["alerts"].append({
                        "type": "SYNC_FAILED",
                        "message": f"Last sync failed: {last_sync.get('error_message', 'Unknown error')}",
                        "severity": "HIGH"
                    })
                    report["recommendations"].append("Shall I retry the sync?")
        except Exception as e:
            report["sync_log_error"] = str(e)
        
        # Check NetSuite events for this vendor
        events_query = """
        SELECT 
            event_type, record_type, netsuite_id, status, 
            created_at, error_message, request_data, response_data
        FROM `invoicereader-477008.vendors_ai.netsuite_events`
        WHERE LOWER(CAST(request_data AS STRING)) LIKE @vendor_pattern
           OR LOWER(CAST(response_data AS STRING)) LIKE @vendor_pattern
        ORDER BY created_at DESC
        LIMIT 10
        """
        try:
            events = bigquery_service.query(events_query, {
                "vendor_pattern": f"%{(vendor_name or vendor_id).lower()}%"
            })
            
            for event in events:
                event_summary = {
                    "type": event.get("event_type"),
                    "record_type": event.get("record_type"),
                    "status": event.get("status"),
                    "timestamp": str(event.get("created_at")),
                    "netsuite_id": event.get("netsuite_id")
                }
                report["recent_events"].append(event_summary)
                
                # Set last activity from most recent event
                if not report["last_activity"] and events:
                    first_event = events[0]
                    report["last_activity"] = f"{first_event.get('event_type')} ({first_event.get('record_type')}) on {str(first_event.get('created_at'))[:10]}"
            
            # Check for failed events
            failed_events = [e for e in events if e.get("status") == "ERROR"]
            if failed_events:
                report["alerts"].append({
                    "type": "RECENT_ERRORS",
                    "message": f"{len(failed_events)} recent NetSuite operations failed",
                    "severity": "MEDIUM"
                })
                
        except Exception as e:
            report["events_error"] = str(e)
        
        # Get invoice count and outstanding balance
        invoice_query = """
        SELECT 
            COUNT(*) as invoice_count,
            SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END) as pending_amount,
            SUM(amount) as total_spend,
            MAX(invoice_date) as last_invoice_date
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE LOWER(vendor_name) LIKE @vendor_pattern
        """
        try:
            invoice_stats = bigquery_service.query(invoice_query, {
                "vendor_pattern": f"%{(vendor_name or '').lower()}%"
            })
            if invoice_stats:
                stats = invoice_stats[0]
                report["financials"] = {
                    "total_invoices": stats.get("invoice_count"),
                    "total_spend": float(stats.get("total_spend", 0)) if stats.get("total_spend") else 0,
                    "pending_amount": float(stats.get("pending_amount", 0)) if stats.get("pending_amount") else 0,
                    "last_invoice": str(stats.get("last_invoice_date"))
                }
                
                # Check for missing recent invoices
                from datetime import datetime, timedelta
                last_invoice = stats.get("last_invoice_date")
                if last_invoice:
                    try:
                        days_since_invoice = (datetime.now() - datetime.fromisoformat(str(last_invoice)[:10])).days
                        if days_since_invoice > 30:
                            report["alerts"].append({
                                "type": "NO_RECENT_INVOICE",
                                "message": f"No invoice received in {days_since_invoice} days",
                                "severity": "LOW"
                            })
                            report["recommendations"].append("Shall I scan Gmail for recent invoices from this vendor?")
                    except:
                        pass
        except Exception as e:
            report["financials_error"] = str(e)
        
        # Determine overall sync status
        if report["last_sync"]:
            report["sync_status"] = report["last_sync"]["status"]
        elif report["netsuite_internal_id"]:
            report["sync_status"] = "SYNCED"
        else:
            report["sync_status"] = "NOT_SYNCED"
            report["recommendations"].append("This vendor is not synced to NetSuite. Shall I create a vendor record?")
        
        return json.dumps(report, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool 
def get_vendor_full_profile(vendor_name: str) -> str:
    """
    The OMNISCIENT tool - Get EVERYTHING about a vendor in ONE call.
    Combines: database search + NetSuite health + recent invoices with PDF links + proactive alerts.
    
    Use this when user asks "Tell me about [vendor]" or "Who is [vendor]?"
    
    Args:
        vendor_name: The vendor name to look up (e.g., "Replit", "AWS", "Google")
    
    Returns:
        Complete vendor dossier with profile, NetSuite status, invoices, PDF links, and alerts
    """
    try:
        dossier = {
            "vendor_name": vendor_name,
            "profile": None,
            "netsuite_status": None,
            "recent_invoices": [],
            "total_spend": 0,
            "pdf_links": [],
            "proactive_alerts": [],
            "recommendations": []
        }
        
        # 1. Get vendor profile from database
        vendor_query = """
        SELECT 
            vendor_id, global_name, netsuite_id, email, phone, 
            tax_id, address, country, domains, sync_status, created_at
        FROM `invoicereader-477008.vendors_ai.global_vendors`
        WHERE LOWER(global_name) LIKE @search_pattern
        LIMIT 1
        """
        try:
            vendors = bigquery_service.query(vendor_query, {"search_pattern": f"%{vendor_name.lower()}%"})
            if vendors:
                v = vendors[0]
                dossier["profile"] = {
                    "vendor_id": v.get("vendor_id"),
                    "name": v.get("global_name"),
                    "netsuite_id": v.get("netsuite_id"),
                    "email": v.get("email"),
                    "phone": v.get("phone"),
                    "tax_id": v.get("tax_id"),
                    "country": v.get("country"),
                    "domains": v.get("domains"),
                    "status": "Active ✅" if v.get("netsuite_id") else "Not Synced ⚠️"
                }
        except Exception as e:
            dossier["profile_error"] = str(e)
        
        # 2. Get NetSuite health status
        try:
            health_result = check_netsuite_health.invoke({"vendor_name": vendor_name})
            health_data = json.loads(health_result)
            dossier["netsuite_status"] = {
                "synced": health_data.get("sync_status") == "SYNCED" or health_data.get("netsuite_internal_id") is not None,
                "internal_id": health_data.get("netsuite_internal_id"),
                "last_activity": health_data.get("last_activity"),
                "recent_events_count": len(health_data.get("recent_events", [])),
                "pending_balance": health_data.get("financials", {}).get("pending_amount", 0)
            }
            
            # Add any alerts from NetSuite check
            for alert in health_data.get("alerts", []):
                dossier["proactive_alerts"].append(alert)
            for rec in health_data.get("recommendations", []):
                dossier["recommendations"].append(rec)
                
        except Exception as e:
            dossier["netsuite_error"] = str(e)
        
        # 3. Get recent invoices with GCS URIs
        invoice_query = """
        SELECT 
            invoice_id, invoice_number, invoice_date, amount, currency, 
            status, gcs_uri, created_at
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE LOWER(vendor_name) LIKE @search_pattern
        ORDER BY invoice_date DESC
        LIMIT 5
        """
        try:
            invoices = bigquery_service.query(invoice_query, {"search_pattern": f"%{vendor_name.lower()}%"})
            total_spend = 0
            
            for inv in invoices:
                invoice_info = {
                    "invoice_number": inv.get("invoice_number"),
                    "date": str(inv.get("invoice_date")),
                    "amount": float(inv.get("amount", 0)) if inv.get("amount") else 0,
                    "currency": inv.get("currency", "USD"),
                    "status": inv.get("status"),
                    "gcs_uri": inv.get("gcs_uri")
                }
                dossier["recent_invoices"].append(invoice_info)
                total_spend += invoice_info["amount"]
                
                # Generate PDF link if GCS URI exists
                if inv.get("gcs_uri"):
                    try:
                        pdf_result = get_invoice_pdf_link.invoke({"gcs_uri": inv.get("gcs_uri")})
                        pdf_data = json.loads(pdf_result)
                        if pdf_data.get("success"):
                            dossier["pdf_links"].append({
                                "invoice": inv.get("invoice_number"),
                                "link": pdf_data.get("html_link")
                            })
                    except:
                        pass
            
            dossier["total_spend"] = total_spend
            
            # Check for missing recent invoices
            if invoices:
                from datetime import datetime
                last_date = invoices[0].get("invoice_date")
                if last_date:
                    try:
                        days_ago = (datetime.now() - datetime.fromisoformat(str(last_date)[:10])).days
                        if days_ago > 30:
                            dossier["proactive_alerts"].append({
                                "type": "MISSING_INVOICE",
                                "message": f"No invoice received from {vendor_name} in {days_ago} days",
                                "severity": "MEDIUM"
                            })
                            dossier["recommendations"].append(f"Shall I scan Gmail specifically for recent {vendor_name} invoices?")
                    except:
                        pass
                        
        except Exception as e:
            dossier["invoices_error"] = str(e)
        
        # 4. Format the complete response
        summary = {
            "vendor_profile": dossier["profile"],
            "netsuite_status": dossier["netsuite_status"],
            "financials": {
                "total_spend": dossier["total_spend"],
                "recent_invoices_count": len(dossier["recent_invoices"]),
                "invoices": dossier["recent_invoices"]
            },
            "documents": dossier["pdf_links"],
            "proactive_alerts": dossier["proactive_alerts"],
            "recommendations": dossier["recommendations"]
        }
        
        return json.dumps(summary, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_all_tools():
    """Return list of all available tools for the agent - OMNISCIENT SEMANTIC AI FIRST ORDER"""
    return [
        # Omniscient Tools (use these first for comprehensive answers)
        get_vendor_full_profile,
        deep_search,
        get_invoice_pdf_link,
        check_netsuite_health,
        # Database First
        search_database_first,
        get_top_vendors_by_spend,
        # Gmail
        check_gmail_status,
        search_gmail_invoices,
        # NetSuite
        create_netsuite_bill,
        search_netsuite_vendor,
        get_bill_status,
        create_netsuite_vendor,
        # Utilities
        match_vendor_to_database,
        run_bigquery,
        get_subscription_summary
    ]
