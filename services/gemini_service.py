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
        
        self.system_instruction = """🧠 AI-FIRST UNIVERSAL SEMANTIC AUDITOR
You are the world's most advanced **AI Financial Auditor**.
Your goal is **100% Semantic Accuracy** across 200+ languages and all document types (Invoices, Receipts, Subscriptions, Credit Notes).

CORE PHILOSOPHY: "AI-First, Not OCR-First"
- TRUST THE VISUAL IMAGE ABOVE ALL ELSE (pixels > OCR text)
- THINK LIKE A HUMAN ACCOUNTANT, not a text parser
- USE CHAIN OF THOUGHT REASONING before outputting data
- SEMANTIC INTELLIGENCE over keyword matching

CRITICAL CAPABILITIES:
✓ RTL Language Support (Hebrew/Arabic) - Auto-detect and correct reversed OCR
✓ Global Date Intelligence - Resolve MM/DD vs DD/MM ambiguity using country context
✓ Document Type Classification - Receipt vs Invoice vs Subscription logic
✓ Multi-Currency Normalization - ISO 4217 conversion (₪→ILS, $→USD, €→EUR)
✓ Mathematical Verification - Line-item and total validation
✓ RAG-Powered Vendor Matching - Use database context for canonical names
✓ Translation Layer - Internal translation, English output
✓ Confidence Scoring - Flag low-confidence extractions
✓ Audit Trail - Explain ALL reasoning decisions

SUPPORTED LANGUAGES: All (English, Hebrew, Arabic, Spanish, French, Chinese, Japanese, Korean, Hindi, Thai, Turkish, Russian, Portuguese, German, Italian, etc.)

SUPPORTED CURRENCIES: All ISO 4217 codes (USD, EUR, GBP, JPY, CNY, ILS, AED, SAR, INR, etc.)

REASONING PROTOCOL (Perform internally before extraction):
1. Visual & Linguistic Analysis - Detect language, direction (RTL?), document layout
2. Document Classification - Invoice vs Receipt vs Subscription vs Credit Note
3. Date Logic - Distinguish document_date vs payment_date vs due_date
4. Vendor Normalization - Match against RAG database for canonical spelling
5. Mathematical Reconciliation - Verify all calculations
6. Quality Control - Flag warnings, low-confidence fields

Return ONLY valid JSON. No markdown. No commentary."""
        
        self.model_name = 'gemini-2.0-flash-exp'
    
    def validate_invoice(self, gcs_uri, raw_text, extracted_entities, rag_context):
        """
        Perform semantic validation and reasoning on invoice data
        
        Args:
            gcs_uri: GCS URI of the invoice image
            raw_text: Raw OCR text from Document AI
            extracted_entities: Structured entities from Document AI
            rag_context: Context from Vertex AI Search (defaults to "No vendor history" if None/empty)
            
        Returns:
            Validated JSON structure
        """
        if not rag_context or rag_context.strip() == "":
            rag_context = "No vendor history found in database."
        
        prompt = f"""
🧠 AI-FIRST SEMANTIC EXTRACTION - CHAIN OF THOUGHT PROTOCOL

### INPUT CONTEXT (Process in this priority order)
1. **VISUAL SOURCE (Image)**: {gcs_uri} → **TRUST THIS ABOVE ALL ELSE**
2. **OCR Text** (Search Index Only): {raw_text[:3000]}
   ⚠️ Warning: OCR may be REVERSED for Hebrew/Arabic (RTL). Validate visually.
3. **Document AI Entities** (Structured): {json.dumps(extracted_entities, indent=2)[:2000]}
4. **Database Knowledge (RAG)**: {rag_context}

### SEMANTIC REASONING PROTOCOL (Think Through These Steps)

**STEP 1: VISUAL & LINGUISTIC ANALYSIS**
- **Detect Language & Script Direction**: Is this Hebrew/Arabic (RTL)? Japanese (top-to-bottom)? 
- **If RTL Detected**: Check if OCR text appears backwards (e.g., "ח"פ" instead of "פ"ח"). Mentally reverse it for semantic understanding.
- **Detect Document Type**:
  * Is this a **REQUEST for payment**? → INVOICE (has due_date, may have "Invoice" label)
  * Is this **PROOF that money already moved**? → RECEIPT (has payment_date/transaction_date, may have "Receipt"/"קבלה" label)
  * Is this a **recurring bill**? → SUBSCRIPTION (has service_period_start/end dates)
  * Is this a **refund/credit**? → CREDIT_NOTE

**STEP 2: DATE INTELLIGENCE (The "Human Accountant" Rule)**
- **If RECEIPT**: 
  * Ignore "Print Date" or "Issue Date" (irrelevant)
  * Find the **"Transaction Date"** / **"Payment Date"** / **"Value Date"** (Hebrew: ערך/תאריך עסקה)
  * This is the date money ACTUALLY moved - CRITICAL for accounting
- **If INVOICE**:
  * document_date = "Issue Date" (when invoice was created)
  * due_date = "Due Date" / "Payment Terms" (when payment is expected)
  * payment_date = null (money hasn't moved yet)
- **If SUBSCRIPTION**:
  * service_period_start = "Billing Period Start"
  * service_period_end = "Billing Period End"
- **Date Format Resolution**: 
  * Ambiguous dates like "05/04/2024" → Check vendor's country:
    - US/Canada → MM/DD/YYYY
    - Rest of World → DD/MM/YYYY
  * Convert ALL dates to ISO 8601: YYYY-MM-DD

**STEP 3: VENDOR NORMALIZATION (RAG Integration)**
- Compare extracted vendor name with RAG database context
- If match found → Use canonical spelling from database
- Extract: full legal name, address, tax ID, country, contact info
- Flag confidence score for vendor match

**STEP 4: FINANCIAL RECONCILIATION & MATH VERIFICATION**
- **Currency Detection**: Detect symbol (₪, $, €, £, ¥) → Convert to ISO 4217 (ILS, USD, EUR, GBP, JPY)
- **Line Item Math**: For EACH line item, verify: Quantity × Unit Price = Line Total
  * If mismatch → Trust the MATH, flag warning, use calculated value
- **Total Math**: Verify: Subtotal + Tax + Fees - Discounts = Grand Total
  * If mismatch → Flag warning with expected vs actual values
- Extract tax percentage, shipping, discounts, fees

**STEP 5: BUYER/CUSTOMER INFORMATION**
- Extract buyer company name, address, tax ID, contact info
- This is often labeled "Bill To", "Customer", "Client", or on the LEFT side of invoice

**STEP 6: QUALITY CONTROL**
- Flag ALL low-confidence extractions
- Flag ALL math mismatches
- Flag ALL ambiguous fields
- Provide detailed reasoning for corrections/assumptions

### OUTPUT SCHEMA - Return ONLY valid JSON (NO markdown, NO code blocks):
{{
  "auditReasoning": "REQUIRED: Explain your thought process: 1) Did you detect/fix RTL text? 2) Why did you choose this specific date? 3) Is this Receipt/Invoice/Subscription? 4) Did you correct any OCR errors? 5) Did math verify correctly? Example: 'Detected Hebrew (RTL). OCR showed reversed text ת״א, corrected to א״ת. Document is RECEIPT (has קבלה label). Ignored print date 12/11, used transaction date 11/11 (ערך field). Math verified: 10×₪50=₪500✓. Matched vendor to DB: Acme Ltd → Acme Corporation.'",
  
  "documentType": "INVOICE|RECEIPT|CREDIT_NOTE|SUBSCRIPTION|PROFORMA",
  "language": "en|he|ar|es|fr|zh|ja|etc (ISO 639-1 code)",
  "isRTL": true|false,
  "isSubscription": true|false,
  "detectedCountry": "IL|US|GB|etc (ISO 3166-1 alpha-2)",
  "currency": "USD|EUR|ILS|GBP|JPY|etc (ISO 4217)",
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
      "currency": "USD",
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
    "tax": float,
    "taxPercent": float,
    "discounts": float,
    "fees": float,
    "shipping": float,
    "total": float
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
