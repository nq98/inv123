import json


class SemanticEntityClassifier:
    """
    AI-first semantic entity classifier using Gemini 1.5
    Classifies entities as VENDOR, BANK, PAYMENT_PROCESSOR, GOVERNMENT_ENTITY, or INDIVIDUAL_PERSON
    """
    
    def __init__(self, gemini_service):
        """
        Initialize SemanticEntityClassifier
        
        Args:
            gemini_service: GeminiService instance for AI classification
        """
        self.gemini = gemini_service
        
    def classify_entity(self, entity_name, entity_context=""):
        """
        Classify an entity using Gemini semantic understanding
        
        Args:
            entity_name: Name of entity to classify
            entity_context: Optional context (address, email, phone, etc.)
            
        Returns:
            {
                'entity_type': 'VENDOR' | 'BANK' | 'PAYMENT_PROCESSOR' | 'GOVERNMENT_ENTITY' | 'INDIVIDUAL_PERSON',
                'confidence': 'HIGH' | 'MEDIUM' | 'LOW',
                'reasoning': 'Explanation of classification',
                'is_valid_vendor': True/False
            }
        """
        if not entity_name or entity_name == "Unknown":
            return {
                'entity_type': 'VENDOR',
                'confidence': 'LOW',
                'reasoning': 'No entity name provided, defaulting to VENDOR',
                'is_valid_vendor': True
            }
        
        prompt = f"""You are an expert semantic entity classifier for invoice processing systems.

ENTITY TO ANALYZE:
Name: {entity_name}
Additional Context: {entity_context or 'None provided'}

YOUR TASK:
Classify this entity into ONE category based on SEMANTIC UNDERSTANDING (not keywords):

CATEGORIES:
1. VENDOR - A business or organization that provides goods/services for payment
   Examples: Software companies, consulting firms, suppliers, service providers
   
2. BANK - A financial institution that handles money/banking services
   Examples: Commercial banks, credit unions, investment banks, financial services
   
3. PAYMENT_PROCESSOR - A company that facilitates payment transactions
   Examples: Payment gateways, merchant services, payment platforms
   
4. GOVERNMENT_ENTITY - Government agency, tax authority, or regulatory body
   Examples: Tax departments, regulatory agencies, government offices
   
5. INDIVIDUAL_PERSON - A natural person, not a business entity
   Examples: Freelancers listed by personal name only, individual contractors

CLASSIFICATION RULES:
- Use SEMANTIC understanding, NOT keyword matching
- Consider the entity's PRIMARY business purpose
- Banks provide financial services, NOT goods/services for invoicing
- Payment processors facilitate transactions, they're NOT vendors
- Government entities collect taxes/fees, they're NOT vendors
- Only classify as VENDOR if the entity genuinely provides billable goods/services

OUTPUT FORMAT (STRICT JSON):
{{
    "entity_type": "VENDOR|BANK|PAYMENT_PROCESSOR|GOVERNMENT_ENTITY|INDIVIDUAL_PERSON",
    "confidence": "HIGH|MEDIUM|LOW",
    "reasoning": "Explain your semantic reasoning here (2-3 sentences)",
    "is_valid_vendor": true_or_false
}}

DO NOT use keyword matching. Rely on semantic understanding of the entity's business purpose."""

        try:
            response = self.gemini.generate_text(prompt, temperature=0.1, response_mime_type='application/json')
            
            # Parse JSON response
            result = json.loads(response)
            
            # Ensure all required fields are present
            required_fields = ['entity_type', 'confidence', 'reasoning', 'is_valid_vendor']
            for field in required_fields:
                if field not in result:
                    print(f"⚠️ Missing field '{field}' in classification result")
                    return self._create_fallback_response(entity_name, f"Missing field: {field}")
            
            # Validate entity_type
            valid_types = ['VENDOR', 'BANK', 'PAYMENT_PROCESSOR', 'GOVERNMENT_ENTITY', 'INDIVIDUAL_PERSON']
            if result['entity_type'] not in valid_types:
                print(f"⚠️ Invalid entity_type: {result['entity_type']}")
                result['entity_type'] = 'VENDOR'
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse error in entity classification: {e}")
            return self._create_fallback_response(entity_name, f"JSON parse error: {str(e)}")
        except Exception as e:
            print(f"❌ Entity classification error: {e}")
            return self._create_fallback_response(entity_name, f"Classification error: {str(e)}")
    
    def _create_fallback_response(self, entity_name, error_message):
        """
        Create a fallback response when classification fails
        
        Args:
            entity_name: Name of the entity
            error_message: Error message to include
            
        Returns:
            Fallback classification result (defaults to VENDOR for safety)
        """
        return {
            'entity_type': 'VENDOR',
            'confidence': 'LOW',
            'reasoning': f'Classification failed: {error_message}. Defaulting to VENDOR for safety.',
            'is_valid_vendor': True
        }
