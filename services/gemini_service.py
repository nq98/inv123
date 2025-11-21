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
        
        self.model_name = 'gemini-1.5-pro-002'
    
    def validate_invoice(self, gcs_uri, raw_text, extracted_entities, rag_context):
        """
        Perform semantic validation and reasoning on invoice data
        
        Args:
            gcs_uri: GCS URI of the invoice image
            raw_text: Raw OCR text from Document AI
            extracted_entities: Structured entities from Document AI
            rag_context: Context from Vertex AI Search
            
        Returns:
            Validated JSON structure
        """
        prompt = f"""
You are an expert Invoice Auditor.

INPUT DATA:
1. OCR Text from Document AI: {raw_text}

2. Structured Entities from Document AI: {json.dumps(extracted_entities, indent=2)}

3. Internal Database Context (RAG): {rag_context}

YOUR TASKS:
1. Merge the Document AI entities with the visual image data to create a PERFECT JSON.
2. Compare the "Vendor Name" on the invoice with the "Internal Database Context". Use the Database spelling/ID if it's a match.
3. MATH CHECK: Write and execute Python code to verify: (Quantity * Unit Price) == Line Total. If the math is wrong on the invoice, flag it.
4. NORMALIZE: Convert all dates to ISO 8601 (YYYY-MM-DD). Convert all currency to ISO 4217 (USD, EUR).

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
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                )
            )
            
            result_text = response.text.strip() if response.text else ""
            
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.startswith('```'):
                result_text = result_text[3:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            
            result_text = result_text.strip()
            
            if not result_text:
                return {
                    "error": "Empty response from Gemini"
                }
            
            validated_data = json.loads(result_text)
            return validated_data
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            response_text = response.text if 'response' in locals() and response and hasattr(response, 'text') else "No response"
            print(f"Raw response: {response_text}")
            return {
                "error": "Failed to parse Gemini response",
                "raw_response": response_text
            }
        except Exception as e:
            print(f"Gemini validation error: {e}")
            return {
                "error": str(e)
            }
