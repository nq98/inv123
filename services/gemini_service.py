import os
import json
from google import genai
from google.genai import types
from config import config

class GeminiService:
    """Service for semantic validation and reasoning using Gemini 1.5 Pro"""
    
    def __init__(self):
        api_key = config.GOOGLE_GEMINI_API_KEY or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=api_key)
        
        self.system_instruction = """You are the **Omni-Global Financial AI**.
You possess complete knowledge of every accounting standard, currency, and document format on Earth.

CORE PHILOSOPHY: "AI-First, Not OCR-First"
- TRUST THE VISUAL IMAGE ABOVE ALL ELSE (pixels > OCR text)
- THINK LIKE A HUMAN ACCOUNTANT, not a text parser
- USE CHAIN OF THOUGHT REASONING before outputting data
- SEMANTIC INTELLIGENCE over keyword matching

CAPABILITIES:
✓ Universal Currency Knowledge - All ISO 4217 codes with regional symbols
✓ Global Country Intelligence - ISO 3166 with country-specific date/tax logic
✓ RTL Language Support - Hebrew/Arabic auto-detect and OCR correction
✓ Multi-Currency Forensics - Cross-currency conversion with exchange rate detection
✓ Document Type Classification - 10 category taxonomy (Tax Invoice, Receipt, Credit Note, Subscription, etc.)
✓ Mathematical Verification - Line-item and total validation across currencies
✓ RAG-Powered Learning - Use historical invoice patterns for accuracy
✓ Confidence Scoring - Flag low-confidence extractions with detailed reasoning

Return ONLY valid JSON. No markdown. No commentary."""
        
        self.model_name = 'gemini-2.0-flash-exp'
    
    def validate_invoice(self, gcs_uri, raw_text, extracted_entities, rag_context, currency_context=None):
        """
        Perform semantic validation and reasoning on invoice data
        
        Args:
            gcs_uri: GCS URI of the invoice image
            raw_text: Raw OCR text from Document AI
            extracted_entities: Structured entities from Document AI
            rag_context: Context from Vertex AI Search (defaults to "No vendor history" if None/empty)
            currency_context: Multi-currency analysis context from MultiCurrencyDetector (optional)
            
        Returns:
            Validated JSON structure
        """
        if not rag_context or rag_context.strip() == "":
            rag_context = "No vendor history found in database."
        
        # Format currency context for the prompt
        currency_analysis = ""
        if currency_context:
            currency_analysis = f"\n\n{currency_context.get('context_summary', 'No multi-currency context available')}"
        
        prompt = f"""
### 1. YOUR INTERNAL KNOWLEDGE BASE

**A. AUTHORIZED CURRENCIES (Support ALL ISO 4217):**
- North America: USD ($), CAD (C$), MXN ($)
- Europe: EUR (€), GBP (£), CHF (Fr), SEK (kr), NOK (kr), DKK (kr), RUB (₽), PLN (zł), CZK (Kč), HUF (Ft), TRY (₺)
- Middle East: ILS (₪), SAR (﷼), AED (د.إ), QAR (﷼), KWD (د.ك), EGP (E£), JOD (JD)
- Asia Pacific: CNY (¥), JPY (¥), INR (₹), AUD ($), NZD ($), SGD ($), HKD ($), KRW (₩), THB (฿), IDR (Rp), MYR (RM), VND (₫), PHP (₱)
- South America: BRL (R$), ARS ($), CLP ($), COP ($), PEN (S/)
- Africa: ZAR (R), NGN (₦), KES (KSh), EGP (E£)
- Crypto/Digital: BTC, ETH, USDC, USDT

**B. AUTHORIZED COUNTRIES (Support ALL ISO 3166 with specific logic):**
- USA (US): MM/DD/YYYY dates, Sales Tax regional
- UK (GB): DD/MM/YYYY, VAT 20%
- Israel (IL): DD/MM/YYYY, VAT 17-18%, RTL Hebrew
- Germany (DE): DD.MM.YYYY, MwSt 19%, comma decimal (1.000,00)
- France (FR): DD/MM/YYYY, TVA 20%
- Japan (JP): YYYY-MM-DD, Consumption Tax 10%
- Brazil (BR): DD/MM/YYYY, NFS-e, CNPJ IDs
- China (CN): YYYY-MM-DD, Fapiao System
- Apply standard logic for all other 190+ countries

**C. AUTHORIZED DOCUMENT TYPES:**
1. Tax Invoice: Standard payment demand with tax breakdown
2. Simplified Invoice / Receipt: Point-of-Sale slip (Starbucks, Taxi, Fuel)
3. Credit Note: Negative balance / Refund
4. Debit Note: Additional charge
5. Pro-Forma Invoice: Quote (not for payment)
6. Utility Bill: Electricity, Water, Gas, Internet
7. Subscription/SaaS: Recurring software charge (AWS, Google, Zoom)
8. Bill of Lading / Shipping Manifest: Customs/Logistics
9. Timesheet / Service Log: Hourly work record
10. Bank Statement: List of transactions

### 2. PRE-ANALYSIS CONTEXT (From Multi-Currency Detector Layer 1.5)
{currency_analysis if currency_analysis else "No multi-currency pre-analysis available."}

### 3. HISTORICAL KNOWLEDGE (From Vertex AI Search RAG)
{rag_context}

### 4. INPUT DATA (Process with priority: IMAGE > RAG > OCR)
**VISUAL SOURCE (Image)**: {gcs_uri} → **TRUST THIS ABOVE ALL ELSE**
**OCR Text** (Search Index Only): {raw_text[:3000]}
⚠️ Warning: OCR may be REVERSED for Hebrew/Arabic (RTL). Validate visually.
**Document AI Entities** (Structured): {json.dumps(extracted_entities, indent=2)[:2000]}

### 5. EXECUTION PROTOCOL (MANDATORY STEPS)

**STEP 1: GLOBAL RECOGNITION**
- Look at IMAGE first
- Identify Language (Hebrew, Japanese, German, etc.) using visual text
- Identify Country based on address/phone patterns (+972→IL, +1→US/CA, +44→GB)
- Identify Document Type from list C above (Tax Invoice, Receipt, Subscription, etc.)

**STEP 2: CURRENCY & MATH FORENSICS (Use Pre-Analysis Context)**
- Single Currency: If "Total $500", output primary_currency_code: "USD", grand_total: 500.00
- Multi-Currency Detection:
  - Check if line items in one currency (e.g., USD) and total in another (e.g., ILS)
  - Use detected exchange rate from pre-analysis context
  - MATH CHECK: (Qty × UnitPrice × FX_Rate) == Total
  - If no rate found but math fails, CALCULATE implied rate
  - Example: 29 × $8 USD × 3.27 = 758.64 ILS
- Verify ALL calculations: Subtotal + Tax - Discounts = Grand Total

**STEP 3: SEMANTIC DATA REPAIR**
- RTL Languages (Hebrew/Arabic): Trust IMAGE, fix reversed OCR text
- Dates: Normalize to YYYY-MM-DD using country-specific logic from list B
- Document Type Logic:
  - Receipt → Set due_date to null, find payment_date (transaction date)
  - Invoice → Set payment_date to null, find due_date
  - Subscription → Extract period_start and period_end
- Vendor Matching: Use RAG context to normalize vendor name to canonical form

### 6. OUTPUT SCHEMA (Enhanced with Global Audit Metadata)

Return ONLY valid JSON (NO markdown, NO code blocks):
{{
  "global_audit_metadata": {{
    "detected_country": "IL|US|GB|DE|FR|JP|BR|CN|etc (ISO 3166-1 alpha-2)",
    "detected_language": "he|en|ar|de|fr|ja|pt|zh|etc (ISO 639-1)",
    "document_category": "Tax Invoice|Simplified Invoice / Receipt|Credit Note|Debit Note|Pro-Forma Invoice|Utility Bill|Subscription/SaaS|Bill of Lading / Shipping Manifest|Timesheet / Service Log|Bank Statement",
    "is_multi_currency": true|false,
    "confidence_level": 0.0-1.0
  }},
  
  "vendor_details": {{
    "name_normalized": "Canonical vendor name (from RAG or semantically normalized)",
    "name_native": "Original vendor name in native language/script",
    "registration_id": "VAT/Tax ID/CNPJ/BIN/HP number or null",
    "address_full": "Complete address string or null",
    "matched_db_id": "vendor_id from RAG database or null"
  }},
  
  "critical_dates": {{
    "issue_date": "YYYY-MM-DD (when document was issued)",
    "payment_date": "YYYY-MM-DD (for Receipts: actual transaction date) or null",
    "due_date": "YYYY-MM-DD (for Invoices: payment deadline) or null",
    "period_start": "YYYY-MM-DD (for Subscriptions/Utilities) or null",
    "period_end": "YYYY-MM-DD (for Subscriptions/Utilities) or null"
  }},
  
  "financial_data": {{
    "primary_currency_code": "ILS|USD|EUR|GBP|JPY|etc (ISO 4217 - final settlement currency)",
    "line_item_currency_code": "USD|EUR|ILS|etc (ISO 4217 - unit price currency, may differ from primary)",
    "exchange_rate_applied": float or null,
    "subtotal": float,
    "tax_total": float,
    "discount_total": float,
    "grand_total": float,
    "tax_breakdown": [
      {{
        "tax_type": "VAT|Sales Tax|GST|etc",
        "tax_rate": float,
        "tax_amount": float
      }}
    ]
  }},
  
  "ai_auditor_notes": "REQUIRED: Comprehensive explanation. Example: 'Found Invoice in Hebrew (RTL). Detected Israel from +972 phone. Document category: Tax Invoice. Multi-currency: USD line items → ILS total. Exchange rate 3.27 detected. Math verified: 29×$8×3.27=758.64 ILS. Applied 50% discount: 379.32 ILS. Tax 18%: 68.28 ILS. Grand total: 447.60 ILS ✓. Matched vendor DreamTeam to database.'",
  
  "auditReasoning": "LEGACY FIELD - Same as ai_auditor_notes for backward compatibility",
  "documentType": "INVOICE|RECEIPT|CREDIT_NOTE|SUBSCRIPTION|PROFORMA|UTILITY_BILL|DEBIT_NOTE|TIMESHEET",
  "language": "en|he|ar|es|fr|zh|ja|etc (ISO 639-1)",
  "isRTL": true|false,
  "isSubscription": true|false,
  "detectedCountry": "IL|US|GB|etc (ISO 3166-1 alpha-2) - LEGACY, use global_audit_metadata.detected_country",
  "currency": "USD|EUR|ILS|etc (ISO 4217) - LEGACY, use financial_data.primary_currency_code",
  "originalCurrency": "same or different if converted",
  "exchangeRate": null|float,
  
  "invoiceNumber": "string",
  "documentDate": "YYYY-MM-DD (Physical date printed on document)",
  "paymentDate": "YYYY-MM-DD (CRITICAL for receipts: actual transaction date) or null",
  "dueDate": "YYYY-MM-DD (for invoices) or null",
  "servicePeriodStart": "YYYY-MM-DD (for subscriptions) or null",
  "servicePeriodEnd": "YYYY-MM-DD (for subscriptions) or null",
  "paymentTerms": "Net 30|Due on receipt|etc or null",

  "vendor": {{
    "name": "Full legal name (corrected using RAG context if available)",
    "address": "Complete address",
    "country": "Country name",
    "email": "email@domain.com or null",
    "phone": "phone number or null",
    "taxId": "VAT/Tax ID or null",
    "registrationNumber": "Business reg number or null",
    "website": "url or null"
  }},

  "buyer": {{
    "name": "Buyer company name or null",
    "address": "Buyer address or null",
    "country": "Country or null",
    "email": "email or null",
    "phone": "phone or null",
    "taxId": "tax id or null",
    "registrationNumber": "reg number or null"
  }},

  "purchaseOrderNumbers": ["PO123", "PO456"] or [],
  
  "paymentDetails": {{
    "iban": "IBAN or null",
    "swift": "SWIFT/BIC or null",
    "bankName": "Bank name or null",
    "accountNumber": "Account number or null",
    "paymentInstructions": "Instructions or null"
  }},

  "lineItems": [
    {{
      "description": "Item description (translate to English if foreign language)",
      "quantity": float,
      "unitPrice": float,
      "unitPriceCurrency": "USD (ISO 4217 code for unit price currency)",
      "currency": "USD (DEPRECATED - use unitPriceCurrency)",
      "lineTotal": float,
      "lineTotalCurrency": "ILS (ISO 4217 code for line total currency, may differ from unitPriceCurrency)",
      "exchangeRateApplied": float or null,
      "taxPercent": float,
      "taxAmount": float,
      "lineSubtotal": float,
      "category": "semantic category (e.g., 'Software Subscription', 'Consulting Services')",
      "productCode": "SKU or null",
      "mathVerified": true|false
    }}
  ],

  "totals": {{
    "subtotal": float,
    "subtotalCurrency": "ILS (ISO 4217)",
    "tax": float,
    "taxCurrency": "ILS (ISO 4217)",
    "taxPercent": float,
    "discounts": float,
    "discountCurrency": "ILS (ISO 4217)",
    "fees": float,
    "feesCurrency": "ILS (ISO 4217)",
    "shipping": float,
    "shippingCurrency": "ILS (ISO 4217)",
    "total": float,
    "totalCurrency": "ILS (ISO 4217)"
  }},

  "multiCurrency": {{
    "isMultiCurrency": true|false,
    "baseCurrency": "USD (ISO 4217 - currency of unit prices)",
    "settlementCurrency": "ILS (ISO 4217 - currency of final totals)",
    "exchangeRate": 3.27 or null,
    "exchangeRateSource": "Document states: (1USD = 3.27ILS) or null",
    "mathVerification": {{
      "lineItemCalculation": "29 × $8.00 USD = $232.00 USD",
      "currencyConversion": "$232.00 × 3.27 = 758.64 ILS",
      "afterDiscount": "758.64 - 379.32 = 379.32 ILS",
      "afterTax": "379.32 + 68.28 = 447.60 ILS",
      "verified": true|false
    }}
  }},

  "vendorMatch": {{
    "normalizedName": "Canonical vendor name from RAG database or semantically normalized",
    "alternateNames": ["Spelling variant 1", "Abbreviation", "Previous names"],
    "confidence": float (0.0-1.0),
    "matchedDbId": "vendor_id_from_rag or null",
    "ragMatchReasoning": "Explain how you matched this vendor to the database"
  }},

  "classificationConfidence": float (0.0-1.0),
  "extractionConfidence": float (0.0-1.0),

  "reasoning": "LEGACY FIELD - Use auditReasoning instead. Brief explanation of extraction decisions.",
  
  "warnings": ["List of issues: math mismatches, low confidence fields, OCR corrections, ambiguous dates, etc."]
}}
"""
        
        max_retries = 2
        response = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                
                if not response or not response.text:
                    if attempt < max_retries - 1:
                        continue
                    return self._create_error_response("Empty response from Gemini", ["Gemini returned empty response"])
                
                result_text = response.text.strip()
                
                if result_text.startswith('```json'):
                    result_text = result_text[7:]
                if result_text.startswith('```'):
                    result_text = result_text[3:]
                if result_text.endswith('```'):
                    result_text = result_text[:-3]
                
                result_text = result_text.strip()
                
                validated_data = json.loads(result_text)
                
                # Ensure minimum required fields exist
                if 'vendor' not in validated_data:
                    validated_data['vendor'] = {"name": "Unknown", "address": None, "country": None}
                if 'warnings' not in validated_data:
                    validated_data['warnings'] = []
                if 'documentType' not in validated_data:
                    validated_data['documentType'] = "Invoice"
                if 'extractionConfidence' not in validated_data:
                    validated_data['extractionConfidence'] = 0.5
                if 'auditReasoning' not in validated_data:
                    validated_data['auditReasoning'] = validated_data.get('reasoning', 'No reasoning provided')
                
                # Backward compatibility: map new field names to old ones
                if 'documentDate' in validated_data and 'issueDate' not in validated_data:
                    validated_data['issueDate'] = validated_data['documentDate']
                if 'isRTL' not in validated_data:
                    validated_data['isRTL'] = False
                if 'isSubscription' not in validated_data:
                    validated_data['isSubscription'] = False
                if 'detectedCountry' not in validated_data:
                    validated_data['detectedCountry'] = None
                
                # NEW: Ensure global_audit_metadata exists with defaults
                if 'global_audit_metadata' not in validated_data:
                    validated_data['global_audit_metadata'] = {
                        'detected_country': validated_data.get('detectedCountry'),
                        'detected_language': validated_data.get('language', 'en'),
                        'document_category': validated_data.get('documentType', 'Invoice'),
                        'is_multi_currency': validated_data.get('multiCurrency', {}).get('isMultiCurrency', False),
                        'confidence_level': validated_data.get('extractionConfidence', 0.5)
                    }
                
                # NEW: Ensure vendor_details exists
                if 'vendor_details' not in validated_data:
                    vendor = validated_data.get('vendor', {})
                    validated_data['vendor_details'] = {
                        'name_normalized': validated_data.get('vendorMatch', {}).get('normalizedName', vendor.get('name', 'Unknown')),
                        'name_native': vendor.get('name', 'Unknown'),
                        'registration_id': vendor.get('taxId') or vendor.get('registrationNumber'),
                        'address_full': vendor.get('address'),
                        'matched_db_id': validated_data.get('vendorMatch', {}).get('matchedDbId')
                    }
                
                # NEW: Ensure critical_dates exists
                if 'critical_dates' not in validated_data:
                    validated_data['critical_dates'] = {
                        'issue_date': validated_data.get('documentDate') or validated_data.get('issueDate'),
                        'payment_date': validated_data.get('paymentDate'),
                        'due_date': validated_data.get('dueDate'),
                        'period_start': validated_data.get('servicePeriodStart'),
                        'period_end': validated_data.get('servicePeriodEnd')
                    }
                
                # NEW: Ensure financial_data exists
                if 'financial_data' not in validated_data:
                    totals = validated_data.get('totals', {})
                    multi_currency = validated_data.get('multiCurrency', {})
                    validated_data['financial_data'] = {
                        'primary_currency_code': multi_currency.get('settlementCurrency') or validated_data.get('currency', 'USD'),
                        'line_item_currency_code': multi_currency.get('baseCurrency') or validated_data.get('currency', 'USD'),
                        'exchange_rate_applied': multi_currency.get('exchangeRate') or validated_data.get('exchangeRate'),
                        'subtotal': totals.get('subtotal', 0),
                        'tax_total': totals.get('tax', 0),
                        'discount_total': totals.get('discounts', 0),
                        'grand_total': totals.get('total', 0),
                        'tax_breakdown': []
                    }
                
                # NEW: Ensure ai_auditor_notes exists
                if 'ai_auditor_notes' not in validated_data:
                    validated_data['ai_auditor_notes'] = validated_data.get('auditReasoning', validated_data.get('reasoning', 'No audit notes provided'))
                
                return validated_data
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                
                response_text = response.text if response and hasattr(response, 'text') else "No response"
                print(f"Raw response: {response_text}")
                return self._create_error_response(
                    "Failed to parse Gemini response after retries", 
                    ["JSON parsing failed"],
                    response_text[:500] if response_text else "No response"
                )
            except Exception as e:
                print(f"Gemini validation error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                
                return self._create_error_response(str(e), [f"Gemini error: {str(e)}"])
    
    def _create_error_response(self, error_message, warnings, raw_response=None):
        """Create a standardized error response matching the comprehensive schema"""
        response = {
            "error": error_message,
            "global_audit_metadata": {
                "detected_country": None,
                "detected_language": "unknown",
                "document_category": "Unknown",
                "is_multi_currency": False,
                "confidence_level": 0.0
            },
            "vendor_details": {
                "name_normalized": "Unknown",
                "name_native": "Unknown",
                "registration_id": None,
                "address_full": None,
                "matched_db_id": None
            },
            "critical_dates": {
                "issue_date": None,
                "payment_date": None,
                "due_date": None,
                "period_start": None,
                "period_end": None
            },
            "financial_data": {
                "primary_currency_code": "USD",
                "line_item_currency_code": "USD",
                "exchange_rate_applied": None,
                "subtotal": 0,
                "tax_total": 0,
                "discount_total": 0,
                "grand_total": 0,
                "tax_breakdown": []
            },
            "ai_auditor_notes": f"Error during extraction: {error_message}",
            "auditReasoning": f"Error during extraction: {error_message}",
            "documentType": "Unknown",
            "language": "unknown",
            "isRTL": False,
            "isSubscription": False,
            "detectedCountry": None,
            "currency": "USD",
            "originalCurrency": "USD",
            "exchangeRate": None,
            "invoiceNumber": None,
            "documentDate": None,
            "issueDate": None,
            "paymentDate": None,
            "dueDate": None,
            "servicePeriodStart": None,
            "servicePeriodEnd": None,
            "paymentTerms": None,
            "vendor": {
                "name": "Unknown",
                "address": None,
                "country": None,
                "email": None,
                "phone": None,
                "taxId": None,
                "registrationNumber": None,
                "website": None
            },
            "buyer": {
                "name": None,
                "address": None,
                "country": None,
                "email": None,
                "phone": None,
                "taxId": None,
                "registrationNumber": None
            },
            "purchaseOrderNumbers": [],
            "paymentDetails": {
                "iban": None,
                "swift": None,
                "bankName": None,
                "accountNumber": None,
                "paymentInstructions": None
            },
            "lineItems": [],
            "totals": {
                "subtotal": 0,
                "tax": 0,
                "taxPercent": 0,
                "discounts": 0,
                "fees": 0,
                "shipping": 0,
                "total": 0
            },
            "vendorMatch": {
                "normalizedName": "Unknown",
                "alternateNames": [],
                "confidence": 0,
                "matchedDbId": None
            },
            "classificationConfidence": 0,
            "extractionConfidence": 0,
            "reasoning": f"Error during extraction: {error_message}",
            "warnings": warnings
        }
        
        if raw_response:
            response['raw_response'] = raw_response
        
        return response
