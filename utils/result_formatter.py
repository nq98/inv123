import json

def format_search_results(search_results):
    """
    Format Vertex AI Search results into a readable context string
    
    Args:
        search_results: List of search results from Vertex AI Search
        
    Returns:
        Formatted context string
    """
    if not search_results:
        return "No vendor history found in database."
    
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

def format_json_output(data, indent=2):
    """Format dictionary as pretty JSON string"""
    return json.dumps(data, indent=indent, ensure_ascii=False)
