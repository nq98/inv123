"""
AI Invoice Composer Service
Provides intelligent invoice generation features:
- Vendor autocomplete from BigQuery
- Magic Fill from natural language
- Semantic validation
"""

import json
import uuid
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from services.bigquery_service import BigQueryService
from services.gemini_service import GeminiService
from google import genai
from google.genai import types


class InvoiceComposer:
    """
    AI-powered invoice composition with natural language understanding
    and intelligent validation
    """
    
    def __init__(self):
        """Initialize services"""
        self.bigquery_service = BigQueryService()
        self.gemini_service = GeminiService()
        
        # Tax rates by country
        self.tax_rates = {
            'United Kingdom': {'type': 'VAT', 'rate': 20.0},
            'UK': {'type': 'VAT', 'rate': 20.0},
            'United States': {'type': 'Sales Tax', 'rate': 8.0},  # Average
            'USA': {'type': 'Sales Tax', 'rate': 8.0},
            'US': {'type': 'Sales Tax', 'rate': 8.0},
            'Israel': {'type': 'VAT', 'rate': 17.0},
            'Germany': {'type': 'VAT', 'rate': 19.0},
            'France': {'type': 'VAT', 'rate': 20.0},
            'Italy': {'type': 'VAT', 'rate': 22.0},
            'Spain': {'type': 'VAT', 'rate': 21.0},
            'Netherlands': {'type': 'VAT', 'rate': 21.0},
            'Canada': {'type': 'GST', 'rate': 5.0},
            'Australia': {'type': 'GST', 'rate': 10.0},
            'Japan': {'type': 'Consumption Tax', 'rate': 10.0},
            'India': {'type': 'GST', 'rate': 18.0},
            'Brazil': {'type': 'ICMS', 'rate': 17.0},
            'Mexico': {'type': 'IVA', 'rate': 16.0},
            'China': {'type': 'VAT', 'rate': 13.0},
            'Singapore': {'type': 'GST', 'rate': 8.0},
            'Hong Kong': {'type': 'None', 'rate': 0.0},
            'UAE': {'type': 'VAT', 'rate': 5.0},
            'Switzerland': {'type': 'VAT', 'rate': 7.7},
            'Norway': {'type': 'VAT', 'rate': 25.0},
            'Sweden': {'type': 'VAT', 'rate': 25.0},
            'Denmark': {'type': 'VAT', 'rate': 25.0}
        }
        
        # Currency mapping
        self.country_currencies = {
            'United Kingdom': 'GBP',
            'UK': 'GBP',
            'United States': 'USD',
            'USA': 'USD',
            'US': 'USD',
            'Israel': 'ILS',
            'Germany': 'EUR',
            'France': 'EUR',
            'Italy': 'EUR',
            'Spain': 'EUR',
            'Netherlands': 'EUR',
            'Canada': 'CAD',
            'Australia': 'AUD',
            'Japan': 'JPY',
            'India': 'INR',
            'Brazil': 'BRL',
            'Mexico': 'MXN',
            'China': 'CNY',
            'Singapore': 'SGD',
            'Hong Kong': 'HKD',
            'UAE': 'AED',
            'Switzerland': 'CHF',
            'Norway': 'NOK',
            'Sweden': 'SEK',
            'Denmark': 'DKK'
        }
    
    def search_vendors(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for vendors in BigQuery global_vendors table
        
        Args:
            query: Search query (vendor name or partial name)
            limit: Maximum number of results
            
        Returns:
            List of vendor dictionaries
        """
        try:
            # SQL query to search vendors
            sql = f"""
            SELECT 
                vendor_id,
                global_name,
                normalized_name,
                ARRAY_TO_STRING(emails, ', ') as email,
                ARRAY_TO_STRING(countries, ', ') as country,
                custom_attributes
            FROM vendors_ai.global_vendors
            WHERE 
                LOWER(global_name) LIKE LOWER('%{query}%')
                OR LOWER(normalized_name) LIKE LOWER('%{query}%')
            ORDER BY 
                CASE 
                    WHEN LOWER(global_name) = LOWER('{query}') THEN 1
                    WHEN LOWER(global_name) LIKE LOWER('{query}%') THEN 2
                    ELSE 3
                END,
                global_name
            LIMIT {limit}
            """
            
            # Execute query
            query_job = self.bigquery_service.client.query(sql)
            results = []
            
            for row in query_job:
                vendor = {
                    'vendor_id': row.vendor_id,
                    'name': row.global_name,
                    'normalized_name': row.normalized_name,
                    'email': row.email or '',
                    'country': row.country or '',
                    'custom_attributes': row.custom_attributes or {}
                }
                
                # Extract additional fields from custom_attributes if available
                if vendor['custom_attributes']:
                    attrs = vendor['custom_attributes']
                    vendor['address'] = attrs.get('address', '')
                    vendor['city'] = attrs.get('city', '')
                    vendor['tax_id'] = attrs.get('tax_id', '')
                    vendor['phone'] = attrs.get('phone', '')
                
                results.append(vendor)
            
            return results
            
        except Exception as e:
            print(f"Error searching vendors: {e}")
            return []
    
    def magic_fill(self, natural_language_input: str, vendor_info: Optional[Dict] = None) -> Dict:
        """
        Parse natural language input to fill invoice fields using Gemini
        
        Args:
            natural_language_input: Natural language description (e.g., "5 hours consulting at $100 per hour")
            vendor_info: Optional vendor information for context
            
        Returns:
            Structured invoice data
        """
        
        # Prepare vendor context
        vendor_context = ""
        if vendor_info:
            vendor_context = f"""
            Vendor Information:
            - Name: {vendor_info.get('name', 'Unknown')}
            - Country: {vendor_info.get('country', 'Unknown')}
            - Email: {vendor_info.get('email', '')}
            - Tax ID: {vendor_info.get('tax_id', '')}
            """
        
        # Prepare the prompt for Gemini
        prompt = f"""You are an AI Invoice Composer. Parse the following natural language input 
        and extract structured invoice information.

        {vendor_context}

        Natural Language Input: "{natural_language_input}"

        Extract and return the following information as JSON:
        {{
            "line_items": [
                {{
                    "description": "string",
                    "quantity": number,
                    "unit_price": number,
                    "discount_percent": number (0 if not mentioned),
                    "tracking_category": "string (e.g., Consulting, Products, Services)"
                }}
            ],
            "currency": "string (USD if not specified)",
            "notes": "string (any additional context)",
            "suggested_tax_rate": number (based on vendor country if known),
            "payment_terms": "string (Net 30 if not specified)"
        }}

        Examples of natural language inputs and expected parsing:
        - "5 hours of consulting at 100 dollars per hour" -> quantity: 5, unit_price: 100, description: "Consulting services"
        - "Website development for $5000 with 10% discount" -> quantity: 1, unit_price: 5000, discount_percent: 10
        - "3 software licenses at €200 each" -> quantity: 3, unit_price: 200, currency: "EUR"
        - "Monthly retainer 2500 pounds" -> quantity: 1, unit_price: 2500, currency: "GBP"

        Important:
        - Parse numbers correctly (handle "k" as thousands, "m" as millions)
        - Detect currency from context (dollar->USD, euro->EUR, pound->GBP, etc.)
        - If vendor country is known, suggest appropriate tax rate
        - Group similar items together
        
        Return ONLY valid JSON, no markdown or commentary."""
        
        try:
            # Call Gemini for parsing
            response = self.gemini_service._generate_content_with_fallback(
                model='gemini-2.0-flash-exp',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    top_k=20,
                    top_p=0.95,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                    system_instruction="You are an expert invoice parser. Return only valid JSON."
                )
            )
            
            # Parse the response
            result_text = response.text.strip()
            
            # Clean up response if needed
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            
            parsed_data = json.loads(result_text)
            
            # Add vendor-specific tax information if available
            if vendor_info and vendor_info.get('country'):
                country = vendor_info.get('country')
                if country in self.tax_rates:
                    tax_info = self.tax_rates[country]
                    parsed_data['tax_type'] = tax_info['type']
                    parsed_data['suggested_tax_rate'] = tax_info['rate']
                    
                    # Apply tax rate to line items if not already specified
                    for item in parsed_data.get('line_items', []):
                        if 'tax_rate' not in item or item['tax_rate'] == 0:
                            item['tax_rate'] = tax_info['rate']
                
                # Set currency based on country if not specified
                if country in self.country_currencies and not parsed_data.get('currency'):
                    parsed_data['currency'] = self.country_currencies[country]
            
            return {
                'success': True,
                'data': parsed_data,
                'original_input': natural_language_input
            }
            
        except Exception as e:
            print(f"Error in magic fill: {e}")
            
            # Fallback: Try basic regex parsing
            fallback_data = self._fallback_parser(natural_language_input)
            return {
                'success': False,
                'error': str(e),
                'data': fallback_data,
                'original_input': natural_language_input
            }
    
    def _fallback_parser(self, text: str) -> Dict:
        """
        Fallback parser using regex when AI fails
        
        Args:
            text: Natural language input
            
        Returns:
            Basic parsed structure
        """
        data = {
            'line_items': [],
            'currency': 'USD',
            'notes': '',
            'payment_terms': 'Net 30'
        }
        
        # Try to extract quantity and price patterns
        quantity_pattern = r'(\d+(?:\.\d+)?)\s*(?:hours?|items?|units?|licenses?|months?|days?)'
        price_pattern = r'(?:[$€£¥₹]|USD|EUR|GBP)\s*(\d+(?:,\d{3})*(?:\.\d+)?)|(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:dollars?|euros?|pounds?|usd|eur|gbp)'
        
        quantities = re.findall(quantity_pattern, text, re.IGNORECASE)
        prices = re.findall(price_pattern, text, re.IGNORECASE)
        
        # Extract quantity
        quantity = 1
        if quantities:
            quantity = float(quantities[0])
        
        # Extract price
        unit_price = 0
        if prices:
            price_match = prices[0]
            if isinstance(price_match, tuple):
                price_str = price_match[0] if price_match[0] else price_match[1]
            else:
                price_str = price_match
            unit_price = float(price_str.replace(',', ''))
        
        # Detect currency
        if '€' in text or 'euro' in text.lower():
            data['currency'] = 'EUR'
        elif '£' in text or 'pound' in text.lower():
            data['currency'] = 'GBP'
        elif '¥' in text or 'yen' in text.lower():
            data['currency'] = 'JPY'
        elif '₹' in text or 'rupee' in text.lower():
            data['currency'] = 'INR'
        
        # Create line item
        if unit_price > 0:
            description = text[:100]  # Use first 100 chars as description
            data['line_items'].append({
                'description': description,
                'quantity': quantity,
                'unit_price': unit_price,
                'discount_percent': 0,
                'tax_rate': 0,
                'tracking_category': 'General'
            })
        
        return data
    
    def validate_invoice(self, invoice_data: Dict) -> Dict:
        """
        Perform semantic validation on invoice data using AI
        
        Args:
            invoice_data: Complete invoice data structure
            
        Returns:
            Validation result with warnings and errors
        """
        
        # Prepare validation prompt
        vendor = invoice_data.get('vendor', {})
        tax_type = invoice_data.get('tax_type', '')
        
        prompt = f"""Validate the following invoice for logical consistency and compliance:

        Invoice Data:
        - Vendor Country: {vendor.get('country', 'Unknown')}
        - Selected Tax Type: {tax_type}
        - Currency: {invoice_data.get('currency', 'USD')}
        - Line Items: {json.dumps(invoice_data.get('line_items', []))}
        
        Check for:
        1. Tax Type Mismatch: Does the selected tax type match the vendor's country?
        2. Currency Consistency: Is the currency appropriate for the vendor's location?
        3. Tax Rate Accuracy: Are the tax rates correct for the jurisdiction?
        4. Data Completeness: Are all required fields present?
        5. Calculation Accuracy: Do the amounts calculate correctly?
        
        Return a JSON response:
        {{
            "is_valid": boolean,
            "warnings": [
                {{
                    "field": "string",
                    "message": "string",
                    "severity": "low|medium|high"
                }}
            ],
            "errors": [
                {{
                    "field": "string", 
                    "message": "string"
                }}
            ],
            "suggestions": [
                {{
                    "field": "string",
                    "current_value": "string",
                    "suggested_value": "string",
                    "reason": "string"
                }}
            ]
        }}
        
        Return ONLY valid JSON, no markdown or commentary."""
        
        try:
            # Call Gemini for validation
            response = self.gemini_service._generate_content_with_fallback(
                model='gemini-2.0-flash-exp',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    top_k=20,
                    top_p=0.95,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                    system_instruction="You are an expert invoice auditor. Return only valid JSON."
                )
            )
            
            # Parse the response
            result_text = response.text.strip()
            
            # Clean up response if needed
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            
            validation_result = json.loads(result_text)
            
            return {
                'success': True,
                'validation': validation_result
            }
            
        except Exception as e:
            print(f"Error in semantic validation: {e}")
            
            # Fallback: Basic rule-based validation
            return self._fallback_validation(invoice_data)
    
    def _fallback_validation(self, invoice_data: Dict) -> Dict:
        """
        Fallback validation using basic rules
        
        Args:
            invoice_data: Invoice data to validate
            
        Returns:
            Basic validation result
        """
        warnings = []
        errors = []
        suggestions = []
        
        vendor = invoice_data.get('vendor', {})
        vendor_country = vendor.get('country', '')
        tax_type = invoice_data.get('tax_type', '')
        currency = invoice_data.get('currency', 'USD')
        
        # Check tax type matches country
        if vendor_country in self.tax_rates:
            expected_tax = self.tax_rates[vendor_country]
            if tax_type and tax_type != expected_tax['type'] and tax_type != 'None':
                warnings.append({
                    'field': 'tax_type',
                    'message': f"Tax type '{tax_type}' may not be appropriate for {vendor_country}. Expected '{expected_tax['type']}'",
                    'severity': 'medium'
                })
                suggestions.append({
                    'field': 'tax_type',
                    'current_value': tax_type,
                    'suggested_value': expected_tax['type'],
                    'reason': f"Standard tax type for {vendor_country}"
                })
        
        # Check currency matches country
        if vendor_country in self.country_currencies:
            expected_currency = self.country_currencies[vendor_country]
            if currency != expected_currency:
                warnings.append({
                    'field': 'currency',
                    'message': f"Currency '{currency}' may not be typical for {vendor_country}. Usually '{expected_currency}'",
                    'severity': 'low'
                })
        
        # Check for required fields
        if not vendor.get('name'):
            errors.append({
                'field': 'vendor.name',
                'message': 'Vendor name is required'
            })
        
        if not invoice_data.get('line_items'):
            errors.append({
                'field': 'line_items',
                'message': 'At least one line item is required'
            })
        
        # Check line items
        for i, item in enumerate(invoice_data.get('line_items', [])):
            if not item.get('description'):
                errors.append({
                    'field': f'line_items[{i}].description',
                    'message': 'Description is required for all line items'
                })
            
            if item.get('quantity', 0) <= 0:
                errors.append({
                    'field': f'line_items[{i}].quantity',
                    'message': 'Quantity must be greater than zero'
                })
            
            if item.get('unit_price', 0) < 0:
                errors.append({
                    'field': f'line_items[{i}].unit_price',
                    'message': 'Unit price cannot be negative'
                })
        
        is_valid = len(errors) == 0
        
        return {
            'success': True,
            'validation': {
                'is_valid': is_valid,
                'warnings': warnings,
                'errors': errors,
                'suggestions': suggestions
            }
        }
    
    def generate_invoice_number(self, prefix: str = "AUTO_GEN") -> str:
        """
        Generate a unique invoice number
        
        Args:
            prefix: Prefix for the invoice number
            
        Returns:
            Unique invoice number
        """
        timestamp = datetime.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:8].upper()
        return f"{prefix}_{timestamp}_{unique_id}"
    
    def prepare_invoice_for_bigquery(self, invoice_data: Dict, gcs_uri: str, file_info: Dict) -> Dict:
        """
        Prepare invoice data for insertion into BigQuery
        
        Args:
            invoice_data: Complete invoice data
            gcs_uri: GCS URI of the generated PDF
            file_info: File information (size, type, name)
            
        Returns:
            Formatted data for BigQuery insertion
        """
        
        # Calculate total amount
        total_amount = 0
        for item in invoice_data.get('line_items', []):
            quantity = item.get('quantity', 1)
            unit_price = item.get('unit_price', 0)
            discount_percent = item.get('discount_percent', 0)
            tax_rate = item.get('tax_rate', 0)
            
            subtotal = quantity * unit_price
            discount = subtotal * (discount_percent / 100)
            after_discount = subtotal - discount
            tax = after_discount * (tax_rate / 100)
            total_amount += after_discount + tax
        
        # Format for BigQuery
        return {
            'invoice_id': invoice_data.get('invoice_number'),
            'vendor_id': invoice_data.get('vendor', {}).get('vendor_id', ''),
            'vendor_name': invoice_data.get('vendor', {}).get('name', ''),
            'client_id': invoice_data.get('buyer', {}).get('name', 'default_client'),
            'amount': total_amount,
            'currency': invoice_data.get('currency', 'USD'),
            'invoice_date': invoice_data.get('issue_date', datetime.now().isoformat()),
            'status': 'generated',
            'gcs_uri': gcs_uri,
            'file_type': 'pdf',
            'file_size': file_info.get('file_size', 0),
            'metadata': {
                'generated': True,
                'generation_timestamp': datetime.now().isoformat(),
                'line_items': invoice_data.get('line_items', []),
                'tax_type': invoice_data.get('tax_type', ''),
                'payment_terms': invoice_data.get('payment_terms', 'Net 30'),
                'po_number': invoice_data.get('po_number', ''),
                'notes': invoice_data.get('notes', ''),
                'buyer': invoice_data.get('buyer', {})
            }
        }
    
    def get_tax_info_for_country(self, country: str) -> Dict:
        """
        Get tax information for a given country
        
        Args:
            country: Country name
            
        Returns:
            Tax information dictionary
        """
        return self.tax_rates.get(country, {'type': 'None', 'rate': 0.0})
    
    def get_currency_for_country(self, country: str) -> str:
        """
        Get default currency for a given country
        
        Args:
            country: Country name
            
        Returns:
            Currency code
        """
        return self.country_currencies.get(country, 'USD')