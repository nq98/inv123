import os
import json
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account
from config import config

class VertexSearchService:
    """Service for querying Vertex AI Search (RAG) for vendor context"""
    
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
        else:
            self.client = discoveryengine.SearchServiceClient()
    
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
