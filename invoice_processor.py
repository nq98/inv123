import json
from services import DocumentAIService, VertexSearchService, GeminiService
from utils import extract_vendor_name, format_search_results
from config import config

class InvoiceProcessor:
    """
    Main invoice processing pipeline orchestrating the 3-layer architecture:
    Layer 1: Document AI for structure extraction
    Layer 2: Vertex AI Search (RAG) for context retrieval
    Layer 3: Gemini for semantic validation and reasoning
    """
    
    def __init__(self):
        self.doc_ai_service = DocumentAIService()
        self.vertex_search_service = VertexSearchService()
        self.gemini_service = GeminiService()
    
    def process_invoice(self, gcs_uri, mime_type='application/pdf'):
        """
        Process an invoice through the complete 3-layer pipeline
        
        Args:
            gcs_uri: GCS URI of the invoice (e.g., gs://bucket/invoice.pdf)
            mime_type: MIME type of the invoice file
            
        Returns:
            Dictionary containing validated invoice data
        """
        result = {
            'gcs_uri': gcs_uri,
            'status': 'processing',
            'layers': {}
        }
        
        try:
            print(f"\n{'='*60}")
            print(f"PROCESSING INVOICE: {gcs_uri}")
            print(f"{'='*60}\n")
            
            print("LAYER 1: Document AI - Structure Extraction")
            print("-" * 60)
            document = self.doc_ai_service.process_document(gcs_uri, mime_type)
            raw_text = self.doc_ai_service.get_raw_text(document)
            extracted_entities = self.doc_ai_service.extract_entities(document)
            
            print(f"✓ Extracted {len(raw_text)} characters of text")
            print(f"✓ Found {len(extracted_entities)} entity types")
            
            result['layers']['layer1_document_ai'] = {
                'status': 'success',
                'text_length': len(raw_text),
                'entity_types': list(extracted_entities.keys())
            }
            
            print("\nLAYER 2: Vertex AI Search (RAG) - Context Retrieval")
            print("-" * 60)
            vendor_name = extract_vendor_name(extracted_entities)
            print(f"✓ Extracted vendor name: {vendor_name}")
            
            search_results = []
            rag_context = "No vendor history found in database."
            
            if vendor_name:
                search_results = self.vertex_search_service.search_vendor(vendor_name)
                rag_context = self.vertex_search_service.format_context(search_results)
                print(f"✓ Found {len(search_results)} vendor matches in RAG datastore")
            else:
                print("⚠ No vendor name found, skipping RAG lookup")
            
            result['layers']['layer2_vertex_search'] = {
                'status': 'success',
                'vendor_query': vendor_name,
                'matches_found': len(search_results)
            }
            
            print("\nLAYER 3: Gemini - Semantic Validation & Math Checking")
            print("-" * 60)
            validated_data = self.gemini_service.validate_invoice(
                gcs_uri,
                raw_text,
                extracted_entities,
                rag_context
            )
            
            if 'error' in validated_data:
                print(f"✗ Gemini validation error: {validated_data['error']}")
                result['layers']['layer3_gemini'] = {
                    'status': 'error',
                    'error': validated_data['error']
                }
            else:
                print("✓ Semantic validation complete")
                print(f"✓ Invoice Number: {validated_data.get('invoice_number', 'N/A')}")
                print(f"✓ Vendor: {validated_data.get('vendor', {}).get('name', 'N/A')}")
                print(f"✓ Grand Total: {validated_data.get('grand_total', 'N/A')} {validated_data.get('currency', '')}")
                
                flags = validated_data.get('validation_flags', [])
                if flags:
                    print(f"⚠ Validation flags: {', '.join(flags)}")
                
                result['layers']['layer3_gemini'] = {
                    'status': 'success',
                    'validation_flags': flags
                }
            
            result['status'] = 'completed'
            result['validated_data'] = validated_data
            
            print(f"\n{'='*60}")
            print("PROCESSING COMPLETE")
            print(f"{'='*60}\n")
            
            return result
            
        except Exception as e:
            print(f"\n✗ ERROR: {str(e)}\n")
            result['status'] = 'error'
            result['error'] = str(e)
            return result
    
    def process_local_file(self, file_path, mime_type='application/pdf'):
        """
        Process a local file by uploading to GCS first
        
        Args:
            file_path: Local path to invoice file
            mime_type: MIME type of the file
            
        Returns:
            Dictionary containing validated invoice data
        """
        from google.cloud import storage
        import os
        
        storage_client = storage.Client(project=config.GOOGLE_CLOUD_PROJECT_ID)
        bucket = storage_client.bucket(config.GCS_INPUT_BUCKET)
        
        filename = os.path.basename(file_path)
        blob = bucket.blob(f"uploads/{filename}")
        
        print(f"Uploading {filename} to GCS...")
        blob.upload_from_filename(file_path, content_type=mime_type)
        
        gcs_uri = f"gs://{config.GCS_INPUT_BUCKET}/uploads/{filename}"
        print(f"✓ Uploaded to: {gcs_uri}")
        
        return self.process_invoice(gcs_uri, mime_type)
