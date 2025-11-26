"""
LangGraph Tools - Wraps existing services for LLM control
SEMANTIC AI FIRST: Always check database before external services
MULTI-TENANT: All tools filter by owner_email for data isolation
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


def _check_gmail_connected(user_email: str = None):
    """Check if Gmail is connected - checks BOTH session and database storage"""
    try:
        from flask import session
        session_token = session.get('gmail_session_token')
        if session_token:
            from services.token_storage import SecureTokenStorage
            token_storage = SecureTokenStorage()
            credentials = token_storage.get_credentials(session_token)
            if credentials:
                return True
        
        if user_email:
            gmail = GmailService(owner_email=user_email)
            if gmail.is_connected_for_user():
                return True
        
        return False
    except Exception as e:
        print(f"Error checking Gmail connection: {e}")
        return False


@tool
def get_dashboard_status(user_email: str) -> str:
    """
    Get a comprehensive dashboard status - CALL THIS ON STARTUP.
    Returns vendor count, invoice count, Gmail status, NetSuite status, and recent activity.
    Use this to greet users proactively with their current data status.
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
    
    Returns:
        JSON with complete dashboard status for proactive greeting
    """
    try:
        gmail_connected = _check_gmail_connected(user_email)
        status = {
            "user_email": user_email,
            "gmail_connected": gmail_connected,
            "gmail_auth_url": _get_gmail_connect_url() if not gmail_connected else None,
            "vendor_count": 0,
            "invoice_count": 0,
            "pending_invoices": 0,
            "recent_invoices": [],
            "netsuite_connected": False,
            "suggested_actions": []
        }
        
        # Get vendor count
        try:
            vendor_query = f"""
            SELECT COUNT(*) as count 
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE owner_email = @user_email
            """
            results = bigquery_service.query(vendor_query, {"user_email": user_email})
            if results:
                status["vendor_count"] = results[0].get("count", 0)
        except Exception as e:
            print(f"Error getting vendor count: {e}")
        
        # Get invoice counts
        try:
            invoice_query = f"""
            SELECT 
                COUNT(*) as total,
                COUNTIF(status = 'pending' OR status IS NULL) as pending
            FROM `invoicereader-477008.vendors_ai.invoices`
            WHERE owner_email = @user_email OR owner_email IS NULL
            """
            results = bigquery_service.query(invoice_query, {"user_email": user_email})
            if results:
                status["invoice_count"] = results[0].get("total", 0)
                status["pending_invoices"] = results[0].get("pending", 0)
        except Exception as e:
            print(f"Error getting invoice count: {e}")
        
        # Get recent invoices (last 5)
        try:
            recent_query = f"""
            SELECT invoice_id, vendor_name, amount, currency, created_at, status
            FROM `invoicereader-477008.vendors_ai.invoices`
            WHERE owner_email = @user_email OR owner_email IS NULL
            ORDER BY created_at DESC
            LIMIT 5
            """
            results = bigquery_service.query(recent_query, {"user_email": user_email})
            if results:
                for r in results:
                    status["recent_invoices"].append({
                        "id": r.get("invoice_id"),
                        "vendor": r.get("vendor_name"),
                        "amount": float(r.get("amount", 0)) if r.get("amount") else 0,
                        "currency": r.get("currency", "USD"),
                        "status": r.get("status", "pending")
                    })
        except Exception as e:
            print(f"Error getting recent invoices: {e}")
        
        # Check NetSuite connection
        try:
            status["netsuite_connected"] = netsuite_service.test_connection().get("connected", False)
        except:
            status["netsuite_connected"] = False
        
        # Build suggested actions based on status
        if not status["gmail_connected"]:
            status["suggested_actions"].append({
                "action": "connect_gmail",
                "label": "Connect Gmail to scan invoices",
                "priority": "high"
            })
        else:
            status["suggested_actions"].append({
                "action": "scan_gmail",
                "label": "Scan Gmail for new invoices",
                "priority": "medium"
            })
        
        if status["pending_invoices"] > 0:
            status["suggested_actions"].append({
                "action": "review_pending",
                "label": f"Review {status['pending_invoices']} pending invoices",
                "priority": "high"
            })
        
        if status["vendor_count"] == 0:
            status["suggested_actions"].append({
                "action": "import_vendors",
                "label": "Import vendors from CSV or NetSuite",
                "priority": "high"
            })
        
        return json.dumps(status, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e), "user_email": user_email})


@tool
def check_gmail_status(user_email: str) -> str:
    """
    Check if Gmail is connected and get connection URL if needed.
    Use this FIRST before trying to search Gmail.
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
    
    Returns:
        JSON with connection status and auth URL if not connected
    """
    try:
        is_connected = _check_gmail_connected(user_email)
        
        if is_connected:
            return json.dumps({
                "connected": True,
                "message": "Gmail is connected and ready to use",
                "user_email": user_email
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
def search_database_first(user_email: str, query: str, search_type: str = "all") -> str:
    """
    SEMANTIC AI FIRST: Search the local database before using external services.
    This tool searches BigQuery for existing invoices, vendors, and subscriptions.
    
    Use this BEFORE calling Gmail or other external services!
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        query: Search term (vendor name, invoice number, email, etc.)
        search_type: "vendors", "invoices", "subscriptions", or "all"
    
    Returns:
        JSON with search results from database
    """
    try:
        if not query or len(query.strip()) == 0:
            return json.dumps({"error": "Invalid or empty search query"})
        
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        search_pattern = f"%{query.strip().lower()}%"
        
        results = {
            "searched_database": True,
            "query": query,
            "user_email": user_email,
            "vendors": [],
            "invoices": [],
            "subscriptions": []
        }
        
        if search_type in ["vendors", "all"]:
            vendor_query = """
            SELECT vendor_id, global_name, normalized_name, emails, domains, netsuite_internal_id, source_system
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE owner_email = @user_email
              AND (LOWER(global_name) LIKE @search_pattern
               OR LOWER(normalized_name) LIKE @search_pattern
               OR LOWER(ARRAY_TO_STRING(emails, ',')) LIKE @search_pattern
               OR LOWER(ARRAY_TO_STRING(domains, ',')) LIKE @search_pattern)
            LIMIT 10
            """
            try:
                vendor_results = bigquery_service.query(vendor_query, {
                    "search_pattern": search_pattern,
                    "user_email": user_email
                })
                results["vendors"] = vendor_results
            except Exception as e:
                results["vendor_error"] = str(e)
        
        if search_type in ["subscriptions", "all"]:
            sub_query = """
            SELECT vendor_name, amount, currency, timestamp, event_type
            FROM `invoicereader-477008.vendors_ai.subscription_events`
            WHERE owner_email = @user_email
              AND LOWER(vendor_name) LIKE @search_pattern
            ORDER BY timestamp DESC
            LIMIT 10
            """
            try:
                sub_results = bigquery_service.query(sub_query, {
                    "search_pattern": search_pattern,
                    "user_email": user_email
                })
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
def get_top_vendors_by_spend(user_email: str, limit: int = 10) -> str:
    """
    Get the top vendors by total payment amount from the INVOICES table.
    Use this for questions about "top vendors", "who did I pay most", "spending analysis".
    
    IMPORTANT: This queries the invoices table (actual financial data), 
    NOT the netsuite_events table (which is just API logs).
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        limit: Number of top vendors to return (default: 10)
    
    Returns:
        JSON with top vendors ranked by total spend
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        query = """
        SELECT 
            vendor_name,
            SUM(amount) as total_spend,
            COUNT(*) as invoice_count,
            MAX(invoice_date) as last_invoice_date,
            STRING_AGG(DISTINCT currency, ', ') as currencies
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE owner_email = @user_email
          AND vendor_name IS NOT NULL 
          AND amount IS NOT NULL
        GROUP BY vendor_name
        ORDER BY total_spend DESC
        LIMIT @limit
        """
        
        results = bigquery_service.query(query, {"limit": limit, "user_email": user_email})
        
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
def search_gmail_invoices(user_email: str, days: int = 7, max_results: int = 20, access_token: Optional[str] = None) -> str:
    """
    Search Gmail for invoice and receipt emails with ROBUST date handling.
    IMPORTANT: Check database first with search_database_first, then use check_gmail_status before this tool!
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        days: Number of days to look back (default: 7 for better reliability)
        max_results: Maximum number of emails to return (default: 20)
        access_token: Optional Gmail access token (uses stored token if not provided)
    
    Returns:
        JSON string with list of invoice emails found, including subject, sender, date, and snippet
    """
    from datetime import datetime, timedelta
    
    after_date = None
    
    try:
        from flask import session
        stored_token = session.get('gmail_token') if not access_token else None
        token_to_use = access_token or (stored_token.get('token') if stored_token else None)
        
        if not token_to_use:
            auth_url = _get_gmail_connect_url()
            return json.dumps({
                "error": "Gmail not connected",
                "action_required": True,
                "message": "I need to connect to Gmail to search your emails.",
                "auth_url": auth_url,
                "html_button": f'<a href="{auth_url}" target="_blank" class="chat-action-btn">Connect Gmail Now</a>'
            })
        
        try:
            service = gmail_service.build_service(stored_token or {'token': token_to_use})
        except Exception as build_error:
            return json.dumps({
                "error": f"Failed to build Gmail service: {str(build_error)}",
                "error_type": "SERVICE_BUILD_FAILED",
                "suggestion": "Your Gmail token may have expired. Try reconnecting Gmail.",
                "action_required": True
            })
        
        if not service:
            return json.dumps({
                "error": "Failed to build Gmail service - service is None",
                "error_type": "SERVICE_NULL",
                "suggestion": "Try disconnecting and reconnecting Gmail"
            })
        
        try:
            if days < 1:
                days = 1
            elif days > 365:
                days = 365
            
            after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
            print(f"📧 Gmail search for {user_email}: Looking for invoices after {after_date} (last {days} days)")
            
            messages = gmail_service.search_invoice_emails(service, max_results=max_results, days=days)
            
        except Exception as search_error:
            error_str = str(search_error)
            
            if 'invalid_grant' in error_str.lower() or 'token' in error_str.lower():
                return json.dumps({
                    "error": f"Gmail token expired or invalid: {error_str}",
                    "error_type": "TOKEN_EXPIRED",
                    "action_required": True,
                    "suggestion": "Your Gmail session has expired. Please reconnect.",
                    "html_button": '<a href="/gmail/connect" class="chat-action-btn">Reconnect Gmail</a>'
                })
            elif 'quota' in error_str.lower() or 'rate' in error_str.lower():
                return json.dumps({
                    "error": f"Gmail API rate limit: {error_str}",
                    "error_type": "RATE_LIMIT",
                    "suggestion": "Too many requests. Please wait a minute and try again."
                })
            else:
                return json.dumps({
                    "error": f"Gmail search failed: {error_str}",
                    "error_type": "SEARCH_FAILED",
                    "query_info": f"Searched for invoices after {after_date or 'unknown'}",
                    "suggestion": "Try again with a shorter time range (e.g., last 7 days)"
                })
        
        if not messages:
            return json.dumps({
                "success": True,
                "total_found": 0,
                "emails": [],
                "message": f"No invoice emails found in the last {days} days.",
                "search_date_range": f"after:{after_date}",
                "suggestion": "Try extending the search range or check if invoices go to a different folder"
            })
        
        results = []
        for msg in messages[:10]:
            try:
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
            except Exception as msg_error:
                print(f"⚠️ Error processing message {msg.get('id')}: {msg_error}")
                continue
        
        return json.dumps({
            "success": True,
            "total_found": len(messages),
            "emails": results,
            "user_email": user_email,
            "search_info": {
                "days_searched": days,
                "date_range": f"after:{after_date}",
                "max_results": max_results
            }
        }, indent=2)
        
    except Exception as e:
        import traceback
        return json.dumps({
            "error": str(e),
            "error_type": "UNEXPECTED_ERROR",
            "traceback": traceback.format_exc(),
            "suggestion": "An unexpected error occurred. Check the logs for details."
        })


@tool
def create_netsuite_bill(
    user_email: str,
    vendor_netsuite_id: str,
    invoice_number: str,
    amount: float,
    currency: str = "USD",
    memo: str = ""
) -> str:
    """
    Create a vendor bill in NetSuite.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
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
            'owner_email': user_email,
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
                "message": f"Successfully created bill for ${amount} {currency}",
                "user_email": user_email
            }, indent=2)
        else:
            return json.dumps({"success": False, "error": "Failed to create bill in NetSuite"})
            
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def search_netsuite_vendor(
    user_email: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    tax_id: Optional[str] = None
) -> str:
    """
    Search for a vendor in NetSuite by name, email, or tax ID.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
        name: Vendor company name to search for
        email: Vendor email address to search for
        tax_id: Vendor tax/VAT ID to search for
    
    Returns:
        JSON string with vendor details if found, or not found message
    """
    try:
        result = netsuite_service.lookup_vendor_integrated(
            name=name or "",
            email=email or "",
            tax_id=tax_id or ""
        )
        
        if result:
            return json.dumps({
                "found": True,
                "vendor": {
                    "netsuite_id": result.get('id'),
                    "name": result.get('companyName'),
                    "email": result.get('email'),
                    "tax_id": result.get('vatRegNumber')
                },
                "user_email": user_email
            }, indent=2)
        else:
            return json.dumps({
                "found": False,
                "message": f"No vendor found matching the criteria"
            })
            
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_bill_status(user_email: str, invoice_id: str) -> str:
    """
    Get the status of a bill in NetSuite by invoice ID.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
        invoice_id: The invoice ID to check status for
    
    Returns:
        JSON string with bill status (exists, approval_status, amount, etc.)
    """
    try:
        result = netsuite_service.get_bill_status(invoice_id)
        result['user_email'] = user_email
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def match_vendor_to_database(
    user_email: str,
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
        user_email: The logged-in user's email for multi-tenant filtering
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
            'country': country,
            'owner_email': user_email
        }
        
        result = vendor_matcher.match_vendor(invoice_data)
        
        return json.dumps({
            "verdict": result.get('verdict'),
            "vendor_id": result.get('vendor_id'),
            "confidence": result.get('confidence'),
            "reasoning": result.get('reasoning'),
            "method": result.get('method'),
            "risk_analysis": result.get('risk_analysis'),
            "user_email": user_email
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def run_bigquery(user_email: str, sql_query: str) -> str:
    """
    Execute a SQL query on BigQuery to analyze vendor data, subscriptions, or invoices.
    
    IMPORTANT: Only SELECT queries are allowed. No INSERT, UPDATE, DELETE, or DROP.
    NOTE: All queries are automatically filtered by owner_email for multi-tenant security.
    
    Available tables:
    - vendors_ai.global_vendors: Master vendor database
    - vendors_ai.subscription_vendors: SaaS subscription vendors
    - vendors_ai.subscription_events: Subscription payment events
    - vendors_ai.netsuite_events: NetSuite sync events
    - vendors_ai.invoices: Invoice records
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        sql_query: The SQL SELECT query to execute
    
    Returns:
        JSON string with query results or error
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        sql_upper = sql_query.upper().strip()
        if any(keyword in sql_upper for keyword in ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER']):
            return json.dumps({"error": "Only SELECT queries are allowed for safety"})
        
        tables_to_filter = [
            'global_vendors',
            'subscription_vendors', 
            'subscription_events',
            'netsuite_events',
            'invoices',
            'netsuite_sync_log'
        ]
        
        modified_query = sql_query
        for table in tables_to_filter:
            if table.lower() in sql_query.lower():
                if 'WHERE' in sql_upper:
                    modified_query = modified_query.replace(
                        'WHERE', 
                        f'WHERE owner_email = "{user_email}" AND ', 
                        1
                    )
                else:
                    if 'GROUP BY' in sql_upper:
                        modified_query = modified_query.replace(
                            'GROUP BY',
                            f'WHERE owner_email = "{user_email}" GROUP BY',
                            1
                        )
                    elif 'ORDER BY' in sql_upper:
                        modified_query = modified_query.replace(
                            'ORDER BY',
                            f'WHERE owner_email = "{user_email}" ORDER BY',
                            1
                        )
                    elif 'LIMIT' in sql_upper:
                        modified_query = modified_query.replace(
                            'LIMIT',
                            f'WHERE owner_email = "{user_email}" LIMIT',
                            1
                        )
                    else:
                        modified_query = modified_query.rstrip(';') + f' WHERE owner_email = "{user_email}"'
                break
        
        results = bigquery_service.query(modified_query)
        
        return json.dumps({
            "success": True,
            "row_count": len(results),
            "results": results[:100],
            "user_email": user_email
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_subscription_summary(user_email: str) -> str:
    """
    Get a summary of all active SaaS subscriptions from Subscription Pulse.
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
    
    Returns:
        JSON string with subscription summary including count, total spend, and top vendors
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        query = """
        SELECT 
            vendor_name,
            SUM(amount) as total_spend,
            COUNT(*) as payment_count,
            MAX(timestamp) as last_payment,
            MIN(timestamp) as first_payment
        FROM `invoicereader-477008.vendors_ai.subscription_events`
        WHERE owner_email = @user_email
        GROUP BY vendor_name
        ORDER BY total_spend DESC
        LIMIT 20
        """
        
        results = bigquery_service.query(query, {"user_email": user_email})
        
        total_spend = sum(r.get('total_spend', 0) for r in results)
        
        return json.dumps({
            "success": True,
            "vendor_count": len(results),
            "total_annual_spend": total_spend,
            "top_subscriptions": results,
            "user_email": user_email
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool 
def create_netsuite_vendor(
    user_email: str,
    company_name: str,
    email: Optional[str] = None,
    tax_id: Optional[str] = None,
    phone: Optional[str] = None
) -> str:
    """
    Create a new vendor in NetSuite.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
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
            'phone': phone,
            'owner_email': user_email
        }
        
        result = netsuite_service.create_vendor(vendor_data)
        result['user_email'] = user_email
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


# ========== OMNISCIENT TOOLS - SEMANTIC AI FIRST ==========

@tool
def deep_search(user_email: str, query: str, search_type: str = "all") -> str:
    """
    Deep semantic search using Vertex AI Search - the 'Deep Swimmer' that finds connections SQL cannot.
    Use this for vague queries like "that expensive software bill" or "invoices from last month".
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        query: Natural language search query (e.g., "expensive software invoice", "Replit bills")
        search_type: Type of search - "vendors", "invoices", or "all" (default: "all")
    
    Returns:
        JSON with semantic search results including vendor matches, invoice data, and GCS URIs for PDFs
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        results = {
            "query": query,
            "search_type": search_type,
            "user_email": user_email,
            "vendors": [],
            "invoices": [],
            "total_found": 0
        }
        
        if search_type in ["vendors", "all"]:
            vendor_results = vertex_search_service.search_vendor(query, max_results=5)
            for r in vendor_results:
                data = r.get('data', {})
                if not data.get('is_rejected_entity') and data.get('owner_email') == user_email:
                    results["vendors"].append({
                        "vendor_name": data.get('vendor_name'),
                        "vendor_id": data.get('vendor_id'),
                        "netsuite_id": data.get('netsuite_id'),
                        "country": data.get('country'),
                        "last_invoice_amount": data.get('last_invoice_amount'),
                        "domains": data.get('domains')
                    })
        
        if search_type in ["invoices", "all"]:
            invoice_results = vertex_search_service.search_similar_invoices(query, limit=5)
            for r in invoice_results:
                data = r.get('data', {})
                if data.get('owner_email') == user_email:
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
        
        if search_type in ["invoices", "all"]:
            bq_query = """
            SELECT 
                invoice_id, vendor_name, invoice_number, invoice_date, 
                amount, currency, gcs_uri, status
            FROM `invoicereader-477008.vendors_ai.invoices`
            WHERE owner_email = @user_email
              AND (LOWER(vendor_name) LIKE @search_pattern 
               OR LOWER(invoice_number) LIKE @search_pattern)
            ORDER BY invoice_date DESC
            LIMIT 5
            """
            search_pattern = f"%{query.lower()}%"
            try:
                bq_results = bigquery_service.query(bq_query, {
                    "search_pattern": search_pattern,
                    "user_email": user_email
                })
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
def get_invoice_pdf_link(user_email: str, gcs_uri: str) -> str:
    """
    Convert a GCS URI (gs://bucket/path) to a clickable HTTPS signed URL valid for 1 hour.
    ALWAYS use this when showing invoices to provide the actual PDF link.
    
    Args:
        user_email: The logged-in user's email for multi-tenant validation
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
        
        uri_without_prefix = gcs_uri[5:]
        parts = uri_without_prefix.split('/', 1)
        
        if len(parts) != 2:
            return json.dumps({"error": "Invalid GCS URI format. Expected gs://bucket/path"})
        
        bucket_name = parts[0]
        blob_name = parts[1]
        
        from google.cloud import storage
        from datetime import timedelta
        from google.oauth2 import service_account
        
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
        
        file_extension = blob_name.split('.')[-1].lower() if '.' in blob_name else 'pdf'
        content_type_map = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg'
        }
        content_type = content_type_map.get(file_extension, 'application/octet-stream')
        
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET",
            response_type=content_type
        )
        
        filename = blob_name.split('/')[-1] if '/' in blob_name else blob_name
        
        return json.dumps({
            "success": True,
            "gcs_uri": gcs_uri,
            "download_url": signed_url,
            "expires_in": "1 hour",
            "file_type": file_extension,
            "html_link": f'<a href="{signed_url}" target="_blank" class="chat-action-btn">📄 View {filename}</a>',
            "user_email": user_email
        })
        
    except Exception as e:
        return json.dumps({"error": str(e), "gcs_uri": gcs_uri})


@tool
def check_netsuite_health(user_email: str, vendor_id: Optional[str] = None, vendor_name: Optional[str] = None) -> str:
    """
    The 'NetSuite Detective' - Get the FULL story of a vendor's NetSuite sync status.
    Don't just say "Synced" - tell the complete health story including last activity, balance, and any issues.
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        vendor_id: Optional vendor ID to check (e.g., V2099)
        vendor_name: Optional vendor name to search for
    
    Returns:
        Full health report: sync status, last activity, events history, outstanding balance, and alerts
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        report = {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "user_email": user_email,
            "sync_status": None,
            "netsuite_internal_id": None,
            "last_sync": None,
            "last_activity": None,
            "recent_events": [],
            "alerts": [],
            "recommendations": []
        }
        
        if vendor_name and not vendor_id:
            vendor_query = """
            SELECT vendor_id, global_name, netsuite_internal_id, emails, domains, source_system
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE owner_email = @user_email
              AND LOWER(global_name) LIKE @search_pattern
            LIMIT 1
            """
            results = bigquery_service.query(vendor_query, {
                "search_pattern": f"%{vendor_name.lower()}%",
                "user_email": user_email
            })
            if results:
                vendor = results[0]
                vendor_id = vendor.get('vendor_id')
                ns_id = vendor.get('netsuite_internal_id')
                report["vendor_id"] = vendor_id
                report["vendor_name"] = vendor.get('global_name')
                report["netsuite_internal_id"] = ns_id
                report["sync_status"] = "SYNCED" if ns_id else "NOT_SYNCED"
        
        if not vendor_id:
            return json.dumps({
                "error": "Could not find vendor. Please provide vendor_id or a valid vendor_name.",
                "suggestion": "Use search_database_first to find the vendor first."
            })
        
        sync_log_query = """
        SELECT 
            action, status, timestamp, error_message, entity_type, entity_id, netsuite_id
        FROM `invoicereader-477008.vendors_ai.netsuite_sync_log`
        WHERE owner_email = @user_email
          AND (entity_id = @vendor_id 
           OR LOWER(TO_JSON_STRING(request_data)) LIKE @vendor_pattern
           OR LOWER(TO_JSON_STRING(response_data)) LIKE @vendor_pattern)
        ORDER BY timestamp DESC
        LIMIT 5
        """
        try:
            sync_logs = bigquery_service.query(sync_log_query, {
                "vendor_id": vendor_id,
                "vendor_pattern": f"%{(vendor_name or '').lower()}%",
                "user_email": user_email
            })
            
            if sync_logs:
                last_sync = sync_logs[0]
                report["last_sync"] = {
                    "action": last_sync.get("action"),
                    "status": last_sync.get("status"),
                    "timestamp": str(last_sync.get("timestamp")),
                    "entity_type": last_sync.get("entity_type"),
                    "netsuite_id": last_sync.get("netsuite_id")
                }
                
                if last_sync.get("status") == "ERROR":
                    report["alerts"].append({
                        "type": "SYNC_FAILED",
                        "message": f"Last sync failed: {last_sync.get('error_message', 'Unknown error')}",
                        "severity": "HIGH"
                    })
                    report["recommendations"].append("Shall I retry the sync?")
        except Exception as e:
            report["sync_log_error"] = str(e)
        
        events_query = """
        SELECT 
            event_type, entity_type, netsuite_id, status, 
            timestamp, error_message
        FROM `invoicereader-477008.vendors_ai.netsuite_events`
        WHERE owner_email = @user_email
          AND (entity_id = @vendor_id
           OR LOWER(TO_JSON_STRING(request_data)) LIKE @vendor_pattern
           OR LOWER(TO_JSON_STRING(response_data)) LIKE @vendor_pattern)
        ORDER BY timestamp DESC
        LIMIT 10
        """
        try:
            events = bigquery_service.query(events_query, {
                "vendor_id": vendor_id,
                "vendor_pattern": f"%{(vendor_name or vendor_id).lower()}%",
                "user_email": user_email
            })
            
            for event in events:
                event_summary = {
                    "type": event.get("event_type"),
                    "entity_type": event.get("entity_type"),
                    "status": event.get("status"),
                    "timestamp": str(event.get("timestamp")),
                    "netsuite_id": event.get("netsuite_id")
                }
                report["recent_events"].append(event_summary)
                
                if not report["last_activity"] and events:
                    first_event = events[0]
                    report["last_activity"] = f"{first_event.get('event_type')} ({first_event.get('entity_type')}) on {str(first_event.get('timestamp'))[:10]}"
            
            failed_events = [e for e in events if e.get("status") == "ERROR"]
            if failed_events:
                report["alerts"].append({
                    "type": "RECENT_ERRORS",
                    "message": f"{len(failed_events)} recent NetSuite operations failed",
                    "severity": "MEDIUM"
                })
                
        except Exception as e:
            report["events_error"] = str(e)
        
        invoice_query = """
        SELECT 
            COUNT(*) as invoice_count,
            SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END) as pending_amount,
            SUM(amount) as total_spend,
            MAX(invoice_date) as last_invoice_date
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE owner_email = @user_email
          AND LOWER(vendor_name) LIKE @vendor_pattern
        """
        try:
            invoice_stats = bigquery_service.query(invoice_query, {
                "vendor_pattern": f"%{(vendor_name or '').lower()}%",
                "user_email": user_email
            })
            if invoice_stats:
                stats = invoice_stats[0]
                report["financials"] = {
                    "total_invoices": stats.get("invoice_count"),
                    "total_spend": float(stats.get("total_spend", 0)) if stats.get("total_spend") else 0,
                    "pending_amount": float(stats.get("pending_amount", 0)) if stats.get("pending_amount") else 0,
                    "last_invoice": str(stats.get("last_invoice_date"))
                }
                
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
def get_vendor_full_profile(user_email: str, vendor_name: str) -> str:
    """
    The OMNISCIENT tool - Get EVERYTHING about a vendor in ONE call.
    Combines: database search + NetSuite health + recent invoices with PDF links + proactive alerts.
    
    Use this when user asks "Tell me about [vendor]" or "Who is [vendor]?"
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        vendor_name: The vendor name to look up (e.g., "Replit", "AWS", "Google")
    
    Returns:
        Complete vendor dossier with profile, NetSuite status, invoices, PDF links, and alerts
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        dossier = {
            "vendor_name": vendor_name,
            "user_email": user_email,
            "profile": None,
            "netsuite_status": None,
            "recent_invoices": [],
            "total_spend": 0,
            "pdf_links": [],
            "proactive_alerts": [],
            "recommendations": []
        }
        
        vendor_query = """
        SELECT 
            vendor_id, global_name, netsuite_internal_id, emails, 
            custom_attributes, countries, domains, source_system, created_at
        FROM `invoicereader-477008.vendors_ai.global_vendors`
        WHERE owner_email = @user_email
          AND LOWER(global_name) LIKE @search_pattern
        LIMIT 1
        """
        try:
            vendors = bigquery_service.query(vendor_query, {
                "search_pattern": f"%{vendor_name.lower()}%",
                "user_email": user_email
            })
            if vendors:
                v = vendors[0]
                custom_attrs = v.get("custom_attributes") or {}
                dossier["profile"] = {
                    "vendor_id": v.get("vendor_id"),
                    "name": v.get("global_name"),
                    "netsuite_id": v.get("netsuite_internal_id"),
                    "email": v.get("emails", [None])[0] if v.get("emails") else None,
                    "phone": custom_attrs.get("phone") if isinstance(custom_attrs, dict) else None,
                    "tax_id": custom_attrs.get("tax_id") if isinstance(custom_attrs, dict) else None,
                    "country": v.get("countries", [None])[0] if v.get("countries") else None,
                    "domains": v.get("domains"),
                    "status": "Active ✅" if v.get("netsuite_internal_id") else "Not Synced ⚠️"
                }
        except Exception as e:
            dossier["profile_error"] = str(e)
        
        try:
            health_result = check_netsuite_health.invoke({"user_email": user_email, "vendor_name": vendor_name})
            health_data = json.loads(health_result)
            dossier["netsuite_status"] = {
                "synced": health_data.get("sync_status") == "SYNCED" or health_data.get("netsuite_internal_id") is not None,
                "internal_id": health_data.get("netsuite_internal_id"),
                "last_activity": health_data.get("last_activity"),
                "recent_events_count": len(health_data.get("recent_events", [])),
                "pending_balance": health_data.get("financials", {}).get("pending_amount", 0)
            }
            
            for alert in health_data.get("alerts", []):
                dossier["proactive_alerts"].append(alert)
            for rec in health_data.get("recommendations", []):
                dossier["recommendations"].append(rec)
                
        except Exception as e:
            dossier["netsuite_error"] = str(e)
        
        invoice_query = """
        SELECT 
            invoice_id, invoice_number, invoice_date, amount, currency, 
            status, gcs_uri, created_at
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE owner_email = @user_email
          AND LOWER(vendor_name) LIKE @search_pattern
        ORDER BY invoice_date DESC
        LIMIT 5
        """
        try:
            invoices = bigquery_service.query(invoice_query, {
                "search_pattern": f"%{vendor_name.lower()}%",
                "user_email": user_email
            })
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
                
                if inv.get("gcs_uri"):
                    try:
                        pdf_result = get_invoice_pdf_link.invoke({"user_email": user_email, "gcs_uri": inv.get("gcs_uri")})
                        pdf_data = json.loads(pdf_result)
                        if pdf_data.get("success"):
                            dossier["pdf_links"].append({
                                "invoice": inv.get("invoice_number"),
                                "link": pdf_data.get("html_link")
                            })
                    except:
                        pass
            
            dossier["total_spend"] = total_spend
            
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
            "recommendations": dossier["recommendations"],
            "user_email": user_email
        }
        
        return json.dumps(summary, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


# ========== INGESTION TOOLS - FILE PROCESSING ==========

@tool
def process_uploaded_invoice(user_email: str, file_path: str) -> str:
    """
    Process an uploaded invoice PDF through the FULL extraction pipeline.
    Uses the EXACT SAME technology as Gmail tab and Invoice tab:
    - Document AI for OCR extraction
    - Vertex AI Search RAG for historical context
    - Gemini for semantic validation
    - VendorMatcher for AI-powered vendor matching (Supreme Judge)
    - BigQuery for invoice storage
    - GCS for permanent file storage
    
    AUTOMATICALLY CALL THIS when user uploads a PDF file.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
        file_path: Path to the uploaded PDF file (e.g., "uploads/abc123_invoice.pdf")
    
    Returns:
        Complete extraction results with vendor match, PDF URL, and action buttons
    """
    try:
        import sys
        sys.path.insert(0, '.')
        from invoice_processor import InvoiceProcessor
        from services.bigquery_service import BigQueryService
        from services.vertex_search_service import VertexSearchService
        from services.gemini_service import GeminiService
        from services.vendor_matcher import VendorMatcher
        from google.cloud import storage
        from datetime import datetime
        import uuid
        
        if not os.path.exists(file_path):
            return json.dumps({
                "error": f"File not found: {file_path}",
                "suggestion": "The file may have been moved or deleted."
            })
        
        print(f"\n{'='*60}")
        print(f"📄 AGENT INVOICE PROCESSING: {file_path}")
        print(f"👤 User: {user_email}")
        print(f"{'='*60}\n")
        
        # ========== STEP 1: FULL 3-LAYER EXTRACTION (Document AI + Vertex + Gemini) ==========
        print("🔍 STEP 1: Running full 3-layer extraction pipeline...")
        processor = InvoiceProcessor()
        result = processor.process_local_file(file_path)
        
        if result.get('status') != 'completed':
            return json.dumps({
                "success": False,
                "error": result.get('error', 'Unknown extraction error'),
                "file_path": file_path
            })
        
        print("✅ Extraction complete!")
        
        # Extract validated data
        validated_data = result.get('validated_data', {}) or {}
        vendor_data = validated_data.get('vendor', {}) or {}
        vendor_name = vendor_data.get('name', 'Unknown Vendor')
        vendor_email = vendor_data.get('email', '')
        vendor_address = vendor_data.get('address', '')
        vendor_tax_id = vendor_data.get('taxId', '')
        vendor_country = vendor_data.get('country', '')
        vendor_phone = vendor_data.get('phone', '')
        
        invoice_number = validated_data.get('invoiceNumber', 'N/A')
        invoice_date = validated_data.get('documentDate', '')
        due_date = validated_data.get('dueDate', '')
        
        totals = validated_data.get('totals', {}) or {}
        total = totals.get('total', 0)
        subtotal = totals.get('subtotal', total)
        tax = totals.get('tax', 0)
        currency = validated_data.get('currency', 'USD')
        
        line_items = validated_data.get('lineItems', []) or []
        
        confidence_val = validated_data.get('extractionConfidence', 0)
        confidence = (confidence_val if isinstance(confidence_val, (int, float)) else 0) * 100
        
        gcs_uri = result.get('gcs_uri', '')
        
        # ========== STEP 2: VENDOR MATCHING (Same as Gmail tab - VendorMatcher + Supreme Judge) ==========
        print(f"\n⚖️ STEP 2: Running VendorMatcher for '{vendor_name}'...")
        
        vendor_match_result = None
        match_verdict = 'NEW_VENDOR'
        matched_vendor_id = None
        matched_vendor_name = vendor_name
        netsuite_id = None
        match_confidence = 0
        match_reasoning = ''
        candidates = []
        
        if vendor_name and vendor_name != 'Unknown Vendor':
            try:
                bigquery_svc = BigQueryService()
                vertex_search_svc = VertexSearchService()
                gemini_svc = GeminiService()
                
                vendor_matcher = VendorMatcher(bigquery_svc, vertex_search_svc, gemini_svc)
                
                # Build invoice vendor data (same as Gmail tab)
                email_domain = None
                if vendor_email and '@' in vendor_email:
                    try:
                        email_domain = vendor_email.split('@')[-1]
                    except:
                        pass
                
                invoice_data = {
                    'vendor_name': vendor_name,
                    'tax_id': vendor_tax_id,
                    'address': vendor_address,
                    'email_domain': email_domain,
                    'phone': vendor_phone,
                    'country': vendor_country
                }
                
                # Run vendor matching (same as Gmail tab)
                match_result = vendor_matcher.match_vendor(invoice_data)
                
                if match_result:
                    match_verdict = match_result.get('verdict', 'NEW_VENDOR')
                    matched_vendor_id = match_result.get('vendor_id')
                    matched_vendor_name = match_result.get('vendor_name', vendor_name)
                    netsuite_id = match_result.get('netsuite_id')
                    match_confidence = match_result.get('confidence', 0)
                    match_reasoning = match_result.get('reasoning', '')
                    candidates = match_result.get('candidates', [])
                    
                    print(f"✅ Vendor match result: {match_verdict} (confidence: {match_confidence}%)")
                    if matched_vendor_id:
                        print(f"   Matched to: {matched_vendor_name} (ID: {matched_vendor_id})")
                    if netsuite_id:
                        print(f"   NetSuite ID: {netsuite_id}")
                else:
                    print("⚠️ No vendor match found - new vendor")
                    
            except Exception as match_err:
                print(f"⚠️ Vendor matching error (non-fatal): {match_err}")
        else:
            print("⚠️ Vendor name is unknown - skipping matching")
        
        # ========== STEP 3: GENERATE PDF URL (Same as Gmail tab) ==========
        print("\n📎 STEP 3: Generating PDF download URL...")
        pdf_url = ''
        
        if gcs_uri and gcs_uri.startswith('gs://'):
            try:
                from google.oauth2 import service_account
                import config
                
                credentials = None
                sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
                if sa_json:
                    try:
                        sa_info = json.loads(sa_json)
                        credentials = service_account.Credentials.from_service_account_info(sa_info)
                    except:
                        pass
                elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
                    credentials = service_account.Credentials.from_service_account_file(config.VERTEX_RUNNER_SA_PATH)
                
                storage_client = storage.Client(project=config.GOOGLE_CLOUD_PROJECT_ID, credentials=credentials)
                
                # Parse GCS URI
                gcs_parts = gcs_uri.replace('gs://', '').split('/', 1)
                bucket_name = gcs_parts[0]
                blob_name = gcs_parts[1] if len(gcs_parts) > 1 else ''
                
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                
                # Generate signed URL (valid for 7 days)
                pdf_url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.utcnow() + timedelta(days=7),
                    method="GET"
                )
                print(f"✅ PDF URL generated: {pdf_url[:80]}...")
            except Exception as url_err:
                print(f"⚠️ Could not generate PDF URL: {url_err}")
        
        # ========== STEP 4: SAVE TO BIGQUERY (Same as Gmail tab) ==========
        print("\n💾 STEP 4: Saving invoice to BigQuery...")
        invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
        
        try:
            bigquery_svc = BigQueryService()
            
            invoice_record = {
                'invoice_id': invoice_number if invoice_number != 'N/A' else invoice_id,
                'vendor_id': matched_vendor_id,
                'vendor_name': vendor_name,
                'client_id': validated_data.get('buyer', {}).get('name', 'Unknown'),
                'amount': float(total) if total else 0,
                'currency': currency,
                'invoice_date': invoice_date,
                'status': 'matched' if matched_vendor_id else 'unmatched',
                'gcs_uri': gcs_uri,
                'file_type': result.get('file_type', 'pdf'),
                'file_size': result.get('file_size', 0),
                'metadata': json.dumps({
                    'source': 'agent_upload',
                    'user_email': user_email,
                    'extraction_confidence': confidence,
                    'full_data': validated_data,
                    'vendor_match': {
                        'verdict': match_verdict,
                        'vendor_id': matched_vendor_id,
                        'netsuite_id': netsuite_id,
                        'confidence': match_confidence
                    }
                })
            }
            
            bigquery_svc.save_invoice(invoice_record)
            print(f"✅ Invoice saved to BigQuery: {invoice_record['invoice_id']}")
        except Exception as bq_err:
            print(f"⚠️ BigQuery save error (non-fatal): {bq_err}")
        
        # ========== BUILD RESPONSE (Matches Gmail tab output format) ==========
        print(f"\n{'='*60}")
        print("✅ INVOICE PROCESSING COMPLETE!")
        print(f"{'='*60}\n")
        
        response = {
            "success": True,
            "user_email": user_email,
            "invoice_id": invoice_number if invoice_number != 'N/A' else invoice_id,
            "source": "agent_upload",
            "extraction": {
                "vendor_name": vendor_name,
                "vendor_email": vendor_email,
                "vendor_address": vendor_address,
                "vendor_tax_id": vendor_tax_id,
                "vendor_country": vendor_country,
                "vendor_phone": vendor_phone,
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "currency": currency,
                "confidence": round(confidence),
                "line_items": line_items[:10]
            },
            "vendor_match": {
                "verdict": match_verdict,
                "matched": matched_vendor_id is not None,
                "vendor_id": matched_vendor_id,
                "vendor_name": matched_vendor_name,
                "netsuite_id": netsuite_id,
                "confidence": match_confidence,
                "reasoning": match_reasoning,
                "candidates": candidates[:5] if candidates else []
            },
            "pdf_url": pdf_url,
            "gcs_uri": gcs_uri,
            "next_steps": [],
            "proactive_message": ""
        }
        
        # Determine next steps based on match result (same logic as Gmail tab)
        if match_verdict == 'MATCH' and netsuite_id:
            response["next_steps"] = [
                {"action": "create_bill", "label": "Create Bill in NetSuite", "enabled": True},
                {"action": "view_vendor", "label": "View Vendor Profile", "enabled": True}
            ]
            response["proactive_message"] = f"Great news! I matched this invoice to '{matched_vendor_name}' who is already in NetSuite (ID: {netsuite_id}). Ready to create the bill?"
        elif match_verdict == 'MATCH' and matched_vendor_id:
            response["next_steps"] = [
                {"action": "sync_vendor", "label": "Sync Vendor to NetSuite First", "enabled": True},
                {"action": "create_bill", "label": "Create Bill", "enabled": False, "reason": "Sync vendor first"}
            ]
            response["proactive_message"] = f"I matched this to vendor '{matched_vendor_name}' in your database, but they're not in NetSuite yet. Want me to sync them first, then create the bill?"
        elif match_verdict == 'AMBIGUOUS':
            response["next_steps"] = [
                {"action": "select_vendor", "label": "Select Correct Vendor", "enabled": True},
                {"action": "create_vendor", "label": "Create New Vendor", "enabled": True}
            ]
            response["proactive_message"] = f"I found {len(candidates)} potential matches for '{vendor_name}'. Please select the correct vendor or create a new one."
        else:
            response["next_steps"] = [
                {"action": "create_vendor", "label": "Create New Vendor & Sync", "enabled": True}
            ]
            response["proactive_message"] = f"'{vendor_name}' is a new vendor. Would you like me to add them to your database and sync to NetSuite?"
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        import traceback
        print(f"❌ Error processing invoice: {e}")
        traceback.print_exc()
        return json.dumps({"error": str(e), "file_path": file_path})


@tool
def import_vendor_csv(user_email: str, file_path: str) -> str:
    """
    Import vendors from an uploaded CSV file using AI-powered column mapping.
    Analyzes the CSV structure, maps columns to schema, and imports to BigQuery.
    
    AUTOMATICALLY CALL THIS when user uploads a CSV file.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
        file_path: Path to the uploaded CSV file (e.g., "uploads/abc123_vendors.csv")
    
    Returns:
        Import results with count of new/updated vendors and HTML table preview
    """
    try:
        import sys
        sys.path.insert(0, '.')
        from services.vendor_csv_mapper import VendorCSVMapper
        
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        if not os.path.exists(file_path):
            return json.dumps({
                "error": f"File not found: {file_path}",
                "suggestion": "The file may have been moved or deleted."
            })
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            csv_content = f.read()
        
        mapper = VendorCSVMapper()
        
        print(f"📋 Analyzing CSV for {user_email}: {file_path}")
        mapping_result = mapper.analyze_csv_headers(csv_content, os.path.basename(file_path))
        
        if not mapping_result.get('success'):
            return json.dumps({
                "success": False,
                "error": mapping_result.get('error', 'Failed to analyze CSV'),
                "file_path": file_path
            })
        
        column_mapping = mapping_result.get('mapping', {})
        
        vendors = mapper.transform_csv_data(csv_content, column_mapping)
        
        new_count = 0
        updated_count = 0
        errors = []
        
        vendors_to_insert = []
        for vendor in vendors:
            try:
                if vendor.get('global_name'):
                    vendor['owner_email'] = user_email
                    
                    existing = bigquery_service.query(
                        "SELECT vendor_id FROM `invoicereader-477008.vendors_ai.global_vendors` WHERE owner_email = @user_email AND LOWER(global_name) = @name LIMIT 1",
                        {"name": vendor['global_name'].lower(), "user_email": user_email}
                    )
                    
                    if existing:
                        updated_count += 1
                    else:
                        import uuid
                        vendor['vendor_id'] = vendor.get('vendor_id') or f"V{uuid.uuid4().hex[:8].upper()}"
                        vendors_to_insert.append(vendor)
                        new_count += 1
            except Exception as e:
                errors.append(str(e))
        
        if vendors_to_insert:
            merge_result = bigquery_service.merge_vendors(vendors_to_insert, source_system="csv_upload")
            if merge_result.get('errors'):
                errors.extend(merge_result['errors'])
        
        html_table = '<table class="payouts-data-table"><thead><tr><th>Name</th><th>Email</th><th>Country</th><th>Status</th></tr></thead><tbody>'
        for v in vendors[:10]:
            name = v.get('global_name', 'N/A')
            email = v.get('emails', ['N/A'])[0] if v.get('emails') else 'N/A'
            country = v.get('countries', ['N/A'])[0] if v.get('countries') else 'N/A'
            status = '🆕 New' if not v.get('existing') else '✅ Updated'
            html_table += f'<tr><td>{name}</td><td>{email}</td><td>{country}</td><td>{status}</td></tr>'
        
        if len(vendors) > 10:
            html_table += f'<tr><td colspan="4" style="text-align:center;color:#6b7280;">... and {len(vendors) - 10} more vendors</td></tr>'
        html_table += '</tbody></table>'
        
        response = {
            "success": True,
            "user_email": user_email,
            "total_vendors": len(vendors),
            "new_vendors": new_count,
            "updated_vendors": updated_count,
            "errors": len(errors),
            "mapping_confidence": mapping_result.get('confidence', 0),
            "detected_language": column_mapping.get('detectedLanguage', 'Unknown'),
            "message": f"Analyzed CSV with {len(vendors)} vendors.\n✅ {new_count} new vendors imported.\n🔄 {updated_count} existing vendors found.",
            "html_table": html_table,
            "html_action": '<a href="#" class="chat-action-btn" onclick="window.PayoutsAgentWidget.sendMessage(\'Show me all vendors\'); return false;">📋 View All Vendors</a>'
        }
        
        if errors:
            response["message"] += f"\n⚠️ {len(errors)} errors occurred during import."
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e), "file_path": file_path})


@tool
def get_netsuite_statistics(user_email: str) -> str:
    """
    Get comprehensive statistics from NetSuite - LIVE data from NetSuite, not local database.
    Use this when user asks for "NetSuite stats", "stats from NetSuite", "what's in NetSuite", 
    "how many vendors in NetSuite", or anything about NetSuite-specific data.
    
    This queries NetSuite directly and provides stats on:
    - Total vendors in NetSuite
    - Vendors synced to local database  
    - Bills created in NetSuite
    - Spending by vendor
    - Recent activity
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
    
    Returns:
        Comprehensive NetSuite statistics with tables and charts
    """
    try:
        stats = {
            "netsuite_connected": False,
            "netsuite_vendors_count": 0,
            "local_synced_count": 0,
            "unsynced_count": 0,
            "vendors_with_bills": 0,
            "total_bills": 0,
            "total_spend": 0,
            "netsuite_vendors": [],
            "spending_by_vendor": []
        }
        
        # Check NetSuite connection
        try:
            connection = netsuite_service.test_connection()
            stats["netsuite_connected"] = connection.get("connected", False)
        except:
            stats["netsuite_connected"] = False
        
        if not stats["netsuite_connected"]:
            return json.dumps({
                "success": False,
                "error": "NetSuite is not connected. Please check your NetSuite credentials.",
                "html_table": '<div class="error-banner" style="background:#fef2f2; padding:16px; border-radius:8px; color:#dc2626;">⚠️ NetSuite connection failed. Check credentials.</div>'
            })
        
        # Get vendors directly from NetSuite
        try:
            netsuite_vendors = netsuite_service.search_vendors(limit=500)
            stats["netsuite_vendors_count"] = len(netsuite_vendors)
            stats["netsuite_vendors"] = netsuite_vendors[:20]  # First 20 for preview
        except Exception as e:
            print(f"Error fetching NetSuite vendors: {e}")
        
        # Get count of locally synced vendors (have NetSuite ID)
        try:
            synced_query = """
            SELECT COUNT(*) as synced_count
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE owner_email = @user_email AND netsuite_internal_id IS NOT NULL
            """
            synced_result = bigquery_service.query(synced_query, {"user_email": user_email})
            if synced_result:
                stats["local_synced_count"] = synced_result[0].get("synced_count", 0)
        except Exception as e:
            print(f"Error getting synced count: {e}")
        
        # Get unsynced vendors count (local vendors without NetSuite ID)
        try:
            unsynced_query = """
            SELECT COUNT(*) as unsynced_count
            FROM `invoicereader-477008.vendors_ai.global_vendors`
            WHERE owner_email = @user_email AND netsuite_internal_id IS NULL
            """
            unsynced_result = bigquery_service.query(unsynced_query, {"user_email": user_email})
            if unsynced_result:
                stats["unsynced_count"] = unsynced_result[0].get("unsynced_count", 0)
        except Exception as e:
            print(f"Error getting unsynced count: {e}")
        
        # Get bills/invoices with NetSuite status
        try:
            bills_query = """
            SELECT 
                COUNT(*) as total_bills,
                COUNTIF(netsuite_bill_id IS NOT NULL) as in_netsuite,
                SUM(amount) as total_spend
            FROM `invoicereader-477008.vendors_ai.invoices`
            WHERE owner_email = @user_email OR owner_email IS NULL
            """
            bills_result = bigquery_service.query(bills_query, {"user_email": user_email})
            if bills_result:
                stats["total_bills"] = bills_result[0].get("total_bills", 0)
                stats["vendors_with_bills"] = bills_result[0].get("in_netsuite", 0)
                stats["total_spend"] = float(bills_result[0].get("total_spend") or 0)
        except Exception as e:
            print(f"Error getting bills stats: {e}")
        
        # Build HTML response
        html = f'''
<div class="netsuite-stats-dashboard">
    <div style="margin-bottom: 16px; font-size: 18px; font-weight: bold;">📊 NetSuite Statistics (Live Data)</div>
    
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 16px; border-radius: 12px; color: white; text-align: center;">
            <div style="font-size: 28px; font-weight: bold;">{stats["netsuite_vendors_count"]}</div>
            <div style="font-size: 12px; opacity: 0.9;">Vendors in NetSuite</div>
        </div>
        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 16px; border-radius: 12px; color: white; text-align: center;">
            <div style="font-size: 28px; font-weight: bold;">{stats["local_synced_count"]}</div>
            <div style="font-size: 12px; opacity: 0.9;">Synced Locally</div>
        </div>
        <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 16px; border-radius: 12px; color: white; text-align: center;">
            <div style="font-size: 28px; font-weight: bold;">{stats["unsynced_count"]}</div>
            <div style="font-size: 12px; opacity: 0.9;">Not in NetSuite</div>
        </div>
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px;">
        <div style="background: #f0fdf4; padding: 16px; border-radius: 8px; border-left: 4px solid #10b981;">
            <div style="font-size: 24px; font-weight: bold; color: #059669;">{stats["total_bills"]}</div>
            <div style="color: #666;">Total Invoices</div>
        </div>
        <div style="background: #eff6ff; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6;">
            <div style="font-size: 24px; font-weight: bold; color: #2563eb;">${stats["total_spend"]:,.2f}</div>
            <div style="color: #666;">Total Spend</div>
        </div>
    </div>
'''
        
        # Add vendor preview table
        if stats["netsuite_vendors"]:
            html += '''<div style="margin-top: 16px;"><div style="font-weight: bold; margin-bottom: 8px;">📋 NetSuite Vendors (First 20)</div>
<table class="payouts-data-table" style="width:100%;border-collapse:collapse;font-size:13px;">
<thead><tr style="background:#f3f4f6;"><th style="padding:8px;text-align:left;">Vendor Name</th><th style="padding:8px;text-align:left;">NetSuite ID</th><th style="padding:8px;text-align:left;">Email</th></tr></thead><tbody>'''
            
            for v in stats["netsuite_vendors"][:20]:
                name = v.get('companyname') or v.get('companyName') or v.get('entityid') or v.get('entityId') or 'N/A'
                ns_id = v.get('id') or v.get('internalId', 'N/A')
                email = v.get('email', 'N/A')
                html += f'<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb;">{name}</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;">{ns_id}</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;">{email}</td></tr>'
            
            if stats["netsuite_vendors_count"] > 20:
                html += f'<tr><td colspan="3" style="padding:8px;text-align:center;color:#6b7280;">... and {stats["netsuite_vendors_count"] - 20} more vendors in NetSuite</td></tr>'
            
            html += '</tbody></table></div>'
        
        html += '</div>'
        
        return json.dumps({
            "success": True,
            "stats": stats,
            "message": f"NetSuite has {stats['netsuite_vendors_count']} vendors. {stats['local_synced_count']} are synced locally.",
            "html_table": html
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def pull_netsuite_vendors(user_email: str) -> str:
    """
    Pull and sync all vendors from NetSuite to the local database.
    Fetches vendor records from NetSuite API and updates BigQuery.
    
    Args:
        user_email: The logged-in user's email for multi-tenant tracking
    
    Returns:
        Sync results with count of vendors and HTML table preview
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        print(f"🔄 Pulling vendors from NetSuite for {user_email}...")
        
        vendors = netsuite_service.search_vendors(limit=500)
        
        if not vendors:
            return json.dumps({
                "success": True,
                "message": "No vendors found in NetSuite.",
                "total_vendors": 0
            })
        
        synced_count = 0
        new_count = 0
        updated_count = 0
        
        vendors_to_insert = []
        for vendor in vendors:
            try:
                netsuite_id = vendor.get('id') or vendor.get('internalId')
                company_name = vendor.get('companyname') or vendor.get('companyName') or vendor.get('entityid') or vendor.get('entityId') or 'Unknown'
                email = vendor.get('email', '')
                
                existing = bigquery_service.query(
                    "SELECT vendor_id FROM `invoicereader-477008.vendors_ai.global_vendors` WHERE owner_email = @user_email AND netsuite_internal_id = @netsuite_id LIMIT 1",
                    {"netsuite_id": str(netsuite_id), "user_email": user_email}
                )
                
                if existing:
                    updated_count += 1
                else:
                    import uuid
                    new_vendor = {
                        'vendor_id': f"V{uuid.uuid4().hex[:8].upper()}",
                        'global_name': company_name,
                        'netsuite_internal_id': str(netsuite_id),
                        'emails': [email] if email else [],
                        'domains': [],
                        'countries': [],
                        'source_system': 'netsuite',
                        'owner_email': user_email
                    }
                    vendors_to_insert.append(new_vendor)
                    new_count += 1
                
                synced_count += 1
                
            except Exception as e:
                print(f"Error syncing vendor: {e}")
        
        if vendors_to_insert:
            bigquery_service.merge_vendors(vendors_to_insert, source_system="netsuite")
        
        html_table = '<table class="payouts-data-table"><thead><tr><th>Name</th><th>NetSuite ID</th><th>Email</th><th>Status</th></tr></thead><tbody>'
        for v in vendors[:10]:
            name = v.get('companyname') or v.get('companyName') or v.get('entityid') or v.get('entityId') or 'N/A'
            ns_id = v.get('id') or v.get('internalId', 'N/A')
            email = v.get('email', 'N/A')
            html_table += f'<tr><td>{name}</td><td>{ns_id}</td><td>{email}</td><td>✅ Synced</td></tr>'
        
        if len(vendors) > 10:
            html_table += f'<tr><td colspan="4" style="text-align:center;color:#6b7280;">... and {len(vendors) - 10} more vendors</td></tr>'
        html_table += '</tbody></table>'
        
        response = {
            "success": True,
            "user_email": user_email,
            "total_vendors": len(vendors),
            "new_vendors": new_count,
            "updated_vendors": updated_count,
            "message": f"Successfully synced {synced_count} vendors from NetSuite.\n🆕 {new_count} new vendors added.\n🔄 {updated_count} existing vendors updated.",
            "html_table": html_table,
            "html_action": '<a href="#" class="chat-action-btn" onclick="window.PayoutsAgentWidget.sendMessage(\'Show me all vendors\'); return false;">📋 View All Vendors</a>'
        }
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def show_vendors_table(user_email: str, limit: int = 20, filter_type: str = "all") -> str:
    """
    Show vendors in a rich HTML table format.
    Use this when user asks to "show vendors", "list vendors", or "see all vendors".
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        limit: Maximum number of vendors to show (default 20)
        filter_type: Filter by "all", "synced" (in NetSuite), or "unsynced"
    
    Returns:
        HTML table with vendor data
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        where_clause = "WHERE owner_email = @user_email"
        if filter_type == "synced":
            where_clause += " AND netsuite_internal_id IS NOT NULL AND LENGTH(TRIM(netsuite_internal_id)) > 0"
        elif filter_type == "unsynced":
            where_clause += " AND (netsuite_internal_id IS NULL OR LENGTH(TRIM(COALESCE(netsuite_internal_id, ''))) = 0)"
        
        query = f"""
        SELECT 
            vendor_id, global_name, netsuite_internal_id, emails, 
            custom_attributes, countries, source_system, created_at
        FROM `invoicereader-477008.vendors_ai.global_vendors`
        {where_clause}
        ORDER BY created_at DESC
        LIMIT {limit}
        """
        
        vendors = bigquery_service.query(query, {"user_email": user_email})
        
        if not vendors:
            return json.dumps({
                "success": True,
                "message": "No vendors found matching your criteria.",
                "html_table": "<p>No vendors in database.</p>"
            })
        
        html_table = '<table class="payouts-data-table"><thead><tr><th>Name</th><th>Tax ID</th><th>NetSuite Status</th><th>Country</th></tr></thead><tbody>'
        
        for v in vendors:
            name = v.get('global_name', 'N/A')
            custom_attrs = v.get('custom_attributes') or {}
            tax_id = custom_attrs.get('tax_id', '-') if isinstance(custom_attrs, dict) else '-'
            ns_id = v.get('netsuite_internal_id')
            ns_status = f'✅ Synced (ID: {ns_id})' if ns_id else '⚠️ Not Synced'
            countries = v.get('countries', [])
            country = countries[0] if countries else '-'
            
            html_table += f'<tr><td><strong>{name}</strong></td><td>{tax_id}</td><td>{ns_status}</td><td>{country}</td></tr>'
        
        html_table += '</tbody></table>'
        
        total_query = f"SELECT COUNT(*) as count FROM `invoicereader-477008.vendors_ai.global_vendors` {where_clause}"
        total_result = bigquery_service.query(total_query, {"user_email": user_email})
        total_count = total_result[0]['count'] if total_result else len(vendors)
        
        synced_query = "SELECT COUNT(*) as count FROM `invoicereader-477008.vendors_ai.global_vendors` WHERE owner_email = @user_email AND netsuite_internal_id IS NOT NULL"
        synced_result = bigquery_service.query(synced_query, {"user_email": user_email})
        synced_count = synced_result[0]['count'] if synced_result else 0
        
        response = {
            "success": True,
            "user_email": user_email,
            "total_vendors": total_count,
            "synced_vendors": synced_count,
            "showing": len(vendors),
            "message": f"Showing {len(vendors)} of {total_count} vendors. {synced_count} synced to NetSuite.",
            "html_table": html_table
        }
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def show_unsynced_vendors(user_email: str, limit: int = 50) -> str:
    """
    Show vendors NOT in NetSuite - dedicated tool for unsynced vendor queries.
    Use this when user asks "show unsynced vendors", "vendors not in NetSuite", "local only vendors".
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        limit: Maximum number of vendors to show (default 50)
    
    Returns:
        HTML table with unsynced vendors
    """
    return show_vendors_table.invoke({"user_email": user_email, "limit": limit, "filter_type": "unsynced"})


@tool
def show_invoices_table(user_email: str, limit: int = 20, vendor_name: str = None) -> str:
    """
    Show invoices in a rich HTML table format with action buttons.
    Use this when user asks to "show invoices", "my invoices", or "recent invoices".
    
    Args:
        user_email: The logged-in user's email for multi-tenant filtering
        limit: Maximum number of invoices to show (default 20)
        vendor_name: Optional filter by vendor name
    
    Returns:
        HTML table with invoice data and action buttons
    """
    try:
        if not user_email:
            return json.dumps({"error": "user_email is required for multi-tenant access"})
        
        where_clause = "WHERE owner_email = @user_email"
        params = {"user_email": user_email}
        
        if vendor_name:
            where_clause += " AND LOWER(vendor_name) LIKE @vendor_pattern"
            params["vendor_pattern"] = f"%{vendor_name.lower()}%"
        
        query = f"""
        SELECT 
            invoice_id, vendor_name, amount, currency, 
            invoice_date, status, gcs_uri, created_at, netsuite_bill_id
        FROM `invoicereader-477008.vendors_ai.invoices`
        {where_clause}
        ORDER BY invoice_date DESC
        LIMIT {limit}
        """
        
        invoices = bigquery_service.query(query, params)
        
        if not invoices:
            filter_msg = f" from {vendor_name}" if vendor_name else ""
            return json.dumps({
                "success": True,
                "message": f"No invoices found{filter_msg}.",
                "html_table": f"<p>No invoices in database{filter_msg}. Upload PDFs or scan Gmail to add invoices.</p>",
                "html_action": '<a href="#" class="chat-action-btn" onclick="window.PayoutsAgentWidget.sendMessage(\'Scan Gmail for invoices\'); return false;">📧 Scan Gmail</a>'
            })
        
        html_table = '<table class="payouts-data-table"><thead><tr><th>Invoice ID</th><th>Vendor</th><th>Amount</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead><tbody>'
        
        total_amount = 0
        for inv in invoices:
            inv_id = inv.get('invoice_id', 'N/A')
            short_id = inv_id[:8] + '...' if len(inv_id) > 12 else inv_id
            vendor = inv.get('vendor_name', 'Unknown')
            amount = float(inv.get('amount', 0)) if inv.get('amount') else 0
            currency = inv.get('currency', 'USD')
            inv_date = str(inv.get('invoice_date', ''))[:10]
            status = inv.get('status', 'pending')
            gcs_uri = inv.get('gcs_uri', '')
            ns_bill_id = inv.get('netsuite_bill_id', '')
            
            total_amount += amount
            
            if ns_bill_id:
                status_badge = '🔗 In NetSuite'
            elif status == 'processed':
                status_badge = '✅ Processed'
            else:
                status_badge = '⏳ Pending'
            
            pdf_btn = ''
            if gcs_uri:
                pdf_btn = f'<a href="#" onclick="window.PayoutsAgentWidget.sendMessage(\'Get PDF for invoice {inv_id}\'); return false;" style="color:#667eea;">📄</a>'
            
            html_table += f'<tr><td><strong>{short_id}</strong></td><td>{vendor}</td><td>{currency} {amount:,.2f}</td><td>{inv_date}</td><td>{status_badge}</td><td>{pdf_btn}</td></tr>'
        
        html_table += '</tbody></table>'
        
        total_query = f"SELECT COUNT(*) as count, SUM(amount) as total FROM `invoicereader-477008.vendors_ai.invoices` {where_clause}"
        total_result = bigquery_service.query(total_query, params)
        total_count = total_result[0]['count'] if total_result else len(invoices)
        grand_total = float(total_result[0]['total'] or 0) if total_result else total_amount
        
        response = {
            "success": True,
            "user_email": user_email,
            "total_invoices": total_count,
            "showing": len(invoices),
            "total_amount": grand_total,
            "message": f"Showing {len(invoices)} of {total_count} invoices. Total spend: ${grand_total:,.2f}",
            "html_table": html_table,
            "html_action": '<a href="#" class="chat-action-btn" onclick="window.PayoutsAgentWidget.sendMessage(\'Scan Gmail for new invoices\'); return false;">📧 Scan Gmail</a>'
        }
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_all_tools():
    """
    Return list of all available tools for the agent - OMNISCIENT SEMANTIC AI FIRST ORDER
    Note: Use get_tools_for_user(user_email) for multi-tenant data isolation
    """
    return [
        # Startup & Dashboard (call on chat open)
        get_dashboard_status,
        # Omniscient Tools (use these first for comprehensive answers)
        get_vendor_full_profile,
        deep_search,
        get_invoice_pdf_link,
        check_netsuite_health,
        # Display Tools (for rich HTML tables and cards)
        show_vendors_table,
        show_unsynced_vendors,
        show_invoices_table,
        # Ingestion Tools (for file uploads)
        process_uploaded_invoice,
        import_vendor_csv,
        pull_netsuite_vendors,
        get_netsuite_statistics,
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


def get_tools_for_user(user_email: str):
    """
    Return list of tools with user_email pre-bound for multi-tenant data isolation.
    Each tool will automatically filter data by the user's email.
    
    Args:
        user_email: The logged-in user's email address
        
    Returns:
        List of tools with user_email bound as the first parameter
    """
    from langchain_core.tools import StructuredTool
    import inspect
    
    all_tools = get_all_tools()
    bound_tools = []
    
    for tool_func in all_tools:
        original_func = tool_func.func
        tool_name = tool_func.name
        tool_description = tool_func.description
        
        sig = inspect.signature(original_func)
        params = list(sig.parameters.keys())
        
        if 'user_email' in params:
            def make_wrapper(orig_fn, email):
                def wrapper(**kwargs):
                    return orig_fn(user_email=email, **kwargs)
                return wrapper
            
            wrapped_func = make_wrapper(original_func, user_email)
            
            new_schema = _remove_user_email_from_schema(tool_func.args_schema) if hasattr(tool_func, 'args_schema') else None
            
            new_tool = StructuredTool.from_function(
                func=wrapped_func,
                name=tool_name,
                description=tool_description,
                args_schema=new_schema,
                return_direct=getattr(tool_func, 'return_direct', False),
            )
            bound_tools.append(new_tool)
        else:
            bound_tools.append(tool_func)
    
    return bound_tools


def _remove_user_email_from_schema(schema_class):
    """
    Create a modified schema class that excludes user_email field.
    This hides the user_email parameter from the LLM since it's injected by the system.
    Supports both Pydantic v1 and v2.
    """
    if schema_class is None:
        return None
    
    from pydantic import create_model, Field
    from typing import get_type_hints, Optional
    
    try:
        original_fields = {}
        
        if hasattr(schema_class, 'model_fields'):
            from pydantic.fields import PydanticUndefined
            for name, field in schema_class.model_fields.items():
                if name != 'user_email':
                    if field.default is not PydanticUndefined:
                        original_fields[name] = (field.annotation, field.default)
                    elif field.default_factory is not None:
                        original_fields[name] = (field.annotation, Field(default_factory=field.default_factory))
                    else:
                        original_fields[name] = (field.annotation, ...)
        else:
            for name, field in schema_class.__fields__.items():
                if name != 'user_email':
                    if field.default is not None:
                        original_fields[name] = (field.outer_type_, field.default)
                    elif field.default_factory is not None:
                        original_fields[name] = (field.outer_type_, Field(default_factory=field.default_factory))
                    elif not field.required:
                        original_fields[name] = (field.outer_type_, None)
                    else:
                        original_fields[name] = (field.outer_type_, ...)
        
        if not original_fields:
            return None
            
        new_schema = create_model(
            f"{schema_class.__name__}NoUserEmail",
            **original_fields
        )
        return new_schema
    except Exception as e:
        print(f"Warning: Could not modify schema: {e}")
        return schema_class
