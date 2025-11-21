def extract_vendor_name(entities):
    """
    Extract vendor name from Document AI entities
    
    Args:
        entities: Dictionary of extracted entities from Document AI
        
    Returns:
        Vendor name string or None
    """
    if not entities:
        return None
    
    vendor_fields = [
        'supplier_name',
        'vendor_name',
        'remit_to_name',
        'seller_name',
        'from_name'
    ]
    
    for field in vendor_fields:
        if field in entities and entities[field]:
            vendor_list = entities[field]
            if isinstance(vendor_list, list) and len(vendor_list) > 0:
                return vendor_list[0].get('value', '')
            elif isinstance(vendor_list, str):
                return vendor_list
    
    return None
