import json
from services import DocumentAIService, VertexSearchService, GeminiService
from services.semantic_vendor_resolver import SemanticVendorResolver
from utils import extract_vendor_name, format_search_results
from utils.multi_currency_detector import MultiCurrencyDetector
from config import config

class InvoiceProcessor:
    """
    Main invoice processing pipeline orchestrating the 3-layer architecture:
    Layer 1: Document AI for structure extraction
    Layer 1.5: Multi-Currency Detection and Analysis
    Layer 2: Vertex AI Search (RAG) for context retrieval
    Layer 3: Gemini for semantic validation and reasoning
    """
    
    def __init__(self):
        self.doc_ai_service = DocumentAIService()
        self.multi_currency_detector = MultiCurrencyDetector()
        self.vertex_search_service = VertexSearchService()
        self.gemini_service = GeminiService()
        self.vendor_resolver = SemanticVendorResolver(self.gemini_service)
    
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
        
        # LAYER 1.5: Multi-Currency Detection
        currency_context = None
        try:
            print("\nLAYER 1.5: Multi-Currency Detection & Analysis")
            print("-" * 60)
            currency_context = self.multi_currency_detector.analyze_invoice_currencies(
                document_text=raw_text,
                document_ai_result=extracted_entities
            )
            
            is_multi = currency_context.get('is_multi_currency', False)
            currencies_found = currency_context.get('currency_symbols_found', [])
            exchange_rates = currency_context.get('exchange_rates', {})
            
            if is_multi:
                print(f"⚠️  MULTI-CURRENCY INVOICE DETECTED")
                print(f"✓ Currencies found: {', '.join(currencies_found)}")
                if exchange_rates:
                    for rate_key, rate_value in exchange_rates.items():
                        print(f"✓ Exchange rate: {rate_key.replace('_TO_', ' → ')} = {rate_value}")
                base_curr = currency_context.get('base_currency', 'N/A')
                settlement_curr = currency_context.get('settlement_currency', 'N/A')
                print(f"✓ Base currency (unit prices): {base_curr}")
                print(f"✓ Settlement currency (totals): {settlement_curr}")
            else:
                print("✓ Single-currency invoice detected")
                if currencies_found:
                    print(f"✓ Currency: {currencies_found[0] if currencies_found else 'N/A'}")
            
            result['layers']['layer1_5_multi_currency'] = {
                'status': 'success',
                'is_multi_currency': is_multi,
                'currencies_found': currencies_found,
                'exchange_rates': exchange_rates,
                'base_currency': currency_context.get('base_currency'),
                'settlement_currency': currency_context.get('settlement_currency')
            }
        except Exception as e:
            print(f"⚠ Multi-currency detection error (non-critical): {str(e)}")
            result['layers']['layer1_5_multi_currency'] = {
                'status': 'warning',
                'error': str(e)
            }
        
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
                rag_context,
                currency_context=currency_context
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
            
            # LAYER 3.5: Semantic Vendor Identity Resolution (AI-First Vendor Identification)
            try:
                print("\n🧠 LAYER 3.5: Semantic Vendor Identity Resolution")
                print("-" * 60)
                
                # Resolve TRUE vendor identity using AI reasoning
                vendor_resolution = self.vendor_resolver.resolve_vendor_identity(
                    document_ai_entities={'entities': extracted_entities},
                    validated_data=validated_data,
                    rag_context=result['layers'].get('layer2_vertex_search')
                )
                
                # Replace vendor in validated_data with semantically resolved vendor
                if vendor_resolution and 'true_vendor' in vendor_resolution:
                    true_vendor_name = vendor_resolution['true_vendor']['name']
                    true_vendor_confidence = vendor_resolution['true_vendor']['confidence']
                    
                    # Update vendor in validated_data
                    if 'vendor' not in validated_data:
                        validated_data['vendor'] = {}
                    
                    # Store original vendor for audit trail
                    validated_data['vendor']['original_supplier_name'] = validated_data.get('vendor', {}).get('name')
                    
                    # Replace with semantically resolved vendor
                    validated_data['vendor']['name'] = true_vendor_name
                    
                    # Add resolution metadata
                    validated_data['vendor_resolution'] = {
                        'is_intermediary': vendor_resolution.get('is_intermediary_scenario', False),
                        'supplier_relationship': vendor_resolution.get('supplier_relationship'),
                        'resolution_confidence': true_vendor_confidence,
                        'reasoning': vendor_resolution.get('reasoning'),
                        'conflicts_detected': vendor_resolution.get('conflicts_detected', []),
                        'alternate_names': vendor_resolution.get('alternate_names', [])
                    }
                    
                    print(f"✓ Vendor resolution complete")
                    
                    result['layers']['layer3_5_vendor_resolution'] = {
                        'status': 'success',
                        'true_vendor': true_vendor_name,
                        'original_supplier': validated_data['vendor'].get('original_supplier_name'),
                        'confidence': true_vendor_confidence,
                        'is_intermediary': vendor_resolution.get('is_intermediary_scenario', False)
                    }
                else:
                    print("⚠️ Vendor resolution returned no results")
                    result['layers']['layer3_5_vendor_resolution'] = {
                        'status': 'warning',
                        'message': 'No vendor resolution results'
                    }
                    
            except Exception as e:
                print(f"⚠️ Vendor resolution error (non-critical): {str(e)}")
                result['layers']['layer3_5_vendor_resolution'] = {
                    'status': 'error',
                    'error': str(e)
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
