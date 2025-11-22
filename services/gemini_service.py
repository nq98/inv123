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
        
        self.system_instruction = """⭐ GEMINI INVOICE INTELLIGENCE ENGINE
Multilingual · Multicurrency · Multidocument · Semantic Reasoning · Ultra-High Accuracy

You are Payouts.com's Global Invoice Intelligence Engine (GIIE).
Your job is to understand ANY financial document from ANY country, ANY language, ANY layout, and return PERFECT structured data with FULL semantic reasoning.

You ALWAYS perform:
- Document classification
- Semantic extraction
- Mathematical validation
- Field normalization
- Currency normalization
- Vendor entity normalization
- Tax interpretation
- Language translation (internally)
- Cross-field consistency checks
- Confidence scoring
- Metadata extraction
- RAG integration when context is provided

You NEVER hallucinate. You NEVER guess without labeling it as low confidence.
You ALWAYS explain your reasoning. You ALWAYS follow the JSON schema exactly.
You ALWAYS use semantic meaning — never rely only on keyword matching.
You ALWAYS work for 200+ countries, 40+ languages, 200+ currencies.

SUPPORTED DOCUMENT TYPES: Invoice, Tax Invoice, Credit Note, Debit Note, Proforma Invoice, Receipt, Payment Request, Remittance Advice, Tax Form, Purchase Order, Statements, Supplier Bills.

MULTILINGUAL: ALL languages (English, Spanish, French, Hebrew, Arabic, Chinese, Japanese, Korean, Hindi, Thai, Turkish, Russian, Portuguese, German, Italian, etc.)

MULTICURRENCY: ALL currencies (USD, EUR, GBP, JPY, CNY, CAD, AUD, ZAR, CHF, SEK, DKK, AED, SAR, ILS, TRY, INR, MXN, etc.)

EXTRACTION RULES:
- Validate line-item math: (Qty × Unit Price) = Line Total
- Validate: Subtotal + Tax = Total
- Flag all mismatches with reasoning
- Normalize vendor entity names using RAG context when provided
- Infer missing values logically
- Detect language automatically, normalize output to English
- Convert dates to ISO 8601 (YYYY-MM-DD)
- Convert currency to ISO 4217 codes
- Provide confidence scores
- Return ONLY valid JSON, no markdown, no commentary."""
        
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
INVOICE INTELLIGENCE ENGINE - FULL EXTRACTION

INPUT DATA:
1. OCR Text from Document AI: {raw_text[:3000]}

2. Structured Entities from Document AI: {json.dumps(extracted_entities, indent=2)[:2000]}

3. Internal Database Context (RAG): {rag_context}

YOUR TASKS:
1. Extract ALL semantic data from the document
2. Compare "Vendor Name" with RAG context - use database spelling/ID if it's a match
3. MATH VALIDATION: Verify (Quantity × Unit Price) = Line Total for EACH line item
4. MATH VALIDATION: Verify Subtotal + Tax + Fees = Grand Total
5. NORMALIZE dates to ISO 8601 (YYYY-MM-DD)
6. NORMALIZE currency to ISO 4217 (USD, EUR, ILS, etc.)
7. DETECT language and document type
8. PROVIDE confidence scores
9. EXPLAIN your reasoning

OUTPUT SCHEMA - Return ONLY valid JSON:
{{
  "documentType": "Invoice|Receipt|Credit Note|Proforma|etc",
  "language": "en|he|es|fr|etc",
  "currency": "USD|EUR|ILS|etc",
  "originalCurrency": "same or different if converted",
  "exchangeRate": null,
  "invoiceNumber": "string",
  "issueDate": "YYYY-MM-DD",
  "dueDate": "YYYY-MM-DD or null",
  "paymentTerms": "Net 30|Due on receipt|etc",

  "vendor": {{
    "name": "Full legal name",
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

  "purchaseOrderNumbers": ["PO123", "PO456"],
  
  "paymentDetails": {{
    "iban": "IBAN or null",
    "swift": "SWIFT/BIC or null",
    "bankName": "Bank name or null",
    "accountNumber": "Account number or null",
    "paymentInstructions": "Instructions or null"
  }},

  "lineItems": [
    {{
      "description": "Item description",
      "quantity": 0,
      "unitPrice": 0,
      "currency": "USD",
      "taxPercent": 0,
      "taxAmount": 0,
      "lineSubtotal": 0,
      "category": "semantic category",
      "productCode": "SKU or null",
      "mathVerified": true
    }}
  ],

  "totals": {{
    "subtotal": 0,
    "tax": 0,
    "taxPercent": 0,
    "discounts": 0,
    "fees": 0,
    "shipping": 0,
    "total": 0
  }},

  "vendorMatch": {{
    "normalizedName": "Canonical vendor name from RAG or semantic normalization",
    "alternateNames": ["Spelling variant 1", "Abbreviation"],
    "confidence": 0.95,
    "matchedDbId": "vendor_id_from_rag or null"
  }},

  "classificationConfidence": 0.99,
  "extractionConfidence": 0.95,

  "reasoning": "Detailed explanation: I extracted vendor from header. Math verified: 10×$50=$500 ✓. Used RAG to correct 'Acme Corp' → 'Acme Corporation Inc.' Tax calculated at 17% (Israel VAT). Date format detected as DD/MM/YYYY based on address.",
  
  "warnings": ["Tax calculation mismatch: expected 500, found 510", "Duplicate invoice number detected"]
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
            "documentType": "Unknown",
            "language": "unknown",
            "currency": "USD",
            "originalCurrency": "USD",
            "exchangeRate": None,
            "invoiceNumber": None,
            "issueDate": None,
            "dueDate": None,
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
