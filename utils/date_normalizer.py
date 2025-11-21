from datetime import datetime
import re

def normalize_date(date_string, country_code='US'):
    """
    Normalize date to ISO 8601 format (YYYY-MM-DD)
    
    Args:
        date_string: Date string in various formats
        country_code: Country code to determine date format (US uses MM/DD, others DD/MM)
        
    Returns:
        Normalized date string in YYYY-MM-DD format
    """
    if not date_string:
        return None
    
    date_string = str(date_string).strip()
    
    us_format_countries = ['US', 'USA', 'United States']
    use_mdy = country_code in us_format_countries
    
    common_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d'),
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', '%m-%d-%Y' if use_mdy else '%d-%m-%Y'),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y' if use_mdy else '%d/%m/%Y'),
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', '%m.%d.%Y' if use_mdy else '%d.%m.%Y'),
    ]
    
    for pattern, date_format in common_patterns:
        if re.match(pattern, date_string):
            try:
                dt = datetime.strptime(date_string, date_format)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    return date_string
