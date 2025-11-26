"""
LangGraph Tools - Wraps existing services for LLM control
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


@tool
def search_gmail_invoices(days: int = 30, max_results: int = 20, access_token: Optional[str] = None) -> str:
    """
    Search Gmail for invoice and receipt emails.
    
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
            return json.dumps({"error": "Gmail not connected. Please connect Gmail first via the web interface."})
        
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


def get_all_tools():
    """Return list of all available tools for the agent"""
    return [
        search_gmail_invoices,
        create_netsuite_bill,
        search_netsuite_vendor,
        get_bill_status,
        match_vendor_to_database,
        run_bigquery,
        get_subscription_summary,
        create_netsuite_vendor
    ]
