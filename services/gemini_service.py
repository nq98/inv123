import os
import json
from google import genai
from google.genai import types
from openai import OpenAI
from config import config


class OpenRouterResponse:
    """Simple response wrapper for OpenRouter API responses"""
    def __init__(self, text):
        self.text = text


class GeminiService:
    """
    Service for semantic validation and reasoning using Gemini 3 Pro (via OpenRouter) as PRIMARY.
    
    MODEL HIERARCHY (in order of priority):
    1. OpenRouter Gemini 3 Pro Preview - PRIMARY (1M context, best reasoning)
    2. AI Studio gemini-2.5-flash - FALLBACK (if OpenRouter fails)
    3. Replit AI Integrations - FINAL FALLBACK (if rate limited)
    """
    
    def __init__(self):
        # Fallback client: User's AI Studio API key (used if OpenRouter fails)
        api_key = config.GOOGLE_GEMINI_API_KEY or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=api_key)
        
        # PRIMARY: OpenRouter Gemini 3 Pro (flagship model with 1M context)
        self.openrouter_client = None
        self.openrouter_model = "google/gemini-3-pro-preview"
        openrouter_api_key = os.getenv('OPENROUTERA')
        
        if openrouter_api_key:
            try:
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                    default_headers={
                        "HTTP-Referer": "https://replit.com",
                        "X-Title": "Enterprise Invoice Extraction System"
                    }
                )
                print("✅ OpenRouter client initialized with Gemini 3 Pro")
            except Exception as e:
                print(f"⚠️ OpenRouter client initialization failed: {e}")
        
        # Fallback client: Replit AI Integrations (billed to Replit credits)
        self.fallback_client = None
        replit_api_key = os.getenv('AI_INTEGRATIONS_GEMINI_API_KEY')
        replit_base_url = os.getenv('AI_INTEGRATIONS_GEMINI_BASE_URL')
        
        if replit_api_key and replit_base_url:
            try:
                self.fallback_client = genai.Client(
                    api_key=replit_api_key,
                    http_options={
                        'api_version': '',
                        'base_url': replit_base_url
                    }
                )
            except Exception as e:
                pass
        
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
        
        # Fallback model for AI Studio (when OpenRouter unavailable)
        self.model_name = 'gemini-2.5-flash'
    
    def _is_rate_limit_error(self, exception):
        """Check if the exception is a rate limit or quota violation error"""
        error_msg = str(exception)
        return (
            "429" in error_msg 
            or "RATE_LIMIT_EXCEEDED" in error_msg
            or "quota" in error_msg.lower() 
            or "rate limit" in error_msg.lower()
            or (hasattr(exception, 'status') and exception.status == 429)
        )
    
    def _call_openrouter(self, prompt, system_instruction=None, response_format="json"):
        """
        Call OpenRouter API with Gemini 3 Pro
        
        Args:
            prompt: The user prompt
            system_instruction: System instruction (optional)
            response_format: Response format - "json" or "text"
            
        Returns:
            Response text from Gemini 3 Pro
        """
        if not self.openrouter_client:
            raise ValueError("OpenRouter client not initialized")
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        try:
            kwargs = {
                "model": self.openrouter_model,
                "messages": messages,
                "temperature": 0.1
            }
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}
            
            response = self.openrouter_client.chat.completions.create(**kwargs)
            
            result_text = response.choices[0].message.content
            print(f"✅ OpenRouter Gemini 3 Pro response received")
            return result_text
            
        except Exception as e:
            print(f"❌ OpenRouter API error: {e}")
            raise e
    
    def _generate_content_with_fallback(self, model, contents, config, use_openrouter_first=True):
        """
        Generate content with tiered fallback chain:
        1. OpenRouter Gemini 3 Pro Preview (PRIMARY - 1M context, best reasoning)
        2. AI Studio (gemini-2.5-flash - fast fallback)
        3. Replit AI Integrations (final fallback on rate limit)
        
        Args:
            model: Model name for fallback (e.g., 'gemini-2.5-flash')
            contents: Prompt contents
            config: GenerateContentConfig
            use_openrouter_first: Try OpenRouter Gemini 3 Pro first (default: True)
            
        Returns:
            Response from Gemini 3 Pro (primary) or fallback model
        """
        # Try OpenRouter Gemini 3 Pro first (PRIMARY)
        if use_openrouter_first and self.openrouter_client:
            try:
                print("🚀 Using OpenRouter Gemini 3 Pro...")
                response_text = self._call_openrouter(
                    prompt=contents,
                    system_instruction=config.system_instruction if hasattr(config, 'system_instruction') else None,
                    response_format="json" if config.response_mime_type == "application/json" else "text"
                )
                return OpenRouterResponse(response_text)
            except Exception as e:
                print(f"⚠️ OpenRouter failed: {e}, falling back to AI Studio...")
        
        # Try primary client (AI Studio)
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            # Check if it's a rate limit error
            if self._is_rate_limit_error(e):
                print(f"⚠️ AI Studio rate limit hit: {e}")
                
                # Try OpenRouter if not already tried
                if not use_openrouter_first and self.openrouter_client:
                    print("🔄 Falling back to OpenRouter Gemini 3 Pro...")
                    try:
                        response_text = self._call_openrouter(
                            prompt=contents,
                            system_instruction=config.system_instruction if hasattr(config, 'system_instruction') else None,
                            response_format="json" if config.response_mime_type == "application/json" else "text"
                        )
                        return OpenRouterResponse(response_text)
                    except Exception as openrouter_error:
                        print(f"⚠️ OpenRouter also failed: {openrouter_error}")
                
                # Try Replit AI Integrations fallback
                if self.fallback_client:
                    print("🔄 Falling back to Replit AI Integrations...")
                    try:
                        # Map model name to Replit AI Integrations equivalent
                        fallback_model = model
                        if 'flash' in model.lower():
                            fallback_model = 'gemini-2.5-flash'
                        elif 'pro' in model.lower():
                            fallback_model = 'gemini-2.5-pro'
                        
                        response = self.fallback_client.models.generate_content(
                            model=fallback_model,
                            contents=contents,
                            config=config
                        )
                        print(f"✅ Fallback successful using {fallback_model}")
                        return response
                    except Exception as fallback_error:
                        print(f"❌ Fallback also failed: {fallback_error}")
                        raise fallback_error
                else:
                    print("❌ No fallback configured, rate limit cannot be bypassed")
                    raise e
            else:
                # Not a rate limit error, re-raise
                raise e
    
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
    "name": "The Brand Name / Logo Name (visible on invoice header)",
    "legal_name": "CRITICAL: The Legal Entity Name found in Payment Instructions / Bank Beneficiary / Remit-To field. This is WHO RECEIVES THE MONEY. If different from Brand Name, PRIORITIZE THIS for matching.",
    "address": "Complete address",
    "country": "Country name",
    "email": "email@domain.com or null",
    "phone": "phone number or null",
    "taxId": "VAT/Tax ID or null",
    "registrationNumber": "Business reg number or null",
    "website": "url or null"
  }},
  
  "vendor_identity_analysis": {{
    "brand_name": "Name/logo visible on invoice header (e.g., 'Fully Booked', 'Go To Health!')",
    "legal_beneficiary": "Legal entity receiving payment from bank/remit-to instructions (e.g., 'Artem Andreevitch Revva', 'GoToHealth Media, LLC')",
    "is_third_party_payment": true|false,
    "reasoning": "REQUIRED: Explain if brand_name differs from legal_beneficiary and why. Example: 'Invoice header shows Fully Booked but payment instructions say Payable to Artem Andreevitch Revva, indicating Artem is a freelancer using Fully Booked as a brand name.'"
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
                # Use fallback-enabled method (automatic rate limit protection)
                response = self._generate_content_with_fallback(
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
    
    def gatekeeper_email_filter(self, sender_email, email_subject, email_body_snippet, attachment_filename):
        """
        Elite Gatekeeper AI Filter using Gemini 1.5 Flash
        Fast semantic analysis to determine if email contains financial document
        
        Args:
            sender_email: Email address of sender
            email_subject: Email subject line
            email_body_snippet: Preview snippet of email body
            attachment_filename: Name of attachment file
        
        Returns:
            dict: {
                "is_financial_document": bool,
                "document_category": str,  # "INVOICE", "RECEIPT", "STATEMENT", "JUNK", "OTHER"
                "confidence": float,
                "reasoning": str
            }
        """
        prompt = f"""
You are the **Chief Financial Mailroom Guard**.
Your ONLY job is to decide if an incoming email contains a **Financial Document** that needs processing.

### INPUT EMAIL DATA
- **Sender:** {sender_email}
- **Subject:** {email_subject}
- **Body Snippet:** {email_body_snippet}
- **Attachment Name:** {attachment_filename}

### 🧠 DECISION LOGIC (SEMANTIC ANALYSIS)

**1. POSITIVE SIGNALS (Keep These)**
- **Explicit Demands:** "Please find attached invoice", "Payment due", "Here is your bill"
- **Proof of Payment:** "Your receipt from Uber", "Payment successful", "Thank you for your purchase"
- **Passive Financials:** "Monthly Statement", "Subscription Renewal", "Credit Note", "Zikui", "Hashbonit"
- **Ambiguous Files with Context:** If filename is "scan001.pdf" BUT body says "Attached the invoice", **KEEP IT**

**2. NEGATIVE SIGNALS (Discard These)**
- **Marketing:** "Special offer", "News from...", "Join our webinar"
- **Logistics (Non-Financial):** "Your package has shipped" (unless includes receipt)
- **Technical:** "Password reset", "Security alert", "Webhook notification", "System Event"
- **Human Chatter:** "See you at lunch", "Meeting notes" (unless expensing receipt)

**3. THE "SAFEGUARD" RULE (Never Miss Money)**
- If unsure (e.g., Order Confirmation that *might* be invoice), output **TRUE**
- Better to process a junk file than throw away a $10,000 invoice

### OUTPUT FORMAT (Strict JSON)
{{
    "is_financial_document": boolean,
    "document_category": "INVOICE | RECEIPT | STATEMENT | JUNK | OTHER",
    "confidence": 0.0-1.0,
    "reasoning": "Explain why. E.g. 'Subject says Payment Processed and attachment is PDF, definitely a receipt.'"
}}
"""
        
        try:
            # PRIMARY: OpenRouter Gemini 3 Pro, FALLBACK: gemini-2.5-flash
            response = self._generate_content_with_fallback(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json'
                )
            )
            
            response_text = response.text or "{}"
            result = json.loads(response_text)
            
            # Ensure all required fields present
            return {
                "is_financial_document": result.get("is_financial_document", False),
                "document_category": result.get("document_category", "OTHER"),
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", "No reasoning provided")
            }
            
        except Exception as e:
            print(f"Gatekeeper AI error: {e}")
            # Fail-safe: If AI errors, let it through (better false positive than false negative)
            return {
                "is_financial_document": True,
                "document_category": "OTHER",
                "confidence": 0.5,
                "reasoning": f"AI filter error: {str(e)} - Defaulting to KEEP for safety"
            }
    
    def batch_gatekeeper_filter(self, emails_batch):
        """
        🚀 BATCH GATEKEEPER: Process 20-30 emails in ONE API call
        
        This reduces latency by 95% compared to sequential processing.
        Uses Gemini Flash for speed.
        
        Args:
            emails_batch: List of dicts, each with:
                - email_id: Unique identifier
                - sender: Sender email
                - subject: Email subject
                - snippet: Body preview
                - attachment: Attachment filename (or "none")
        
        Returns:
            dict: {email_id: {is_financial_document, document_category, confidence, reasoning}}
        """
        if not emails_batch:
            return {}
        
        batch_size = len(emails_batch)
        print(f"🚀 BATCH GATEKEEPER: Processing {batch_size} emails in ONE API call...")
        
        emails_list_text = ""
        for i, email in enumerate(emails_batch, 1):
            emails_list_text += f"""
EMAIL #{i} (ID: {email.get('email_id', f'email_{i}')})
- Sender: {email.get('sender', 'unknown')}
- Subject: {email.get('subject', '(no subject)')}
- Snippet: {email.get('snippet', '')[:200]}
- Attachment: {email.get('attachment', 'none')}
---"""
        
        prompt = f"""
You are the **Chief Financial Mailroom Guard** with BATCH processing capability.
Analyze ALL {batch_size} emails below and classify each one.

### EMAIL BATCH TO ANALYZE
{emails_list_text}

### 🧠 DECISION LOGIC (Apply to EACH email)

**POSITIVE SIGNALS (KEEP)**
- Explicit demands: "Please find attached invoice", "Payment due", "Here is your bill"
- Proof of payment: "Your receipt from...", "Payment successful", "Thank you for your purchase"
- Passive financials: "Monthly Statement", "Subscription Renewal", "Credit Note"
- Ambiguous files with context: If body mentions "invoice" or "receipt", KEEP IT

**NEGATIVE SIGNALS (DISCARD)**
- Marketing: "Special offer", "News from...", "Join our webinar"
- Logistics: "Your package shipped" (unless includes receipt)
- Technical: "Password reset", "Security alert", "Webhook notification"
- Human chatter: "See you at lunch", "Meeting notes"

**SAFEGUARD RULE**: When unsure, output TRUE (better false positive than missing a $10k invoice)

### OUTPUT FORMAT (Strict JSON object with email_id keys)
Return a JSON object where keys are email IDs:
{{
    "email_1": {{
        "is_financial_document": true,
        "document_category": "INVOICE",
        "confidence": 0.95,
        "reasoning": "Subject contains 'invoice' and has PDF attachment"
    }},
    "email_2": {{
        "is_financial_document": false,
        "document_category": "JUNK",
        "confidence": 0.90,
        "reasoning": "Marketing newsletter about product updates"
    }}
}}

IMPORTANT: Use the EXACT email IDs provided above (e.g., "email_1", "email_2", etc.)
"""
        
        try:
            import time
            start_time = time.time()
            
            # PRIMARY: OpenRouter Gemini 3 Pro, FALLBACK: gemini-2.5-flash
            response = self._generate_content_with_fallback(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json'
                )
            )
            
            elapsed = time.time() - start_time
            print(f"⚡ Batch gatekeeper (Gemini 3) completed in {elapsed:.2f}s ({batch_size} emails, {elapsed/batch_size:.3f}s avg)")
            
            response_text = response.text or "{}"
            results = json.loads(response_text)
            
            processed_results = {}
            for i, email in enumerate(emails_batch, 1):
                email_id = email.get('email_id', f'email_{i}')
                
                email_key = None
                for key in [email_id, f'email_{i}', str(i)]:
                    if key in results:
                        email_key = key
                        break
                
                if email_key and email_key in results:
                    result = results[email_key]
                    processed_results[email_id] = {
                        "is_financial_document": result.get("is_financial_document", True),
                        "document_category": result.get("document_category", "OTHER"),
                        "confidence": result.get("confidence", 0.5),
                        "reasoning": result.get("reasoning", "Batch processed")
                    }
                else:
                    processed_results[email_id] = {
                        "is_financial_document": True,
                        "document_category": "OTHER",
                        "confidence": 0.5,
                        "reasoning": "Missing from batch response - defaulting to KEEP"
                    }
            
            kept = sum(1 for r in processed_results.values() if r["is_financial_document"])
            discarded = batch_size - kept
            print(f"📊 Batch results: {kept} KEEP, {discarded} DISCARD")
            
            return processed_results
            
        except Exception as e:
            print(f"❌ Batch gatekeeper error: {e}")
            fallback_results = {}
            for i, email in enumerate(emails_batch, 1):
                email_id = email.get('email_id', f'email_{i}')
                fallback_results[email_id] = {
                    "is_financial_document": True,
                    "document_category": "OTHER",
                    "confidence": 0.5,
                    "reasoning": f"Batch error: {str(e)} - Defaulting to KEEP"
                }
            return fallback_results
    
    def batch_text_extraction(self, emails_batch):
        """
        🚀 BATCH TEXT EXTRACTION: Process 10+ text-based emails in ONE API call
        
        This is for emails WITHOUT PDF attachments (like Replit, Stripe receipts in body).
        PDFs still go through Document AI + Vertex Search + Gemini full pipeline.
        
        Args:
            emails_batch: List of dicts, each with:
                - email_id: Unique identifier
                - subject: Email subject
                - sender: Sender email
                - body: Email body HTML/text (truncated to 2000 chars)
                - date: Email date
        
        Returns:
            dict: {email_id: {extracted_data or None if not a receipt}}
        """
        if not emails_batch:
            return {}
        
        batch_size = len(emails_batch)
        print(f"🚀 BATCH TEXT EXTRACTION: Processing {batch_size} text-based emails in ONE API call...")
        
        emails_list_text = ""
        for i, email in enumerate(emails_batch, 1):
            body_preview = email.get('body', '')[:2000]
            emails_list_text += f"""
--- EMAIL_ID: {email.get('email_id', f'email_{i}')} ---
Subject: {email.get('subject', '(no subject)')}
Sender: {email.get('sender', 'unknown')}
Date: {email.get('date', 'unknown')}
Body:
{body_preview}
"""
        
        prompt = f"""You are an expert financial data extractor processing {batch_size} emails.

### 🧠 CHAIN OF THOUGHT EXTRACTION PROCESS (Apply to EACH email)

For each email, follow these steps:

**Step 1: Entity Classification**
- PROCESSOR: Payment platforms (Stripe, PayPal, Replit) - they process payments but aren't the vendor
- VENDOR: The company whose product/service was purchased

**Step 2: Data Extraction**
- Invoice/Receipt number (from subject OR body)
- Date (YYYY-MM-DD format)  
- Vendor name (the actual seller, NOT the payment processor)
- Currency and amounts (subtotal, tax, total)
- **LINE ITEMS (CRITICAL)**: Extract FULL details for each item:
  - description: Full description including any reference numbers
  - quantity: Number of units (default 1 if not specified)
  - unitPrice: Price per unit (same as lineSubtotal for single items)
  - lineSubtotal: Total for this line item
  - category: Type of product/service (e.g., "Software Subscription", "API Credits")
  
  **Where to find line items**:
  - "Summary" sections: "Payment for invoice XXX - Service Name : $XX.XX"
  - Itemized lists with prices
  - Service descriptions followed by amounts
  - **UNIVERSAL FALLBACK**: If only total is visible, create ONE line item with:
    * description: "Service/Product" or extracted service name
    * quantity: 1
    * unitPrice: total amount
    * lineSubtotal: total amount

**Step 3: Mathematical Verification**
- Tax = Total - Subtotal (verify this matches)
- If amounts seem wrong, recalculate

### EMAIL BATCH TO PROCESS
{emails_list_text}

### OUTPUT FORMAT (Strict JSON object)
Return a JSON object where keys are the exact email IDs provided:
{{
    "text_email_1": {{
        "success": true,
        "vendor": {{
            "name": "Replit",
            "email": "support@replit.com"
        }},
        "invoiceNumber": "1600-0026",
        "invoiceDate": "2025-11-25",
        "currency": "USD",
        "totals": {{
            "subtotal": 50.06,
            "tax": 0.00,
            "total": 50.06
        }},
        "lineItems": [
            {{
                "description": "Replit Core Usage - Payment for invoice BWFLLB-00039",
                "quantity": 1,
                "unitPrice": 50.06,
                "lineSubtotal": 50.06,
                "category": "Software Subscription"
            }}
        ],
        "confidenceScore": "High",
        "missingCriticalData": false,
        "reasoning": "Replit receipt - extracted from body: Amount paid $50.06, Payment for invoice BWFLLB-00039"
    }},
    "text_email_2": {{
        "success": false,
        "confidenceScore": "Low",
        "missingCriticalData": true,
        "reasoning": "Not a receipt/invoice - just a notification"
    }}
}}

### 🚫 ANTI-HALLUCINATION RULES (CRITICAL - ZERO TOLERANCE FOR JUNK):

1. **NEVER GENERATE FAKE INVOICE NUMBERS**:
   - Invoice numbers MUST be VERBATIM from the email text (subject or body)
   - If no invoice number is visible, set invoiceNumber to "N/A"
   - NEVER generate UUIDs, random numbers, or made-up strings
   - Examples of REAL invoice numbers: "INV-2025-001", "1600-0026", "BWFLLB-00039"
   - WRONG: "8523144a-7d7e-44bd-bbf8-d36109e40a5d" (this is a UUID - NEVER DO THIS)

2. **AMOUNT MUST BE > 0** - Set success=false if:
   - Total amount is $0.00 or negative
   - No clear monetary amount found in email
   - Amount cannot be determined

3. **PAYMENT PROCESSOR NOTIFICATIONS** - Set success=false for:
   - Stripe: "Your payout is on the way", "Payment received", "Funds transferred"
   - PayPal: "You sent/received a payment" (unless it's a PayPal INVOICE)
   - Wise/TransferWise: "Your transfer is complete"
   - These are NOTIFICATIONS about payments, NOT invoices to pay

4. **NON-INVOICE DETECTION** - Set success=false for:
   - Deployment notifications ("Successfully deployed to...")
   - System alerts and status updates
   - Marketing emails without financial transactions
   - Password resets, welcome emails, newsletters
   - Shipping notifications without prices
   - "Thank you for your payment" confirmations (already paid, not an invoice)
   - Bank transaction alerts

5. **VENDOR NAME RULES**:
   - NEVER use "Unknown" as vendor name - set success=false instead
   - Payment processors (Stripe, PayPal) are NOT vendors unless they're billing YOU
   - The vendor is the company whose product/service was purchased

### CONFIDENCE SCORING (CRITICAL):
- **High**: Vendor name, total amount, AND invoice number all clearly extracted FROM THE EMAIL
- **Medium**: 2 out of 3 fields extracted, some inference required
- **Low**: Major fields missing, ambiguous data, or confusing format
- **missingCriticalData**: true if vendor OR total is missing/zero

### LINE ITEM EXTRACTION RULES:
1. **ALWAYS include quantity** - Default to 1 if not specified
2. **ALWAYS include unitPrice** - Same as lineSubtotal if single item  
3. **ALWAYS include lineSubtotal** - The actual amount for this line item
4. **Look for line item details in**:
   - "Summary" section: "Payment for invoice XXX - Service Name : $XX.XX"
   - Individual line items with prices
   - Subscription descriptions with amounts
5. **If no itemized breakdown**, create ONE line item with:
   - description: General description from context (e.g., "Service subscription")
   - quantity: 1
   - unitPrice: same as total
   - lineSubtotal: same as total

### CRITICAL SUCCESS RULES:
1. **success: true** if you can identify ANY of these:
   - Invoice/Receipt number (from subject OR body)
   - Vendor name (from sender email domain or body)
   - This IS a financial document (receipt, invoice, bill, statement)

2. **success: false** ONLY if:
   - It's clearly NOT a financial document (shipping notification, password reset, marketing email)
   
3. **EXTRACT WHAT YOU CAN**: 
   - If price is missing, set totals.total to 0 and add a note in reasoning
   - If date is missing, use "unknown" 
   - If only invoice number is in subject, that's STILL success!

4. **Replit/Stripe/SaaS receipts**: These are ALWAYS success=true if they mention "receipt" or have invoice numbers in subject

IMPORTANT: 
- Use EXACT email IDs from the emails above (e.g., "text_email_1", "text_email_2")
- Vendor should be the actual seller, NOT payment processor (Stripe, PayPal, etc.)
"""
        
        try:
            import time
            start_time = time.time()
            
            response = self._generate_content_with_fallback(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json'
                ),
                use_openrouter_first=True
            )
            
            elapsed = time.time() - start_time
            print(f"⚡ Batch text extraction completed in {elapsed:.2f}s ({batch_size} emails, {elapsed/batch_size:.3f}s avg)")
            
            response_text = response.text or "{}"
            results = json.loads(response_text)
            
            processed_results = {}
            success_count = 0
            
            for i, email in enumerate(emails_batch, 1):
                email_id = email.get('email_id', f'email_{i}')
                
                email_key = None
                for key in [email_id, f'email_{i}', str(i)]:
                    if key in results:
                        email_key = key
                        break
                
                if email_key and email_key in results:
                    result = results[email_key]
                    processed_results[email_id] = result
                    if result.get('success', False):
                        success_count += 1
                else:
                    processed_results[email_id] = {
                        "success": False,
                        "reasoning": "Missing from batch response"
                    }
            
            print(f"📊 Batch extraction results: {success_count}/{batch_size} successful")
            return processed_results
            
        except Exception as e:
            print(f"❌ Batch text extraction error: {e}")
            fallback_results = {}
            for i, email in enumerate(emails_batch, 1):
                email_id = email.get('email_id', f'email_{i}')
                fallback_results[email_id] = {
                    "success": False,
                    "reasoning": f"Batch error: {str(e)}"
                }
            return fallback_results
    
    def generate_text(self, prompt, temperature=0.1, response_mime_type='application/json', use_gemini3=False):
        """
        Generate text using Gemini with automatic fallback
        
        Args:
            prompt: Text prompt to send to Gemini
            temperature: Sampling temperature (0.0-1.0)
            response_mime_type: MIME type for response (default: application/json)
            use_gemini3: Use OpenRouter Gemini 3 Pro first (default: False)
            
        Returns:
            String response from Gemini
        """
        response = self._generate_content_with_fallback(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type=response_mime_type
            ),
            use_openrouter_first=use_gemini3
        )
        
        return response.text or "{}"
    
    def generate_with_gemini3(self, prompt, system_instruction=None, response_format="json"):
        """
        Generate text using OpenRouter Gemini 3 Pro directly (1M context, best reasoning)
        
        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            response_format: "json" or "text"
            
        Returns:
            String response from Gemini 3 Pro
        """
        if not self.openrouter_client:
            print("⚠️ OpenRouter not available, falling back to standard generation")
            return self.generate_text(prompt, response_mime_type="application/json" if response_format == "json" else "text/plain")
        
        try:
            return self._call_openrouter(
                prompt=prompt,
                system_instruction=system_instruction,
                response_format=response_format
            )
        except Exception as e:
            print(f"⚠️ Gemini 3 Pro failed: {e}, falling back to standard generation")
            return self.generate_text(prompt, response_mime_type="application/json" if response_format == "json" else "text/plain")
    
    def extract_invoice_from_text(self, email_html_or_text, email_subject="", sender_email=""):
        """
        OPTIMIZATION 1: Text-First Short-Circuit
        Extract invoice data directly from email HTML/text WITHOUT PDF conversion.
        This is MUCH faster than HTML → PDF → Document AI OCR pipeline.
        
        Args:
            email_html_or_text: Raw HTML or plain text content from email body
            email_subject: Email subject for additional context
            sender_email: Sender email for vendor identification
        
        Returns:
            dict: Validated invoice data structure OR None if extraction incomplete
        """
        import re
        from html.parser import HTMLParser
        
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.in_script = False
                self.in_style = False
                
            def handle_starttag(self, tag, attrs):
                if tag == 'script':
                    self.in_script = True
                elif tag == 'style':
                    self.in_style = True
                elif tag in ('br', 'p', 'div', 'tr', 'li'):
                    self.text_parts.append('\n')
                elif tag == 'td':
                    self.text_parts.append(' | ')
                    
            def handle_endtag(self, tag):
                if tag == 'script':
                    self.in_script = False
                elif tag == 'style':
                    self.in_style = False
                    
            def handle_data(self, data):
                if not self.in_script and not self.in_style:
                    text = data.strip()
                    if text:
                        self.text_parts.append(text)
            
            def get_text(self):
                return ' '.join(self.text_parts)
        
        try:
            if '<html' in email_html_or_text.lower() or '<body' in email_html_or_text.lower():
                parser = TextExtractor()
                parser.feed(email_html_or_text)
                clean_text = parser.get_text()
            else:
                clean_text = email_html_or_text
            
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            clean_text = clean_text[:8000]
            
            prompt = f"""You are a **Semantic Financial AI** with deep reasoning capabilities. THINK before extracting.

### EMAIL CONTEXT
- **Subject:** {email_subject}
- **Sender:** {sender_email}

### EMAIL BODY TEXT
{clean_text}

---
## SEMANTIC REASONING EXTRACTION

You must use your intelligence to understand this document semantically. Do NOT use pattern matching or regex logic.

### STEP 1: ENTITY UNDERSTANDING
Use semantic reasoning to understand the roles of each entity:

**Key Question:** Who is the INTERMEDIARY vs who is the SERVICE PROVIDER?
- The company sending the email is often an intermediary (payment platform, notification service)
- The entity receiving money for goods/services is the actual vendor
- Look at the business context: Who provided value? Who is being paid FOR something?
- Parse any JSON/structured data in the email body to find beneficiary/payee information

**Buyer Understanding:**
- Who is the payer? Look for contextual clues in greetings, salutations, "to:" fields
- Use semantic understanding of the document flow

### STEP 2: TEXT INTELLIGENCE
Apply your language understanding to clean the text:
- Identify and correct obvious OCR/concatenation errors using linguistic knowledge
- Recognize when words are incorrectly joined or split
- Fix spacing issues based on what makes grammatical sense
- Preserve intentional formatting (company names, abbreviations)

Report what you intelligently corrected.

### STEP 3: MATHEMATICAL REASONING
Apply arithmetic logic to verify/calculate amounts:
- If you have any two of (subtotal, tax, fees, total), calculate the missing values
- Look for fee fields and incorporate them into your calculations
- Verify that the numbers make mathematical sense
- Use the formula: Total = Subtotal + Tax + Fees (solve for any missing variable)

### STEP 4: CONFIDENCE CALIBRATION
Honestly assess your extraction quality:
- High confidence: All data clearly visible and verified
- Medium confidence: Some inference required but reasonable
- Low confidence: Significant ambiguity or missing data
- Your confidence should reflect ACTUAL data quality, not a default value

### OUTPUT

Return ONLY valid JSON (NO markdown, NO code blocks):
{{
  "chainOfThought": {{
    "processorIdentified": "The intermediary/platform sending this notification",
    "vendorIdentified": "The entity receiving payment for goods/services",
    "buyerIdentified": "The entity making the payment",
    "ocrFixesApplied": ["List each text correction you made and why"],
    "mathVerification": "Show your arithmetic: how you calculated/verified the amounts"
  }},
  "vendor": {{
    "name": "The actual service provider (NOT the notification sender)",
    "email": "vendor email or null",
    "address": "Full address with city, country",
    "taxId": "VAT/Tax ID or null"
  }},
  "buyer": {{
    "name": "The payer entity",
    "address": "Buyer address if available"
  }},
  "invoiceNumber": "Invoice/receipt number",
  "documentType": "INVOICE|RECEIPT",
  "documentDate": "YYYY-MM-DD",
  "dueDate": "YYYY-MM-DD or null",
  "paymentDate": "YYYY-MM-DD or null",
  "currency": "ISO 4217 currency code",
  "totals": {{
    "subtotal": float (derive mathematically if not explicit),
    "tax": float (calculate if possible),
    "fees": float (platform fees, wire fees, service charges),
    "taxPercent": float or null,
    "total": float (REQUIRED)
  }},
  "lineItems": [
    {{
      "description": "Semantically cleaned description",
      "quantity": float (default 1 if not specified),
      "unitPrice": float (same as lineSubtotal for single items),
      "lineSubtotal": float (REQUIRED - the line item total)
    }}
  ],
  "extractionConfidence": 0.0-1.0 (calibrated to actual quality),
  "reasoning": "Your semantic reasoning process",
  "warnings": ["Any remaining uncertainties"]
}}

IMPORTANT: If you cannot find a vendor name OR a total amount, return {{"extraction_incomplete": true, "reason": "Missing vendor/total"}}
"""
            
            # PRIMARY: OpenRouter Gemini 3 Pro, FALLBACK: gemini-2.5-flash
            response = self._generate_content_with_fallback(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json'
                )
            )
            
            result_text = response.text or "{}"
            result = json.loads(result_text)
            
            if result.get('extraction_incomplete'):
                print(f"⚠️ Text-first extraction incomplete: {result.get('reason', 'Unknown')}")
                return None
            
            vendor = result.get('vendor', {}).get('name', 'Unknown')
            total = result.get('totals', {}).get('total', 0)
            
            if not vendor or vendor == 'Unknown' or not total or total <= 0:
                print(f"⚠️ Text-first extraction incomplete: vendor={vendor}, total={total}")
                return None
            
            chain_of_thought = result.get('chainOfThought', {})
            processor = chain_of_thought.get('processorIdentified', '')
            ocr_fixes = chain_of_thought.get('ocrFixesApplied', [])
            math_verification = chain_of_thought.get('mathVerification', '')
            
            if ocr_fixes:
                print(f"🔧 OCR FIXES APPLIED: {ocr_fixes}")
            if math_verification:
                print(f"📊 MATH VERIFIED: {math_verification}")
            if processor:
                print(f"🏦 PROCESSOR: {processor} → VENDOR: {vendor}")
            
            validated_data = {
                'vendor': result.get('vendor', {}),
                'buyer': result.get('buyer', {}),
                'invoiceNumber': result.get('invoiceNumber'),
                'documentType': result.get('documentType', 'RECEIPT'),
                'documentDate': result.get('documentDate'),
                'issueDate': result.get('documentDate'),
                'dueDate': result.get('dueDate'),
                'paymentDate': result.get('paymentDate'),
                'currency': result.get('currency', 'USD'),
                'totals': result.get('totals', {}),
                'lineItems': result.get('lineItems', []),
                'extractionConfidence': result.get('extractionConfidence', 0.7),
                'auditReasoning': result.get('reasoning', 'Extracted from email text'),
                'chainOfThought': chain_of_thought,
                'warnings': result.get('warnings', []),
                'source': 'text_first_extraction'
            }
            
            confidence = result.get('extractionConfidence', 0.7)
            buyer_name = result.get('buyer', {}).get('name', 'Unknown')
            fees = result.get('totals', {}).get('fees', 0)
            tax = result.get('totals', {}).get('tax', 0)
            
            print(f"✅ SEMANTIC EXTRACTION: {vendor} | {result.get('currency', 'USD')} {total}")
            if buyer_name and buyer_name != 'Unknown':
                print(f"   👤 Buyer: {buyer_name}")
            if fees > 0:
                print(f"   💰 Fees calculated: {fees}")
            if tax > 0:
                print(f"   📋 Tax: {tax}")
            print(f"   🎯 Confidence: {confidence*100:.0f}%")
            
            return validated_data
            
        except Exception as e:
            print(f"❌ Text-first extraction error: {e}")
            return None
    
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
    
    def classify_link_type(self, url, email_context=""):
        """
        AI-semantic link classifier - determines how to process a URL
        
        Args:
            url: The URL to classify
            email_context: Optional email subject/body for context
        
        Returns:
            tuple: (link_type, confidence, reasoning)
                link_type: 'direct_pdf', 'web_receipt', or 'auth_required'
                confidence: float 0-1
                reasoning: str explanation
        """
        
        prompt = f"""Analyze this URL and classify what type of link it is for invoice/receipt extraction.

URL: {url}
Email Context: {email_context}

Classify as ONE of:
1. **direct_pdf**: Direct PDF download link (ends in .pdf, has /pdf in path, direct file download)
2. **web_receipt**: Web-based receipt page that renders in browser (public receipt, pre-authenticated link with token)
3. **auth_required**: ONLY use if URL truly requires login (no token, short path, generic dashboard)
4. **not_invoice**: NOT a receipt - just an image, icon, logo, tracking pixel, email decoration

⚠️ CRITICAL - STRIPE/PAYMENT PROVIDER PUBLIC RECEIPTS:
Many payment providers send PUBLIC receipt URLs that LOOK like dashboard URLs but are PUBLIC!

**PUBLIC RECEIPT INDICATORS (classify as web_receipt or direct_pdf):**
- URLs with LONG TOKENS/HASHES (40+ chars) in the path = PUBLIC ACCESS via token!
- Example: dashboard.stripe.com/receipts/payment/CAcQARoXChVhY2N... (long token = PUBLIC)
- Example: pay.stripe.com/invoice/acct_xxx/live_YWNjdF8x... (long token = PUBLIC)
- URLs from: pay.stripe.com, receipt.*, invoice.*, checkout.*
- ANY URL with /receipts/ or /payment/ + long alphanumeric path = web_receipt (PUBLIC!)
- If URL ends with /pdf or has ?format=pdf → direct_pdf

**TRULY AUTH_REQUIRED (only these):**
- Short dashboard URLs with NO long tokens: dashboard.stripe.com/ (just domain)
- URLs that go to /login, /signin, /account/settings
- URLs with NO receipt/invoice/payment path AND no long tokens

FILTER OUT (not_invoice):
- Image URLs: .png, .jpg, .gif, /icons/, /images/, /assets/
- S3/CDN decoration: stripe-images.s3.amazonaws.com with /icons/
- Tracking pixels, logos, email graphics

DECISION PRIORITY (check in this order):
1. Is it an image/icon/decoration? → not_invoice
2. Does it end in .pdf or have /pdf? → direct_pdf
3. Does path have /receipts/ or /payment/ or /invoice/ WITH 30+ char token? → web_receipt (PUBLIC!)
4. Is it a short generic URL with NO token? → auth_required

Return ONLY valid JSON:
{{
  "linkType": "direct_pdf" | "web_receipt" | "auth_required" | "not_invoice",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation - MUST mention if long token detected = public access"
}}"""

        try:
            config = {
                'response_mime_type': 'application/json'
            }
            
            response = self._generate_content_with_fallback(
                self.model_name,
                prompt,
                config
            )
            
            result = json.loads(response.text)
            
            return (
                result.get('linkType', 'auth_required'),
                result.get('confidence', 0.0),
                result.get('reasoning', 'No reasoning provided')
            )
            
        except Exception as e:
            print(f"Link classification error: {e}")
            # Safe fallback: assume auth required if classification fails
            return ('auth_required', 0.0, f'Classification failed: {str(e)}')
