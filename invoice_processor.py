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
        
        print(f"\n{'='*60}")
        print(f"PROCESSING INVOICE: {gcs_uri}")
        print(f"{'='*60}\n")
        
        raw_text = ""
        extracted_entities = {}
        vendor_name = None
        rag_context = "No vendor history found in database."
        
        try:
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
                'entity_types': list(extracted_entities.keys()),
                'entities': extracted_entities
            }
        except Exception as e:
            print(f"✗ Document AI error: {str(e)}")
            result['layers']['layer1_document_ai'] = {
                'status': 'error',
                'error': str(e)
            }
            result['status'] = 'error'
            result['error'] = f"Document AI failed: {str(e)}"
            result['validated_data'] = {
                'error': str(e),
                'validation_flags': ['Document AI processing failed']
            }
            return result
        
        try:
            print("\nLAYER 2: Vertex AI Search (RAG) - Context Retrieval")
            print("-" * 60)
            vendor_name = extract_vendor_name(extracted_entities)
            print(f"✓ Extracted vendor name: {vendor_name}")
            
            # Search for vendor information
            vendor_search_results = []
            vendor_context = "No vendor history found in database."
            
            if vendor_name:
                vendor_search_results = self.vertex_search_service.search_vendor(vendor_name)
                vendor_context = self.vertex_search_service.format_context(vendor_search_results)
                print(f"✓ Found {len(vendor_search_results)} vendor matches in RAG datastore")
            else:
                print("⚠ No vendor name found, skipping vendor lookup")
            
            # Search for similar past invoice extractions (RAG self-learning)
            print("🧠 Searching for similar past invoice extractions...")
            invoice_extraction_results = self.vertex_search_service.search_similar_invoices(
                document_text=raw_text,
                vendor_name=vendor_name,
                limit=3
            )
            
            invoice_extraction_context = self.vertex_search_service.format_invoice_extraction_context(
                invoice_extraction_results
            )
            
            if invoice_extraction_results:
                print(f"✓ Found {len(invoice_extraction_results)} similar past invoice extractions")
            else:
                print("ℹ️ No similar past extractions found - this is a new pattern")
            
            # Combine vendor context and invoice extraction context
            rag_context = f"{vendor_context}\n\n{invoice_extraction_context}"
            
            result['layers']['layer2_vertex_search'] = {
                'status': 'success',
                'vendor_query': vendor_name,
                'vendor_matches_found': len(vendor_search_results),
                'similar_invoices_found': len(invoice_extraction_results)
            }
        except Exception as e:
            print(f"⚠ Vertex Search error (non-critical): {str(e)}")
            result['layers']['layer2_vertex_search'] = {
                'status': 'warning',
                'error': str(e)
            }
        
        try:
            print("\nLAYER 3: Gemini - Semantic Validation & Math Checking")
            print("-" * 60)
            validated_data = self.gemini_service.validate_invoice(
                gcs_uri,
                raw_text,
                extracted_entities,
                rag_context
            )
            
            if 'error' in validated_data:
                print(f"⚠ Gemini validation completed with warnings: {validated_data.get('error', 'Unknown')}")
                result['layers']['layer3_gemini'] = {
                    'status': 'completed_with_warnings',
                    'error': validated_data.get('error')
                }
            else:
                print("✓ Semantic validation complete")
                print(f"✓ Invoice Number: {validated_data.get('invoiceNumber', 'N/A')}")
                print(f"✓ Vendor: {validated_data.get('vendor', {}).get('name', 'N/A')}")
                totals = validated_data.get('totals', {})
                total_amount = totals.get('total', 'N/A') if totals else 'N/A'
                print(f"✓ Grand Total: {total_amount} {validated_data.get('currency', 'USD')}")
                
                flags = validated_data.get('validation_flags', [])
                if flags:
                    print(f"⚠ Validation flags: {', '.join(flags)}")
                
                result['layers']['layer3_gemini'] = {
                    'status': 'success',
                    'validation_flags': flags
                }
            
            result['status'] = 'completed'
            result['validated_data'] = validated_data
            
            # FEEDBACK LOOP: Store successful extraction to knowledge base for future learning
            try:
                extraction_confidence = validated_data.get('extractionConfidence', 0.0)
                if extraction_confidence > 0.7 and 'error' not in validated_data:
                    print("\n🧠 FEEDBACK LOOP: Storing extraction to knowledge base...")
                    extracted_vendor_name = validated_data.get('vendor', {}).get('name') or vendor_name
                    
                    stored = self.vertex_search_service.store_invoice_extraction(
                        document_text=raw_text,
                        vendor_name=extracted_vendor_name,
                        extracted_data=validated_data,
                        success=True
                    )
                    
                    if stored:
                        result['layers']['feedback_loop'] = {
                            'status': 'success',
                            'stored_to_knowledge_base': True,
                            'confidence': extraction_confidence
                        }
                    else:
                        result['layers']['feedback_loop'] = {
                            'status': 'warning',
                            'stored_to_knowledge_base': False,
                            'reason': 'Storage failed but extraction succeeded'
                        }
                else:
                    print(f"ℹ️ Skipping knowledge base storage (confidence={extraction_confidence:.2f}, threshold=0.7)")
                    result['layers']['feedback_loop'] = {
                        'status': 'skipped',
                        'reason': f'Confidence too low ({extraction_confidence:.2f} < 0.7) or extraction had errors'
                    }
            except Exception as e:
                print(f"⚠ Feedback loop error (non-critical): {str(e)}")
                result['layers']['feedback_loop'] = {
                    'status': 'error',
                    'error': str(e)
                }
            
            print(f"\n{'='*60}")
            print("PROCESSING COMPLETE")
            print(f"{'='*60}\n")
            
            return result
            
        except Exception as e:
            print(f"✗ Gemini validation error: {str(e)}")
            result['layers']['layer3_gemini'] = {
                'status': 'error',
                'error': str(e)
            }
            result['status'] = 'error'
            result['error'] = f"Gemini validation failed: {str(e)}"
            result['validated_data'] = {
                'error': str(e),
                'validation_flags': ['Gemini validation failed']
            }
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
        from google.oauth2 import service_account
        import os
        
        try:
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH
            )
            storage_client = storage.Client(
                project=config.GOOGLE_CLOUD_PROJECT_ID,
                credentials=credentials
            )
            bucket = storage_client.bucket(config.GCS_INPUT_BUCKET)
            
            filename = os.path.basename(file_path)
            blob = bucket.blob(f"uploads/{filename}")
            
            print(f"Uploading {filename} to GCS...")
            blob.upload_from_filename(file_path, content_type=mime_type)
            
            gcs_uri = f"gs://{config.GCS_INPUT_BUCKET}/uploads/{filename}"
            print(f"✓ Uploaded to: {gcs_uri}")
            
            return self.process_invoice(gcs_uri, mime_type)
        except Exception as e:
            print(f"✗ Error uploading file to GCS: {str(e)}")
            return {
                'status': 'error',
                'error': f"Failed to upload file: {str(e)}",
                'details': 'Check Google Cloud credentials and bucket permissions'
            }
