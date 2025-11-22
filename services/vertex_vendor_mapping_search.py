import os
import json
import hashlib
from datetime import datetime
from google.cloud import discoveryengine_v1 as discoveryengine
from google.oauth2 import service_account
from config import config

class VertexVendorMappingSearch:
    """
    Vertex AI Search RAG service for vendor CSV mapping knowledge base
    
    Stores and retrieves past CSV mapping metadata to enable:
    - Learning from historical uploads
    - Context-aware mapping suggestions
    - Multi-tenant mapping intelligence
    - Adaptive ERP system recognition
    """
    
    def __init__(self):
        # Use vertex-runner service account
        credentials_path = config.VERTEX_RUNNER_SA_PATH
        if not credentials_path or not os.path.exists(credentials_path):
            raise ValueError(f"Vertex AI credentials not found at {credentials_path}")
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        self.project_id = config.GOOGLE_CLOUD_PROJECT_ID
        self.project_number = config.GOOGLE_CLOUD_PROJECT_NUMBER
        self.location = "global"
        
        # Use separate datastore for vendor mapping metadata
        self.datastore_id = "vendor-mappings-ds"
        
        # Initialize Vertex AI Search clients
        self.search_client = discoveryengine.SearchServiceClient(credentials=credentials)
        self.document_client = discoveryengine.DocumentServiceClient(credentials=credentials)
        
        # Build serving config path
        self.serving_config = (
            f"projects/{self.project_number}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{self.datastore_id}/"
            f"servingConfigs/default_search"
        )
        
        # Build parent path for documents
        self.parent = (
            f"projects/{self.project_number}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{self.datastore_id}/"
            f"branches/default_branch"
        )
    
    def generate_csv_fingerprint(self, headers, sample_data=None):
        """
        Generate unique fingerprint for CSV structure
        
        Args:
            headers: List of column names
            sample_data: Optional sample rows for better fingerprinting
        
        Returns:
            Unique hash identifying this CSV structure
        """
        # Sort headers for consistent fingerprinting
        sorted_headers = sorted(headers)
        fingerprint_data = json.dumps({
            "headers": sorted_headers,
            "header_count": len(headers)
        }, sort_keys=True)
        
        return hashlib.md5(fingerprint_data.encode()).hexdigest()
    
    def search_similar_mappings(self, headers, detected_language=None, limit=5):
        """
        Search Vertex AI for similar CSV mappings based on column structure
        
        Args:
            headers: List of column names from current CSV
            detected_language: Optional language code (e.g., 'de', 'es', 'en')
            limit: Max number of similar mappings to return
        
        Returns:
            List of similar mapping metadata from past uploads
        """
        
        try:
            # Build search query
            # Include header names and language for semantic matching
            query_parts = [f"CSV columns: {', '.join(headers[:10])}"]  # First 10 columns
            if detected_language:
                query_parts.append(f"language: {detected_language}")
            
            search_query = " ".join(query_parts)
            
            # Create search request
            request = discoveryengine.SearchRequest(
                serving_config=self.serving_config,
                query=search_query,
                page_size=limit,
                query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                    condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
                ),
                spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                    mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
                ),
            )
            
            # Execute search
            response = self.search_client.search(request)
            
            similar_mappings = []
            for result in response.results:
                try:
                    # Extract document data
                    doc_data = result.document.derived_struct_data
                    
                    mapping_info = {
                        "csv_fingerprint": doc_data.get("csv_fingerprint", "unknown"),
                        "detected_language": doc_data.get("detected_language", "unknown"),
                        "source_system": doc_data.get("source_system_guess", "unknown"),
                        "column_mapping": doc_data.get("column_mapping", {}),
                        "confidence": doc_data.get("overall_confidence", 0.0),
                        "upload_count": doc_data.get("upload_count", 1),
                        "success_rate": doc_data.get("success_rate", 1.0),
                        "last_used": doc_data.get("last_used", None)
                    }
                    
                    similar_mappings.append(mapping_info)
                    
                except Exception as e:
                    print(f"⚠️ Error parsing search result: {e}")
                    continue
            
            if similar_mappings:
                print(f"✓ Found {len(similar_mappings)} similar CSV mappings in knowledge base")
            else:
                print("ℹ️ No similar CSV mappings found - this is a new structure")
            
            return similar_mappings
            
        except Exception as e:
            print(f"⚠️ Error searching vendor mappings: {e}")
            # Return empty list on error - system will work without RAG context
            return []
    
    def store_mapping(self, headers, column_mapping, detected_language, source_system, 
                     overall_confidence, success=True):
        """
        Store successful CSV mapping to Vertex AI Search for future learning
        
        Args:
            headers: List of column names
            column_mapping: Dict mapping CSV columns to target fields
            detected_language: Language code (e.g., 'de', 'es', 'en')
            source_system: Detected ERP system (e.g., 'SAP', 'QuickBooks')
            overall_confidence: AI confidence score (0.0-1.0)
            success: Whether import was successful
        
        Returns:
            True if stored successfully, False otherwise
        """
        
        try:
            # Generate fingerprint
            fingerprint = self.generate_csv_fingerprint(headers)
            
            # Create document ID (use fingerprint for deduplication)
            doc_id = f"mapping_{fingerprint}"
            
            # Try to get existing document to update upload count
            existing_doc = None
            try:
                doc_path = f"{self.parent}/documents/{doc_id}"
                existing_doc = self.document_client.get_document(name=doc_path)
            except Exception:
                # Document doesn't exist yet - that's OK
                pass
            
            # Calculate updated stats
            upload_count = 1
            success_count = 1 if success else 0
            
            if existing_doc:
                existing_data = existing_doc.derived_struct_data
                upload_count = existing_data.get("upload_count", 0) + 1
                success_count = existing_data.get("success_count", 0) + (1 if success else 0)
            
            success_rate = success_count / upload_count if upload_count > 0 else 0.0
            
            # Create document content
            document_data = {
                "csv_fingerprint": fingerprint,
                "headers": headers,
                "header_count": len(headers),
                "detected_language": detected_language or "unknown",
                "source_system_guess": source_system or "unknown",
                "column_mapping": column_mapping,
                "overall_confidence": overall_confidence,
                "upload_count": upload_count,
                "success_count": success_count,
                "success_rate": success_rate,
                "last_used": datetime.utcnow().isoformat(),
                "created_at": existing_doc.derived_struct_data.get("created_at") if existing_doc else datetime.utcnow().isoformat(),
            }
            
            # Create searchable text content
            text_content = f"""
            CSV Mapping Knowledge Base Entry
            
            Language: {detected_language or 'unknown'}
            Source System: {source_system or 'unknown'}
            
            CSV Columns: {', '.join(headers)}
            
            Column Mappings:
            {json.dumps(column_mapping, indent=2)}
            
            Stats:
            - Upload Count: {upload_count}
            - Success Rate: {success_rate * 100:.1f}%
            - Overall Confidence: {overall_confidence * 100:.1f}%
            
            Last Used: {document_data['last_used']}
            """
            
            # Create or update document
            document = discoveryengine.Document(
                name=f"{self.parent}/documents/{doc_id}",
                id=doc_id,
                derived_struct_data=document_data,
                content=discoveryengine.Document.Content(
                    mime_type="text/plain",
                    raw_bytes=text_content.encode('utf-8')
                )
            )
            
            if existing_doc:
                # Update existing document
                self.document_client.update_document(document=document)
                print(f"✓ Updated vendor mapping in knowledge base (upload #{upload_count})")
            else:
                # Create new document
                request = discoveryengine.CreateDocumentRequest(
                    parent=self.parent,
                    document=document,
                    document_id=doc_id
                )
                self.document_client.create_document(request=request)
                print(f"✓ Stored new vendor mapping in knowledge base")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Error storing vendor mapping: {e}")
            # Don't fail the import if RAG storage fails
            return False
