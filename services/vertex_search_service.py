import os
import json
import hashlib
from datetime import datetime
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account
from config import config

class VertexSearchService:
    """Service for querying Vertex AI Search (RAG) for vendor context and invoice extraction learning"""
    
    def __init__(self):
        credentials = None
        
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
            except json.JSONDecodeError:
                print("Warning: Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH
            )
        
        if credentials:
            self.client = discoveryengine.SearchServiceClient(credentials=credentials)
            self.document_client = discoveryengine.DocumentServiceClient(credentials=credentials)
        else:
            self.client = discoveryengine.SearchServiceClient()
            self.document_client = discoveryengine.DocumentServiceClient()
        
        # Build parent path for document operations
        self.parent = (
            f"projects/{config.GOOGLE_CLOUD_PROJECT_NUMBER}/locations/global/"
            f"collections/{config.VERTEX_SEARCH_COLLECTION}/dataStores/{config.VERTEX_SEARCH_DATA_STORE_ID}/"
            f"branches/default_branch"
        )
    
    def search_vendor(self, vendor_query, max_results=5):
        """
        Search for vendor information in the RAG datastore
        
        Args:
            vendor_query: Vendor name to search for
            max_results: Maximum number of results to return
            
        Returns:
            List of search results with vendor context
        """
        if not vendor_query:
            return []
        
        request = discoveryengine.SearchRequest(
            serving_config=config.VERTEX_SEARCH_SERVING_CONFIG,
            query=vendor_query,
            page_size=max_results
        )
        
        try:
            response = self.client.search(request)
            results = []
            
            for result in response.results:
                document_data = {}
                
                if hasattr(result, 'document'):
                    doc = result.document
                    
                    if hasattr(doc, 'derived_struct_data'):
                        document_data = dict(doc.derived_struct_data)
                    elif hasattr(doc, 'struct_data'):
                        document_data = dict(doc.struct_data)
                
                results.append({
                    'id': result.id if hasattr(result, 'id') else None,
                    'data': document_data
                })
            
            return results
        except Exception as e:
            print(f"Error searching vendor: {e}")
            return []
    
    def format_context(self, search_results):
        """
        Format search results into context string for Gemini
        
        Returns:
            Formatted context string (always returns a string, never None/empty)
        """
        if not search_results or len(search_results) == 0:
            return "No vendor history found in database. This is a new vendor or vendor name was not detected."
        
        context_parts = []
        for i, result in enumerate(search_results, 1):
            data = result.get('data', {})
            
            vendor_name = data.get('vendor_name', 'Unknown')
            vendor_id = data.get('vendor_id', 'N/A')
            country = data.get('country', 'Unknown')
            last_amount = data.get('last_invoice_amount', 'N/A')
            
            context_parts.append(
                f"Match {i}: Vendor '{vendor_name}' (ID: {vendor_id}) in {country}. "
                f"Last invoice: {last_amount}."
            )
        
        return " ".join(context_parts)
    
    def search_similar_invoices(self, document_text, vendor_name=None, limit=3):
        """
        Search for similar past invoice extractions in the RAG datastore
        
        Args:
            document_text: Raw OCR text from the invoice
            vendor_name: Optional vendor name to narrow search
            limit: Maximum number of similar invoices to return
            
        Returns:
            List of similar invoice extraction results with metadata
        """
        if not document_text:
            return []
        
        # Build search query combining vendor name and document snippet
        query_parts = []
        if vendor_name:
            query_parts.append(f"vendor:{vendor_name}")
        
        # Use first 500 chars of document text for similarity matching
        doc_snippet = document_text[:500].replace('\n', ' ')
        query_parts.append(f"invoice extraction: {doc_snippet}")
        
        query = " ".join(query_parts)
        
        request = discoveryengine.SearchRequest(
            serving_config=config.VERTEX_SEARCH_SERVING_CONFIG,
            query=query,
            page_size=limit,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
        )
        
        try:
            response = self.client.search(request)
            results = []
            
            for result in response.results:
                document_data = {}
                
                if hasattr(result, 'document'):
                    doc = result.document
                    
                    if hasattr(doc, 'derived_struct_data'):
                        document_data = dict(doc.derived_struct_data)
                    elif hasattr(doc, 'struct_data'):
                        document_data = dict(doc.struct_data)
                
                # Only include results that have extraction metadata
                if document_data.get('extraction_type') == 'invoice_extraction':
                    results.append({
                        'id': result.id if hasattr(result, 'id') else None,
                        'data': document_data
                    })
            
            return results
        except Exception as e:
            print(f"Error searching similar invoices: {e}")
            return []
    
    def format_invoice_extraction_context(self, search_results):
        """
        Format invoice extraction search results into context string for Gemini
        
        Returns:
            Formatted context string showing past successful extractions
        """
        if not search_results or len(search_results) == 0:
            return "No similar invoice extractions found in knowledge base. This appears to be a new vendor or document pattern."
        
        context_parts = ["PAST SUCCESSFUL EXTRACTIONS FROM SIMILAR INVOICES:"]
        
        for i, result in enumerate(search_results, 1):
            data = result.get('data', {})
            
            vendor_name = data.get('vendor_name', 'Unknown')
            doc_type = data.get('document_type', 'Invoice')
            currency = data.get('currency', 'USD')
            confidence = data.get('confidence_score', 0.0)
            timestamp = data.get('extraction_timestamp', 'Unknown')
            
            # Extract key fields from past extraction
            extracted_data = data.get('extracted_data', {})
            invoice_num = extracted_data.get('invoiceNumber', 'N/A')
            total = extracted_data.get('totals', {}).get('total', 'N/A')
            
            context_parts.append(
                f"\nExample {i}: Vendor='{vendor_name}', Type={doc_type}, "
                f"Invoice#={invoice_num}, Total={currency} {total}, "
                f"Confidence={confidence:.2f}, Extracted={timestamp}"
            )
            
            # Include line items if available (first 2 for context)
            line_items = extracted_data.get('lineItems', [])
            if line_items:
                context_parts.append(f"  Line items: {len(line_items)} items extracted")
                for idx, item in enumerate(line_items[:2], 1):
                    desc = item.get('description', 'N/A')
                    qty = item.get('quantity', 0)
                    price = item.get('unitPrice', 0)
                    context_parts.append(f"    - {desc} (Qty:{qty} @ {currency}{price})")
        
        return "\n".join(context_parts)
    
    def store_invoice_extraction(self, document_text, vendor_name, extracted_data, success=True):
        """
        Store successful invoice extraction to Vertex AI Search for future learning
        
        Args:
            document_text: Raw OCR text from the invoice
            vendor_name: Extracted vendor name
            extracted_data: Complete validated extraction result from Gemini
            success: Whether extraction was successful (default: True)
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            # Generate unique document ID based on invoice number and timestamp
            invoice_num = extracted_data.get('invoiceNumber', 'unknown')
            timestamp = datetime.utcnow().isoformat()
            doc_hash = hashlib.md5(f"{vendor_name}_{invoice_num}_{timestamp}".encode()).hexdigest()[:12]
            doc_id = f"invoice_extraction_{doc_hash}"
            
            # Extract key metadata for storage
            document_type = extracted_data.get('documentType', 'Invoice')
            currency = extracted_data.get('currency', 'USD')
            confidence_score = extracted_data.get('extractionConfidence', 0.0)
            
            # Extract multi-currency metadata
            multi_currency_data = extracted_data.get('multiCurrency', {})
            is_multi_currency = multi_currency_data.get('isMultiCurrency', False)
            base_currency = multi_currency_data.get('baseCurrency', currency)
            settlement_currency = multi_currency_data.get('settlementCurrency', currency)
            exchange_rate = multi_currency_data.get('exchangeRate')
            
            # Build currencies_involved list
            currencies_involved = [currency]
            if is_multi_currency:
                if base_currency not in currencies_involved:
                    currencies_involved.append(base_currency)
                if settlement_currency not in currencies_involved:
                    currencies_involved.append(settlement_currency)
            
            # Create searchable metadata
            metadata = {
                'extraction_type': 'invoice_extraction',
                'vendor_name': vendor_name or 'Unknown',
                'document_type': document_type,
                'currency': currency,
                'confidence_score': confidence_score,
                'extraction_timestamp': timestamp,
                'success': success,
                # Multi-currency metadata
                'is_multi_currency': is_multi_currency,
                'currencies_involved': currencies_involved,
                'base_currency': base_currency,
                'settlement_currency': settlement_currency,
                'exchange_rate': exchange_rate,
                'extracted_data': {
                    'invoiceNumber': extracted_data.get('invoiceNumber'),
                    'documentDate': extracted_data.get('documentDate'),
                    'totals': extracted_data.get('totals', {}),
                    'lineItems': extracted_data.get('lineItems', []),
                    'vendor': extracted_data.get('vendor', {}),
                    'buyer': extracted_data.get('buyer', {}),
                    'currency': currency,
                    'multiCurrency': multi_currency_data,
                }
            }
            
            # Create searchable text content for better RAG retrieval
            multi_currency_info = ""
            if is_multi_currency:
                multi_currency_info = f"""
            Multi-Currency Invoice:
            - Base Currency (unit prices): {base_currency}
            - Settlement Currency (totals): {settlement_currency}
            - Exchange Rate: {exchange_rate if exchange_rate else 'N/A'}
            - Currencies Involved: {', '.join(currencies_involved)}
            """
            
            text_content = f"""
            Invoice Extraction Knowledge Base Entry
            
            Vendor: {vendor_name}
            Document Type: {document_type}
            Invoice Number: {extracted_data.get('invoiceNumber', 'N/A')}
            Date: {extracted_data.get('documentDate', 'N/A')}
            Currency: {currency}{multi_currency_info}
            Total: {extracted_data.get('totals', {}).get('total', 'N/A')}
            
            Confidence Score: {confidence_score * 100:.1f}%
            Extraction Status: {'Success' if success else 'Failed'}
            Timestamp: {timestamp}
            
            Line Items:
            {json.dumps(extracted_data.get('lineItems', []), indent=2)}
            
            Document Text Snippet:
            {document_text[:1000]}
            """
            
            # Create document for Vertex AI Search
            document = discoveryengine.Document(
                name=f"{self.parent}/documents/{doc_id}",
                id=doc_id,
                derived_struct_data=metadata,
                content=discoveryengine.Document.Content(
                    mime_type="text/plain",
                    raw_bytes=text_content.encode('utf-8')
                )
            )
            
            # Store in Vertex AI Search
            request = discoveryengine.CreateDocumentRequest(
                parent=self.parent,
                document=document,
                document_id=doc_id
            )
            
            self.document_client.create_document(request=request)
            print(f"✓ Stored invoice extraction to knowledge base: {vendor_name} - Invoice #{invoice_num}")
            return True
            
        except Exception as e:
            print(f"⚠ Error storing invoice extraction: {e}")
            # Don't fail the extraction if storage fails
            return False
