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
        
        self.system_instruction = """You are a financial auditor API. Your goal is 100% data accuracy.

Rule 1 (Context Priority): If the OCR text says 'Gooogle' but the RAG Context says the vendor is 'Google LLC', output 'Google LLC'.

Rule 2 (Math Validation): You MUST calculate line items. If the invoice says 5 * 10 = 40, output math_verified: false and flag it. Do not silently fix it; flag the discrepancy.

Rule 3 (Global Dates): If the invoice is from the US, read dates as MM/DD/YYYY. If from Europe/Israel, read as DD/MM/YYYY. Use the detected address to decide the locale.

Rule 4: Return ONLY valid JSON. No markdown, no code blocks, just pure JSON."""
        
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
You are an expert Invoice Auditor.

INPUT DATA:
1. OCR Text from Document AI: {raw_text[:2000]}

2. Structured Entities from Document AI: {json.dumps(extracted_entities, indent=2)}

3. Internal Database Context (RAG): {rag_context}

YOUR TASKS:
1. Merge the Document AI entities to create a PERFECT JSON.
2. Compare the "Vendor Name" on the invoice with the "Internal Database Context". Use the Database spelling/ID if it's a match.
3. MATH CHECK: Verify (Quantity * Unit Price) == Line Total for each line item. If the math is wrong, set math_verified: false and add a flag.
4. NORMALIZE: Convert all dates to ISO 8601 (YYYY-MM-DD). Convert all currency to ISO 4217 (USD, EUR, etc).

OUTPUT SCHEMA:
Return ONLY valid JSON matching this schema:
{{
    "vendor": {{ "name": "string", "address": "string", "matched_db_id": "string or null" }},
    "invoice_number": "string",
    "date": "YYYY-MM-DD",
    "currency": "ISO_CODE",
    "line_items": [
        {{ "description": "string", "qty": float, "unit_price": float, "total": float, "math_verified": boolean }}
    ],
    "subtotal": float,
    "tax": float,
    "grand_total": float,
    "validation_flags": ["list of warnings or errors"]
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
                    return {
                        "error": "Empty response from Gemini",
                        "vendor": {"name": "Unknown", "address": "", "matched_db_id": None},
                        "validation_flags": ["Gemini returned empty response"]
                    }
                
                result_text = response.text.strip()
                
                if result_text.startswith('```json'):
                    result_text = result_text[7:]
                if result_text.startswith('```'):
                    result_text = result_text[3:]
                if result_text.endswith('```'):
                    result_text = result_text[:-3]
                
                result_text = result_text.strip()
                
                validated_data = json.loads(result_text)
                
                if 'vendor' not in validated_data:
                    validated_data['vendor'] = {"name": "Unknown", "address": "", "matched_db_id": None}
                if 'validation_flags' not in validated_data:
                    validated_data['validation_flags'] = []
                
                return validated_data
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                
                response_text = response.text if response and hasattr(response, 'text') else "No response"
                print(f"Raw response: {response_text}")
                return {
                    "error": "Failed to parse Gemini response after retries",
                    "raw_response": response_text[:500] if response_text else "No response",
                    "vendor": {"name": "Unknown", "address": "", "matched_db_id": None},
                    "validation_flags": ["JSON parsing failed"]
                }
            except Exception as e:
                print(f"Gemini validation error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                
                return {
                    "error": str(e),
                    "vendor": {"name": "Unknown", "address": "", "matched_db_id": None},
                    "validation_flags": [f"Gemini error: {str(e)}"]
                }
