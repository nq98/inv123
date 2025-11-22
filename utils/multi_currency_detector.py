import re
from typing import Dict, List, Optional, Any


class MultiCurrencyDetector:
    """
    Detects and analyzes multi-currency scenarios in invoice documents.
    
    This service identifies:
    - Multiple currency symbols in the same document
    - Exchange rate statements
    - Base currency (unit prices) vs settlement currency (totals)
    - Expected currency conversions and math verification
    """
    
    # Currency symbols and their ISO codes
    CURRENCY_SYMBOLS = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₪': 'ILS',
        '₹': 'INR',
        '₽': 'RUB',
        '₩': 'KRW',
        'R$': 'BRL',
        'C$': 'CAD',
        'A$': 'AUD',
        'CHF': 'CHF',
        'kr': 'SEK',
        'zł': 'PLN',
        '₺': 'TRY',
        'د.إ': 'AED',
        'ريال': 'SAR'
    }
    
    # ISO currency codes
    ISO_CURRENCIES = [
        'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'ILS', 'AED', 'SAR', 'INR', 'CAD',
        'AUD', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'RON', 'BGN',
        'HRK', 'RSD', 'TRY', 'RUB', 'UAH', 'BRL', 'MXN', 'ARS', 'CLP', 'COP',
        'PEN', 'ZAR', 'EGP', 'KES', 'NGN', 'GHS', 'THB', 'VND', 'IDR', 'MYR',
        'SGD', 'PHP', 'KRW', 'TWD', 'HKD', 'NZD', 'PKR', 'BDT', 'LKR', 'NPR'
    ]
    
    def __init__(self):
        """Initialize the multi-currency detector with regex patterns"""
        # Exchange rate patterns
        # Matches: "1 USD = 3.27 ILS", "(1USD=3.27ILS)", "Exchange rate: 3.27", "1USD = 3.27ILS"
        self.exchange_rate_patterns = [
            # Pattern: "1 USD = 3.27 ILS" or "1USD=3.27ILS"
            r'1\s*([A-Z]{3})\s*=\s*([0-9]+\.?[0-9]*)\s*([A-Z]{3})',
            # Pattern: "(1USD = 3.27ILS)" or "(1 USD = 3.27 ILS)"
            r'\(1\s*([A-Z]{3})\s*=\s*([0-9]+\.?[0-9]*)\s*([A-Z]{3})\)',
            # Pattern: "Exchange rate: 3.27" (requires context)
            r'[Ee]xchange\s+[Rr]ate[:\s]+([0-9]+\.?[0-9]*)',
            # Pattern: "Rate: 1 USD = 3.27 ILS"
            r'[Rr]ate[:\s]+1\s*([A-Z]{3})\s*=\s*([0-9]+\.?[0-9]*)\s*([A-Z]{3})',
            # Pattern: "USD/ILS: 3.27"
            r'([A-Z]{3})/([A-Z]{3})[:\s]+([0-9]+\.?[0-9]*)',
            # Pattern: Hebrew "שער חליפין" (exchange rate) followed by number
            r'שער\s+חליפין[:\s]+([0-9]+\.?[0-9]*)'
        ]
        
        # Amount + currency patterns
        # Matches: "758.64 ILS", "$8.00", "8.00 USD", "₪758.64"
        self.amount_currency_patterns = [
            # Pattern: "123.45 USD" or "123.45USD"
            r'([0-9,]+\.?[0-9]*)\s*([A-Z]{3})\b',
            # Pattern: "$123.45" or "€123.45"
            r'([$€£¥₪₹₽₩])\s*([0-9,]+\.?[0-9]*)',
            # Pattern: "123.45$" (some locales)
            r'([0-9,]+\.?[0-9]*)\s*([$€£¥₪₹₽₩])',
            # Pattern: "ILS 123.45"
            r'\b([A-Z]{3})\s+([0-9,]+\.?[0-9]*)'
        ]
    
    def analyze_invoice_currencies(self, document_text: str, document_ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect multi-currency scenarios from invoice text and Document AI results.
        
        Args:
            document_text: Raw OCR text from the invoice
            document_ai_result: Structured entities from Document AI
            
        Returns:
            Dictionary with multi-currency analysis:
            {
                'currency_symbols_found': List of detected currency symbols/codes,
                'exchange_rates': Dict of exchange rates (e.g., {"USD_TO_ILS": 3.27}),
                'is_multi_currency': Boolean,
                'base_currency': Currency of line items (e.g., "USD"),
                'settlement_currency': Currency of final total (e.g., "ILS"),
                'expected_conversions': Dict with computed totals,
                'context_summary': Human-readable summary for Gemini
            }
        """
        if not document_text:
            return self._empty_result()
        
        # Step 1: Extract all currency mentions
        currencies_found = self._extract_currencies(document_text)
        
        # Step 2: Find exchange rate statements
        exchange_rates = self._extract_exchange_rates(document_text)
        
        # Step 3: Determine if multi-currency scenario exists
        is_multi_currency = len(currencies_found) > 1 or len(exchange_rates) > 0
        
        # Step 4: Identify base vs settlement currency
        base_currency, settlement_currency = self._identify_currency_hierarchy(
            document_text, currencies_found, exchange_rates, document_ai_result
        )
        
        # Step 5: Compute expected conversions (if we have exchange rates)
        expected_conversions = self._compute_expected_conversions(
            document_ai_result, exchange_rates, base_currency, settlement_currency
        )
        
        # Step 6: Create context summary for Gemini
        context_summary = self._generate_context_summary(
            currencies_found, exchange_rates, base_currency, 
            settlement_currency, is_multi_currency, expected_conversions
        )
        
        return {
            'currency_symbols_found': list(currencies_found),
            'exchange_rates': exchange_rates,
            'is_multi_currency': is_multi_currency,
            'base_currency': base_currency,
            'settlement_currency': settlement_currency,
            'expected_conversions': expected_conversions,
            'context_summary': context_summary
        }
    
    def _extract_currencies(self, text: str) -> set:
        """Extract all currency symbols and codes from text"""
        currencies = set()
        
        # Find currency symbols
        for symbol, code in self.CURRENCY_SYMBOLS.items():
            if symbol in text:
                currencies.add(code)
        
        # Find ISO currency codes
        for currency_code in self.ISO_CURRENCIES:
            # Use word boundaries to avoid false matches
            if re.search(r'\b' + currency_code + r'\b', text):
                currencies.add(currency_code)
        
        return currencies
    
    def _extract_exchange_rates(self, text: str) -> Dict[str, float]:
        """
        Extract exchange rate statements from text.
        
        Returns:
            Dict mapping "BASE_TO_SETTLEMENT" to exchange rate value
            e.g., {"USD_TO_ILS": 3.27}
        """
        exchange_rates = {}
        
        for pattern in self.exchange_rate_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                groups = match.groups()
                
                # Different patterns have different group structures
                if len(groups) == 3 and groups[0] and groups[1] and groups[2]:
                    # Pattern: "1 USD = 3.27 ILS"
                    base_currency = groups[0].upper()
                    rate_value = float(groups[1])
                    settlement_currency = groups[2].upper()
                    
                    if base_currency in self.ISO_CURRENCIES and settlement_currency in self.ISO_CURRENCIES:
                        key = f"{base_currency}_TO_{settlement_currency}"
                        exchange_rates[key] = rate_value
                
                elif len(groups) == 1 and groups[0]:
                    # Pattern: "Exchange rate: 3.27" - needs context to determine currencies
                    # We'll try to infer from nearby currency mentions
                    rate_value = float(groups[0])
                    
                    # Look for currencies in surrounding context (50 chars before/after)
                    match_start = match.start()
                    context_start = max(0, match_start - 50)
                    context_end = min(len(text), match.end() + 50)
                    context = text[context_start:context_end]
                    
                    context_currencies = self._extract_currencies(context)
                    if len(context_currencies) == 2:
                        # Assume first is base, second is settlement
                        curr_list = sorted(list(context_currencies))
                        key = f"{curr_list[0]}_TO_{curr_list[1]}"
                        exchange_rates[key] = rate_value
        
        return exchange_rates
    
    def _identify_currency_hierarchy(
        self, text: str, currencies_found: set, 
        exchange_rates: Dict[str, float], document_ai_result: Dict[str, Any]
    ) -> tuple:
        """
        Identify which currency is used for unit prices (base) vs totals (settlement).
        
        Returns:
            Tuple of (base_currency, settlement_currency)
        """
        # If exchange rates detected, extract from the key
        if exchange_rates:
            # Take the first exchange rate
            first_rate_key = list(exchange_rates.keys())[0]
            # Format: "USD_TO_ILS"
            parts = first_rate_key.split('_TO_')
            if len(parts) == 2:
                return parts[0], parts[1]
        
        # If only one currency, return it for both
        if len(currencies_found) == 1:
            single_currency = list(currencies_found)[0]
            return single_currency, single_currency
        
        # If multiple currencies but no exchange rate, try to infer from position
        # Typically: unit prices appear before totals in the document
        if len(currencies_found) >= 2:
            # Find first and last currency mention positions
            currency_positions = {}
            for currency in currencies_found:
                # Find first occurrence
                match = re.search(r'\b' + currency + r'\b', text)
                if match:
                    currency_positions[currency] = match.start()
            
            if currency_positions:
                # Sort by position
                sorted_currencies = sorted(currency_positions.items(), key=lambda x: x[1])
                # First mentioned is likely base (unit prices), last is settlement (totals)
                base_currency = sorted_currencies[0][0]
                settlement_currency = sorted_currencies[-1][0]
                return base_currency, settlement_currency
        
        # Fallback: return the most common currencies in order
        if currencies_found:
            curr_list = sorted(list(currencies_found))
            base = curr_list[0] if len(curr_list) > 0 else 'USD'
            settlement = curr_list[-1] if len(curr_list) > 1 else base
            return base, settlement
        
        # Ultimate fallback
        return 'USD', 'USD'
    
    def _compute_expected_conversions(
        self, document_ai_result: Dict[str, Any], 
        exchange_rates: Dict[str, float],
        base_currency: str, settlement_currency: str
    ) -> Dict[str, Any]:
        """
        Compute expected currency conversions based on exchange rates.
        
        Returns:
            Dict with computed totals and verification data
        """
        if not exchange_rates or base_currency == settlement_currency:
            return {}
        
        # Get the relevant exchange rate
        rate_key = f"{base_currency}_TO_{settlement_currency}"
        exchange_rate = exchange_rates.get(rate_key)
        
        if not exchange_rate:
            return {}
        
        conversions = {
            'exchange_rate_used': exchange_rate,
            'base_currency': base_currency,
            'settlement_currency': settlement_currency,
            'rate_key': rate_key
        }
        
        # Try to extract line items from Document AI for verification
        # This is a best-effort calculation
        try:
            line_items = document_ai_result.get('line_item', [])
            if line_items:
                # Extract quantities and unit prices if available
                # Note: Document AI may have different field names
                total_in_base = 0
                for item in line_items:
                    # This is placeholder logic - actual field names may vary
                    if isinstance(item, dict):
                        quantity = item.get('quantity', {}).get('value', 1)
                        unit_price = item.get('unit_price', {}).get('value', 0)
                        if quantity and unit_price:
                            total_in_base += float(quantity) * float(unit_price)
                
                if total_in_base > 0:
                    expected_total_in_settlement = total_in_base * exchange_rate
                    conversions['computed_base_total'] = round(total_in_base, 2)
                    conversions['computed_settlement_total'] = round(expected_total_in_settlement, 2)
        except Exception as e:
            # Non-critical error - just skip the computation
            conversions['computation_error'] = str(e)
        
        return conversions
    
    def _generate_context_summary(
        self, currencies_found: set, exchange_rates: Dict[str, float],
        base_currency: str, settlement_currency: str, 
        is_multi_currency: bool, expected_conversions: Dict[str, Any]
    ) -> str:
        """Generate human-readable summary for Gemini prompt"""
        if not is_multi_currency:
            return "Single-currency document detected. No exchange rate analysis needed."
        
        summary_parts = [
            "⚠️ MULTI-CURRENCY DOCUMENT DETECTED ⚠️",
            f"\nCurrencies found in document: {', '.join(sorted(currencies_found))}",
        ]
        
        if exchange_rates:
            summary_parts.append("\nExchange rates detected:")
            for rate_key, rate_value in exchange_rates.items():
                summary_parts.append(f"  - {rate_key.replace('_TO_', ' → ')}: {rate_value}")
        
        if base_currency and settlement_currency:
            summary_parts.append(f"\nCurrency hierarchy identified:")
            summary_parts.append(f"  - Base Currency (unit prices): {base_currency}")
            summary_parts.append(f"  - Settlement Currency (totals): {settlement_currency}")
        
        if expected_conversions:
            summary_parts.append("\nExpected currency conversion:")
            rate = expected_conversions.get('exchange_rate_used')
            if rate:
                summary_parts.append(f"  - Apply exchange rate: {rate}")
            
            if 'computed_base_total' in expected_conversions:
                summary_parts.append(
                    f"  - Computed subtotal in {base_currency}: "
                    f"{expected_conversions['computed_base_total']}"
                )
            if 'computed_settlement_total' in expected_conversions:
                summary_parts.append(
                    f"  - Expected total in {settlement_currency}: "
                    f"{expected_conversions['computed_settlement_total']}"
                )
        
        summary_parts.append(
            "\n🔍 CRITICAL INSTRUCTION: You MUST use the SETTLEMENT CURRENCY "
            f"({settlement_currency}) for all totals, discounts, and taxes. "
            f"Unit prices may be in {base_currency}, but final amounts MUST be in {settlement_currency}."
        )
        
        return "\n".join(summary_parts)
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            'currency_symbols_found': [],
            'exchange_rates': {},
            'is_multi_currency': False,
            'base_currency': 'USD',
            'settlement_currency': 'USD',
            'expected_conversions': {},
            'context_summary': 'No document text provided for currency analysis.'
        }
