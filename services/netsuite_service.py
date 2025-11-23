"""
NetSuite REST API Service with OAuth 1.0a Authentication
Handles vendor and invoice synchronization with NetSuite
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from requests_oauthlib import OAuth1
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NetSuiteService:
    """
    NetSuite REST API service with OAuth 1.0a authentication
    Handles vendor and vendor bill operations with retry logic
    """
    
    # Currency code to NetSuite ID mapping
    CURRENCY_MAP = {
        'USD': '1',
        'EUR': '2',
        'GBP': '3',
        'CAD': '4',
        'ILS': '5',
        'AUD': '6',
        'CHF': '7',
        'JPY': '8',
        'INR': '9',
        'SGD': '10'
    }
    
    # Default subsidiary ID (configurable via environment)
    DEFAULT_SUBSIDIARY_ID = '2'
    
    # Default tax code ID (configurable via environment)
    DEFAULT_TAX_CODE_ID = '18'
    
    # Default expense account ID (configurable via environment)
    DEFAULT_EXPENSE_ACCOUNT_ID = '351'
    
    def __init__(self):
        """Initialize NetSuite service with OAuth 1.0a credentials from environment"""
        
        # Load credentials from environment
        self.account_id = os.getenv('NETSUITE_ACCOUNT_ID')
        self.consumer_key = os.getenv('NETSUITE_CONSUMER_KEY')
        self.consumer_secret = os.getenv('NETSUITE_CONSUMER_SECRET')
        self.token_id = os.getenv('NETSUITE_TOKEN_ID')
        self.token_secret = os.getenv('NETSUITE_TOKEN_SECRET')
        
        # Validate credentials
        if not all([self.account_id, self.consumer_key, self.consumer_secret, 
                   self.token_id, self.token_secret]):
            logger.warning("NetSuite credentials not fully configured. Service will be disabled.")
            self.enabled = False
            return
        
        self.enabled = True
        
        # Replace underscores with hyphens and convert to lowercase for URL
        self.account_id_url = self.account_id.replace('_', '-').lower()
        
        # Build base URL
        self.base_url = f"https://{self.account_id_url}.suitetalk.api.netsuite.com/services/rest"
        
        # Store default headers for requests
        self.default_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'prefer': 'transient'  # Don't persist failed requests
        }
        
        logger.info(f"NetSuite service initialized for account: {self.account_id}")
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None, 
                     params: Dict = None, retries: int = 3) -> Optional[Dict]:
        """
        Make an authenticated request to NetSuite API with retry logic
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /record/v1/vendor)
            data: Request body data
            params: Query parameters
            retries: Number of retries for failed requests
            
        Returns:
            Response data or None if failed
        """
        if not self.enabled:
            logger.warning("NetSuite service is not enabled. Skipping request.")
            return None
        
        url = f"{self.base_url}{endpoint}"
        
        # Create OAuth1 authentication for each request
        oauth = OAuth1(
            client_key=self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=self.token_id,
            resource_owner_secret=self.token_secret,
            realm=self.account_id,  # Use account ID as realm
            signature_method='HMAC-SHA256'
        )
        
        # Merge default headers with any custom headers
        headers = self.default_headers.copy()
        
        for attempt in range(retries):
            try:
                logger.debug(f"NetSuite {method} request to {endpoint} (attempt {attempt + 1}/{retries})")
                
                # Make the request with OAuth1 authentication
                response = requests.request(
                    method=method,
                    url=url,
                    auth=oauth,
                    json=data,
                    params=params,
                    headers=headers,
                    timeout=30
                )
                
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                # Check for success
                if response.status_code in [200, 201, 204]:
                    if response.status_code == 204:
                        return {'success': True}
                    return response.json() if response.text else {'success': True}
                
                # Log error details with headers for debugging
                error_msg = f"NetSuite API error: {response.status_code}"
                error_msg += f"\nRequest URL: {url}"
                error_msg += f"\nRequest Method: {method}"
                
                # Log important response headers for debugging
                if response.headers:
                    important_headers = ['WWW-Authenticate', 'X-N-OperationId', 'NS_RTIMER_COMPOSITE']
                    for header in important_headers:
                        if header in response.headers:
                            error_msg += f"\n{header}: {response.headers[header]}"
                
                if response.text:
                    try:
                        error_data = response.json()
                        error_msg += f"\nResponse Body: {error_data}"
                    except:
                        error_msg += f"\nResponse Text: {response.text[:500]}"  # Limit text length
                
                logger.error(error_msg)
                
                # Don't retry client errors (400-499) except 429
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    return None
                
            except requests.exceptions.Timeout:
                logger.error(f"Request timeout on attempt {attempt + 1}/{retries}")
                if attempt == retries - 1:
                    return None
                time.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"NetSuite request error: {str(e)}")
                logger.error(f"Error type: {type(e).__name__}")
                if attempt == retries - 1:
                    return None
                time.sleep(2 ** attempt)
        
        return None
    
    def test_connection(self) -> Dict:
        """
        Test NetSuite connection and authentication
        
        Returns:
            Connection status and metadata
        """
        if not self.enabled:
            return {
                'connected': False,
                'error': 'NetSuite credentials not configured'
            }
        
        try:
            # Try to fetch metadata catalog (lightweight endpoint)
            result = self._make_request('GET', '/record/v1/metadata-catalog/')
            
            if result:
                return {
                    'connected': True,
                    'account_id': self.account_id,
                    'base_url': self.base_url,
                    'metadata': result.get('items', [])[:5]  # Return first 5 record types
                }
            else:
                return {
                    'connected': False,
                    'error': 'Failed to authenticate with NetSuite'
                }
                
        except Exception as e:
            return {
                'connected': False,
                'error': str(e)
            }
    
    def search_vendors(self, name: str = None, tax_id: str = None, 
                      email: str = None, limit: int = 10) -> List[Dict]:
        """
        Search for vendors in NetSuite by various criteria
        
        Args:
            name: Vendor company name
            tax_id: VAT/Tax registration number
            email: Vendor email address
            limit: Maximum results to return
            
        Returns:
            List of matching vendors
        """
        if not self.enabled:
            return []
        
        # Build search query
        query_parts = []
        if name:
            query_parts.append(f"companyName CONTAIN '{name}'")
        if tax_id:
            query_parts.append(f"vatRegNumber IS '{tax_id}'")
        if email:
            query_parts.append(f"email CONTAIN '{email}'")
        
        if not query_parts:
            logger.warning("No search criteria provided")
            return []
        
        query = " OR ".join(query_parts)
        
        params = {
            'q': query,
            'limit': limit
        }
        
        result = self._make_request('GET', '/record/v1/vendor', params=params)
        
        if result and 'items' in result:
            return result['items']
        
        return []
    
    def get_vendor(self, vendor_id: str) -> Optional[Dict]:
        """
        Get vendor details by NetSuite internal ID
        
        Args:
            vendor_id: NetSuite vendor internal ID
            
        Returns:
            Vendor details or None
        """
        if not self.enabled:
            return None
        
        result = self._make_request('GET', f'/record/v1/vendor/{vendor_id}')
        return result
    
    def create_vendor(self, vendor_data: Dict) -> Optional[Dict]:
        """
        Create a new vendor in NetSuite
        
        Args:
            vendor_data: Vendor data from our system with fields:
                - name: Company name
                - tax_id: VAT/Tax registration number
                - email: Email address
                - phone: Phone number
                - address: Address dictionary
                - external_id: Our vendor_id for reference
                
        Returns:
            Created vendor data with NetSuite internal ID
        """
        if not self.enabled:
            return None
        
        # Map our data to NetSuite format
        netsuite_vendor = {
            'companyName': vendor_data.get('name', ''),
            'isPerson': False,
            'subsidiary': {
                'id': os.getenv('NETSUITE_SUBSIDIARY_ID', self.DEFAULT_SUBSIDIARY_ID)
            }
        }
        
        # Add optional fields if present
        if vendor_data.get('tax_id'):
            netsuite_vendor['vatRegNumber'] = vendor_data['tax_id']
        
        if vendor_data.get('email'):
            netsuite_vendor['email'] = vendor_data['email']
        
        if vendor_data.get('phone'):
            netsuite_vendor['phone'] = vendor_data['phone']
        
        if vendor_data.get('external_id'):
            netsuite_vendor['externalId'] = f"VENDOR_{vendor_data['external_id']}"
        
        # Add address if provided
        if vendor_data.get('address'):
            addr = vendor_data['address']
            netsuite_vendor['addressbook'] = {
                'items': [{
                    'addressbookAddress': {
                        'addr1': addr.get('line1', ''),
                        'city': addr.get('city', ''),
                        'state': addr.get('state', ''),
                        'zip': addr.get('postal_code', ''),
                        'country': addr.get('country', 'US')
                    },
                    'defaultBilling': True,
                    'defaultShipping': True
                }]
            }
        
        logger.info(f"Creating vendor in NetSuite: {vendor_data.get('name')}")
        result = self._make_request('POST', '/record/v1/vendor', data=netsuite_vendor)
        
        if result:
            logger.info(f"Successfully created vendor with ID: {result.get('id')}")
            return result
        
        logger.error(f"Failed to create vendor: {vendor_data.get('name')}")
        return None
    
    def update_vendor(self, vendor_id: str, updates: Dict) -> Optional[Dict]:
        """
        Update vendor information in NetSuite
        
        Args:
            vendor_id: NetSuite vendor internal ID
            updates: Fields to update
            
        Returns:
            Updated vendor data or None
        """
        if not self.enabled:
            return None
        
        # Map update fields to NetSuite format
        netsuite_updates = {}
        
        if 'name' in updates:
            netsuite_updates['companyName'] = updates['name']
        
        if 'tax_id' in updates:
            netsuite_updates['vatRegNumber'] = updates['tax_id']
        
        if 'email' in updates:
            netsuite_updates['email'] = updates['email']
        
        if 'phone' in updates:
            netsuite_updates['phone'] = updates['phone']
        
        if not netsuite_updates:
            logger.warning("No valid updates provided")
            return None
        
        logger.info(f"Updating vendor {vendor_id} in NetSuite")
        result = self._make_request('PATCH', f'/record/v1/vendor/{vendor_id}', 
                                   data=netsuite_updates)
        
        if result:
            logger.info(f"Successfully updated vendor {vendor_id}")
            return result
        
        logger.error(f"Failed to update vendor {vendor_id}")
        return None
    
    def create_vendor_bill(self, bill_data: Dict) -> Optional[Dict]:
        """
        Create a vendor bill (invoice) in NetSuite
        
        Args:
            bill_data: Bill data with fields:
                - invoice_id: Our invoice ID (used as external ID)
                - vendor_netsuite_id: NetSuite vendor internal ID
                - invoice_number: Invoice number
                - invoice_date: Invoice date (ISO format)
                - due_date: Due date (ISO format)
                - currency: Currency code (USD, EUR, etc.)
                - line_items: List of line items with amount, description, account
                - total_amount: Total invoice amount
                - memo: Optional memo/notes
                
        Returns:
            Created vendor bill data with NetSuite internal ID
        """
        if not self.enabled:
            return None
        
        # Map currency code to NetSuite ID
        currency_id = self.CURRENCY_MAP.get(
            bill_data.get('currency', 'USD').upper(), 
            '1'  # Default to USD
        )
        
        # Build vendor bill object
        netsuite_bill = {
            'externalId': f"INV_{bill_data['invoice_id']}",
            'entity': {
                'id': bill_data['vendor_netsuite_id']
            },
            'subsidiary': {
                'id': os.getenv('NETSUITE_SUBSIDIARY_ID', self.DEFAULT_SUBSIDIARY_ID)
            },
            'currency': {
                'id': currency_id
            },
            'tranId': bill_data.get('invoice_number', bill_data['invoice_id']),
            'trandate': bill_data.get('invoice_date', datetime.now().strftime('%Y-%m-%d')),
            'memo': bill_data.get('memo', f"Invoice from AI extraction system - {bill_data['invoice_id']}")
        }
        
        # Add due date if provided
        if bill_data.get('due_date'):
            netsuite_bill['duedate'] = bill_data['due_date']
        
        # Build expense lines
        expense_items = []
        line_items = bill_data.get('line_items', [])
        
        if line_items:
            # Use provided line items
            for item in line_items:
                expense_item = {
                    'account': {
                        'id': item.get('account_id', 
                                     os.getenv('NETSUITE_EXPENSE_ACCOUNT_ID', 
                                             self.DEFAULT_EXPENSE_ACCOUNT_ID))
                    },
                    'amount': item.get('amount', 0),
                    'memo': item.get('description', '')
                }
                
                # Add tax code if provided
                if item.get('tax_code_id'):
                    expense_item['taxCode'] = {'id': item['tax_code_id']}
                else:
                    expense_item['taxCode'] = {
                        'id': os.getenv('NETSUITE_TAX_CODE_ID', self.DEFAULT_TAX_CODE_ID)
                    }
                
                expense_items.append(expense_item)
        else:
            # Create single line item with total amount
            expense_items.append({
                'account': {
                    'id': os.getenv('NETSUITE_EXPENSE_ACCOUNT_ID', 
                                  self.DEFAULT_EXPENSE_ACCOUNT_ID)
                },
                'amount': bill_data.get('total_amount', 0),
                'memo': bill_data.get('memo', 'Invoice total'),
                'taxCode': {
                    'id': os.getenv('NETSUITE_TAX_CODE_ID', self.DEFAULT_TAX_CODE_ID)
                }
            })
        
        netsuite_bill['expense'] = {'items': expense_items}
        
        logger.info(f"Creating vendor bill in NetSuite for invoice: {bill_data['invoice_id']}")
        result = self._make_request('POST', '/record/v1/vendorbill', data=netsuite_bill)
        
        if result:
            logger.info(f"Successfully created vendor bill with ID: {result.get('id')}")
            return result
        
        logger.error(f"Failed to create vendor bill for invoice: {bill_data['invoice_id']}")
        return None
    
    def get_vendor_bill(self, bill_id: str) -> Optional[Dict]:
        """
        Get vendor bill details by NetSuite internal ID
        
        Args:
            bill_id: NetSuite vendor bill internal ID
            
        Returns:
            Vendor bill details or None
        """
        if not self.enabled:
            return None
        
        result = self._make_request('GET', f'/record/v1/vendorbill/{bill_id}')
        return result
    
    def sync_vendor_to_netsuite(self, vendor_data: Dict) -> Dict:
        """
        Sync a vendor from our system to NetSuite
        Checks if vendor exists, creates if not, updates if needed
        
        Args:
            vendor_data: Vendor data from our system
            
        Returns:
            Sync result with status and NetSuite ID
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'NetSuite service not enabled',
                'netsuite_id': None
            }
        
        try:
            # Check if vendor exists by tax ID first (most unique)
            existing_vendors = []
            if vendor_data.get('tax_id'):
                existing_vendors = self.search_vendors(tax_id=vendor_data['tax_id'])
            
            # If no tax ID match, try by name
            if not existing_vendors and vendor_data.get('name'):
                existing_vendors = self.search_vendors(name=vendor_data['name'])
            
            if existing_vendors:
                # Vendor exists, return the first match
                vendor = existing_vendors[0]
                logger.info(f"Vendor already exists in NetSuite: {vendor.get('id')}")
                return {
                    'success': True,
                    'action': 'found_existing',
                    'netsuite_id': vendor.get('id'),
                    'vendor_data': vendor
                }
            else:
                # Create new vendor
                result = self.create_vendor(vendor_data)
                if result:
                    return {
                        'success': True,
                        'action': 'created',
                        'netsuite_id': result.get('id'),
                        'vendor_data': result
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to create vendor in NetSuite',
                        'netsuite_id': None
                    }
                    
        except Exception as e:
            logger.error(f"Error syncing vendor to NetSuite: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'netsuite_id': None
            }
    
    def sync_invoice_to_netsuite(self, invoice_data: Dict, vendor_netsuite_id: str) -> Dict:
        """
        Sync an invoice from our system to NetSuite as a vendor bill
        
        Args:
            invoice_data: Invoice data from our system
            vendor_netsuite_id: NetSuite vendor internal ID
            
        Returns:
            Sync result with status and NetSuite bill ID
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'NetSuite service not enabled',
                'netsuite_bill_id': None
            }
        
        try:
            # Prepare bill data
            bill_data = {
                'invoice_id': invoice_data.get('invoice_id'),
                'vendor_netsuite_id': vendor_netsuite_id,
                'invoice_number': invoice_data.get('invoiceNumber'),
                'invoice_date': invoice_data.get('invoiceDate'),
                'due_date': invoice_data.get('dueDate'),
                'currency': invoice_data.get('currency', 'USD'),
                'total_amount': invoice_data.get('totals', {}).get('total', 0),
                'memo': f"AI extracted invoice - {invoice_data.get('invoiceNumber', 'Unknown')}"
            }
            
            # Add line items if available
            if invoice_data.get('lineItems'):
                bill_data['line_items'] = []
                for item in invoice_data['lineItems']:
                    bill_data['line_items'].append({
                        'description': item.get('description', ''),
                        'amount': item.get('totalPrice', item.get('unitPrice', 0))
                    })
            
            # Create vendor bill
            result = self.create_vendor_bill(bill_data)
            
            if result:
                return {
                    'success': True,
                    'action': 'created',
                    'netsuite_bill_id': result.get('id'),
                    'bill_data': result
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create vendor bill in NetSuite',
                    'netsuite_bill_id': None
                }
                
        except Exception as e:
            logger.error(f"Error syncing invoice to NetSuite: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'netsuite_bill_id': None
            }