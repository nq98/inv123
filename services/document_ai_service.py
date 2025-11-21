import os
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
from config import config

class DocumentAIService:
    """Service for extracting structured data from invoices using Document AI"""
    
    def __init__(self):
        if os.path.exists(config.DOCUMENTAI_ACCESS_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.DOCUMENTAI_ACCESS_SA_PATH
            )
            self.client = documentai.DocumentProcessorServiceClient(credentials=credentials)
        else:
            self.client = documentai.DocumentProcessorServiceClient()
    
    def process_document(self, gcs_uri, mime_type='application/pdf'):
        """
        Process an invoice document using Document AI
        
        Args:
            gcs_uri: GCS URI of the document (e.g., gs://bucket/file.pdf)
            mime_type: MIME type of the document
            
        Returns:
            Processed document with extracted entities
        """
        if not config.DOCAI_PROCESSOR_NAME:
            raise ValueError("DOCAI_PROCESSOR_NAME not configured. Check DOCAI_PROCESSOR_ID and DOCAI_LOCATION.")
        
        try:
            gcs_document = documentai.GcsDocument(
                gcs_uri=gcs_uri,
                mime_type=mime_type
            )
            
            request = documentai.ProcessRequest(
                name=config.DOCAI_PROCESSOR_NAME,
                gcs_document=gcs_document
            )
            
            result = self.client.process_document(request=request)
            return result.document
        except Exception as e:
            raise RuntimeError(f"Document AI processing failed: {str(e)}") from e
    
    def extract_entities(self, document):
        """
        Extract structured entities from Document AI result
        
        Returns:
            Dictionary of extracted entities
        """
        entities = {}
        for entity in document.entities:
            entity_type = entity.type_
            entity_value = entity.mention_text if hasattr(entity, 'mention_text') else entity.text_anchor.content
            
            if entity_type not in entities:
                entities[entity_type] = []
            
            entities[entity_type].append({
                'value': entity_value,
                'confidence': entity.confidence if hasattr(entity, 'confidence') else 1.0,
                'normalized_value': entity.normalized_value.text if hasattr(entity, 'normalized_value') else None
            })
        
        return entities
    
    def get_raw_text(self, document):
        """Extract raw OCR text from document"""
        return document.text
