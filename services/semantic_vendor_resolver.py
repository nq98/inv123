"""
Semantic Vendor Identity Resolver - AI-First Vendor Identification

This service uses Gemini AI to semantically reason about vendor identity by analyzing
ALL identity signals (supplier name, payment recipient, bank holder, etc.) to determine
the TRUE vendor (economic beneficiary who receives payment).

This is the core of making the system truly "AI-first semantic" instead of blindly
trusting Document AI's supplier_name field.
"""

import json
from typing import Dict, Any, Optional
from google import genai
from google.genai import types


class SemanticVendorResolver:
    """
    Semantic Vendor Identity Resolver
    
    Analyzes all vendor-related signals from an invoice to determine the TRUE vendor
    using AI reasoning instead of hardcoded field priority.
    """
    
    def __init__(self, gemini_service):
        """
        Initialize the resolver with Gemini service
        
        Args:
            gemini_service: GeminiService instance for AI reasoning
        """
        self.gemini = gemini_service
        
    def resolve_vendor_identity(
        self,
        document_ai_entities: Dict[str, Any],
        validated_data: Dict[str, Any],
        rag_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve the TRUE vendor identity using semantic AI reasoning
        
        Analyzes:
        - Invoice header supplier name
        - Payment recipient (remit_to_name)
        - Bank account holder
        - Email domains
        - Payment instructions
        - RAG history (if available)
        
        Returns:
            {
                "true_vendor": {
                    "name": str,
                    "confidence": float (0.0-1.0),
                    "type": "INDIVIDUAL" | "COMPANY" | "BRAND" | "INTERMEDIARY"
                },
                "reasoning": str,
                "identity_signals": {
                    "supplier_name": str,
                    "payment_recipient": str,
                    "bank_holder": str,
                    "email_domain": str
                },
                "is_intermediary_scenario": bool,
                "supplier_relationship": str (if intermediary),
                "alternate_names": [str],
                "conflicts_detected": [str]
            }
        """
        
        # Extract all identity signals from the invoice
        signals = self._extract_identity_signals(document_ai_entities, validated_data)
        
        # Build reasoning prompt for Gemini
        prompt = self._build_reasoning_prompt(signals, rag_context)
        
        try:
            # Call Gemini with semantic reasoning
            response = self.gemini._generate_content_with_fallback(
                model=self.gemini.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type='application/json',
                    response_schema={
                        "type": "object",
                        "properties": {
                            "true_vendor": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "confidence": {"type": "number"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["INDIVIDUAL", "COMPANY", "BRAND", "INTERMEDIARY"]
                                    }
                                },
                                "required": ["name", "confidence", "type"]
                            },
                            "reasoning": {"type": "string"},
                            "is_intermediary_scenario": {"type": "boolean"},
                            "supplier_relationship": {"type": "string"},
                            "alternate_names": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "conflicts_detected": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": [
                            "true_vendor",
                            "reasoning",
                            "is_intermediary_scenario",
                            "alternate_names",
                            "conflicts_detected"
                        ]
                    }
                )
            )
            
            result = json.loads(response.text or "{}")
            
            # Add identity signals to result for transparency
            result["identity_signals"] = signals
            
            print(f"🧠 Semantic Vendor Resolution:")
            print(f"   TRUE Vendor: {result.get('true_vendor', {}).get('name', 'Unknown')}")
            print(f"   Confidence: {result.get('true_vendor', {}).get('confidence', 0.0):.2f}")
            print(f"   Type: {result.get('true_vendor', {}).get('type', 'Unknown')}")
            if result.get('is_intermediary_scenario'):
                print(f"   ⚠️  Intermediary detected: {result.get('supplier_relationship', 'Unknown')}")
            print(f"   Reasoning: {result.get('reasoning', 'No reasoning provided')}")
            
            return result
            
        except Exception as e:
            print(f"❌ Semantic vendor resolution failed: {e}")
            # Fallback: return supplier_name with low confidence
            return {
                "true_vendor": {
                    "name": signals.get("supplier_name", "Unknown"),
                    "confidence": 0.5,
                    "type": "UNKNOWN"
                },
                "reasoning": f"Fallback to supplier_name due to error: {str(e)}",
                "identity_signals": signals,
                "is_intermediary_scenario": False,
                "supplier_relationship": None,
                "alternate_names": [],
                "conflicts_detected": [f"Resolution failed: {str(e)}"]
            }
    
    def _extract_identity_signals(
        self,
        document_ai_entities: Dict[str, Any],
        validated_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract all vendor identity signals from invoice data
        
        Returns dict with all available identity information
        """
        signals = {}
        
        # Document AI entities
        entities = document_ai_entities.get("entities", {})
        
        # Supplier name (invoice header/letterhead)
        supplier_name_list = entities.get("supplier_name", [])
        if supplier_name_list:
            signals["supplier_name"] = supplier_name_list[0].get("normalized_value") or supplier_name_list[0].get("value")
        
        # Payment recipient (remit_to)
        remit_to_list = entities.get("remit_to_name", [])
        if remit_to_list:
            signals["remit_to_name"] = remit_to_list[0].get("normalized_value") or remit_to_list[0].get("value")
        
        # Email
        supplier_email_list = entities.get("supplier_email", [])
        if supplier_email_list:
            email = supplier_email_list[0].get("normalized_value") or supplier_email_list[0].get("value")
            signals["supplier_email"] = email
            # Extract domain
            if "@" in email:
                signals["email_domain"] = email.split("@")[1]
        
        # Phone
        supplier_phone_list = entities.get("supplier_phone", [])
        if supplier_phone_list:
            signals["supplier_phone"] = supplier_phone_list[0].get("normalized_value") or supplier_phone_list[0].get("value")
        
        # Website
        supplier_website_list = entities.get("supplier_website", [])
        if supplier_website_list:
            signals["supplier_website"] = supplier_website_list[0].get("normalized_value") or supplier_website_list[0].get("value")
        
        # Validated data (Gemini extraction)
        vendor_data = validated_data.get("vendor", {})
        if vendor_data:
            signals["validated_vendor_name"] = vendor_data.get("name")
            signals["validated_email"] = vendor_data.get("email")
            signals["validated_phone"] = vendor_data.get("phone")
            signals["validated_address"] = vendor_data.get("address")
        
        # Payment details
        payment_details = validated_data.get("paymentDetails", {})
        if payment_details:
            signals["bank_name"] = payment_details.get("bankName")
            signals["iban"] = payment_details.get("iban")
            signals["swift"] = payment_details.get("swift")
            signals["account_number"] = payment_details.get("accountNumber")
            
            # Try to extract beneficiary name from payment instructions
            instructions = payment_details.get("paymentInstructions", "")
            if instructions:
                signals["payment_instructions"] = instructions
                # Look for "Payable to:" or "Name:" patterns
                if "Payable to:" in instructions or "Name:" in instructions:
                    signals["payment_instructions_snippet"] = instructions[:200]
        
        return signals
    
    def _build_reasoning_prompt(
        self,
        signals: Dict[str, Any],
        rag_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build semantic reasoning prompt for Gemini
        """
        
        # Format signals for readability
        signals_text = json.dumps(signals, indent=2)
        
        rag_text = ""
        if rag_context and rag_context.get("vendor_matches_found", 0) > 0:
            rag_text = f"\n\n**VENDOR HISTORY (RAG):**\n{json.dumps(rag_context, indent=2)}"
        
        prompt = f"""You are an AI-first semantic vendor identity resolver for an AP automation system.

Your task is to determine the TRUE VENDOR (economic beneficiary who receives payment) by analyzing ALL identity signals from an invoice.

**IDENTITY SIGNALS EXTRACTED FROM INVOICE:**
{signals_text}{rag_text}

**YOUR REASONING PROCESS:**

1. **Identify all names mentioned:**
   - Invoice header/letterhead supplier name
   - Payment recipient (remit_to_name)
   - Names in payment instructions
   - Bank account holder (if extractable)
   - Email domain owner

2. **Semantic Analysis:**
   - Who is RECEIVING the money? (Follow the payment flow)
   - Is supplier_name the same as payment_recipient?
   - If different: Is supplier a BRAND/AGENCY invoicing on behalf of individual?
   - Is this a freelancer using a business name?
   - Is this an intermediary/marketplace scenario?

3. **Determine TRUE VENDOR:**
   - **Priority Rule**: The economic beneficiary (person/entity receiving funds) is the TRUE vendor
   - If invoice says "Company X" but payment goes to "Person Y" → Person Y is TRUE vendor
   - If all names match → That entity is TRUE vendor
   - Consider email domains: generic (@gmail.com) vs corporate
   - Use semantic reasoning (NOT keyword matching)

4. **Confidence Scoring:**
   - 0.95-1.0: All signals agree, clear identity
   - 0.75-0.90: Minor conflicts but clear payment recipient
   - 0.50-0.70: Significant conflicts or ambiguity
   - 0.0-0.45: Cannot determine true vendor

5. **Type Classification:**
   - INDIVIDUAL: Person (freelancer, contractor)
   - COMPANY: Registered business entity
   - BRAND: Business name used by individual
   - INTERMEDIARY: Agency/platform invoicing on behalf of someone

**CRITICAL RULES:**
- Always follow the money flow
- Payment recipient > Invoice letterhead
- Explain conflicts clearly
- Be explicit about intermediary scenarios
- Return structured JSON only

**OUTPUT FORMAT:**
{{
  "true_vendor": {{
    "name": "Actual person/entity receiving payment",
    "confidence": 0.0-1.0,
    "type": "INDIVIDUAL|COMPANY|BRAND|INTERMEDIARY"
  }},
  "reasoning": "Clear explanation of your decision process and why you chose this vendor",
  "is_intermediary_scenario": true/false,
  "supplier_relationship": "If intermediary: explain relationship (e.g., 'Fully Booked is brand name used by Artem for invoicing')",
  "alternate_names": ["All other names found"],
  "conflicts_detected": ["List any conflicts between different identity signals"]
}}

Now analyze the identity signals and determine the TRUE vendor."""
        
        return prompt


def create_semantic_vendor_resolver(gemini_service):
    """Factory function to create SemanticVendorResolver instance"""
    return SemanticVendorResolver(gemini_service)
