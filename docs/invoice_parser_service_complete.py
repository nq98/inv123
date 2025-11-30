"""
Complete Invoice Parser Service
4-Layer Hybrid AI Extraction Engine

Copy this to: services/invoice_parser_service.py
"""

import os
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google.cloud import bigquery
import google.generativeai as genai

logger = logging.getLogger(__name__)


class InvoiceParserService:
    """
    4-Layer Hybrid Invoice Parsing Engine
    
    Layer 1: Document AI (OCR + layout)
    Layer 2: Vertex AI Search RAG (historical context)
    Layer 3: Gemini AI (semantic reasoning)
    Layer 4: Validation & verification
    """
    
    PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    DATASET_ID = 'vendors_ai'
    LOCATION = 'us'
    PROCESSOR_ID = os.environ.get('DOCUMENT_AI_PROCESSOR_ID')
    GCS_BUCKET = os.environ.get('GCS_BUCKET', 'payouts-invoices')
    
    def __init__(self):
        self._init_clients()
        self._ensure_table_exists()
    
    def _init_clients(self):
        """Initialize all Google Cloud clients"""
        creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        credentials = None
        
        if creds_json:
            from google.oauth2 import service_account
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
        
        try:
            if credentials:
                self.doc_ai_client = documentai.DocumentProcessorServiceClient(credentials=credentials)
                self.storage_client = storage.Client(credentials=credentials)
                self.bq_client = bigquery.Client(credentials=credentials, project=self.PROJECT_ID)
            else:
                self.doc_ai_client = documentai.DocumentProcessorServiceClient()
                self.storage_client = storage.Client()
                self.bq_client = bigquery.Client(project=self.PROJECT_ID)
            
            self.bucket = self.storage_client.bucket(self.GCS_BUCKET)
            logger.info("All clients initialized")
        except Exception as e:
            logger.error(f"Client initialization failed: {e}")
            self.doc_ai_client = None
            self.storage_client = None
            self.bq_client = None
        
        api_key = os.environ.get('GOOGLE_GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-pro')
        else:
            self.gemini_model = None
    
    def _ensure_table_exists(self):
        """Create invoices table if it doesn't exist"""
        if not self.bq_client:
            return
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        
        schema = [
            bigquery.SchemaField("invoice_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("invoice_number", "STRING"),
            bigquery.SchemaField("vendor_name", "STRING"),
            bigquery.SchemaField("vendor_id", "STRING"),
            bigquery.SchemaField("amount", "FLOAT64"),
            bigquery.SchemaField("currency", "STRING"),
            bigquery.SchemaField("tax_amount", "FLOAT64"),
            bigquery.SchemaField("subtotal", "FLOAT64"),
            bigquery.SchemaField("invoice_date", "DATE"),
            bigquery.SchemaField("due_date", "DATE"),
            bigquery.SchemaField("scheduled_date", "DATE"),
            bigquery.SchemaField("payment_type", "STRING"),
            bigquery.SchemaField("payment_status", "STRING"),
            bigquery.SchemaField("category", "STRING"),
            bigquery.SchemaField("gl_code", "STRING"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("line_items", "STRING"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("approval_status", "STRING"),
            bigquery.SchemaField("approved_by", "STRING"),
            bigquery.SchemaField("approved_at", "TIMESTAMP"),
            bigquery.SchemaField("rejected_by", "STRING"),
            bigquery.SchemaField("rejected_at", "TIMESTAMP"),
            bigquery.SchemaField("rejection_reason", "STRING"),
            bigquery.SchemaField("source", "STRING"),
            bigquery.SchemaField("original_filename", "STRING"),
            bigquery.SchemaField("gcs_path", "STRING"),
            bigquery.SchemaField("extraction_confidence", "FLOAT64"),
            bigquery.SchemaField("extraction_method", "STRING"),
            bigquery.SchemaField("raw_extraction", "STRING"),
            bigquery.SchemaField("user_email", "STRING"),
            bigquery.SchemaField("tenant_id", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ]
        
        try:
            table = bigquery.Table(table_id, schema=schema)
            table = self.bq_client.create_table(table, exists_ok=True)
            logger.info(f"Table {table_id} ready")
        except Exception as e:
            logger.error(f"Table creation error: {e}")

    def parse_invoice(self, file_content: bytes, filename: str, user_email: str) -> Dict[str, Any]:
        """Parse a single invoice PDF using 4-layer hybrid approach"""
        invoice_id = f"INV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        try:
            gcs_path = self._upload_to_gcs(file_content, filename, user_email)
            doc_ai_result = self._extract_with_document_ai(file_content, filename)
            rag_context = self._get_rag_context(doc_ai_result)
            gemini_result = self._semantic_extraction(doc_ai_result, rag_context)
            validated_result = self._validate_extraction(gemini_result, doc_ai_result)
            self._store_invoice(invoice_id, validated_result, gcs_path, user_email, filename)
            
            return {
                'status': 'success',
                'invoice_id': invoice_id,
                'extracted_data': validated_result,
                'gcs_path': gcs_path,
                'confidence': validated_result.get('confidence', 0.0)
            }
        except Exception as e:
            logger.error(f"Invoice parsing failed: {e}")
            return {'status': 'error', 'error': str(e), 'invoice_id': invoice_id}
    
    def parse_invoices_bulk(self, files: List[tuple], user_email: str) -> Dict[str, Any]:
        """Parse multiple invoices"""
        results = []
        for file_content, filename in files:
            result = self.parse_invoice(file_content, filename, user_email)
            results.append({
                'filename': filename,
                'status': result.get('status'),
                'invoice_id': result.get('invoice_id'),
                'vendor_name': result.get('extracted_data', {}).get('vendor_name'),
                'amount': result.get('extracted_data', {}).get('amount'),
                'error': result.get('error')
            })
        
        successful = sum(1 for r in results if r['status'] == 'success')
        return {
            'status': 'success',
            'total': len(files),
            'processed': successful,
            'failed': len(files) - successful,
            'results': results
        }
    
    def _upload_to_gcs(self, file_content: bytes, filename: str, user_email: str) -> str:
        """Upload invoice to GCS"""
        if not self.storage_client:
            raise Exception("GCS not initialized")
        
        date_path = datetime.now().strftime('%Y/%m/%d')
        safe_email = user_email.replace('@', '_at_').replace('.', '_')
        gcs_path = f"invoices/{safe_email}/{date_path}/{filename}"
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(file_content, content_type='application/pdf')
        return gcs_path
    
    def _extract_with_document_ai(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Layer 1: Document AI extraction"""
        if not self.doc_ai_client or not self.PROCESSOR_ID:
            return {}
        
        try:
            mime_type = 'application/pdf'
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                mime_type = 'image/png' if filename.lower().endswith('.png') else 'image/jpeg'
            
            processor_name = self.doc_ai_client.processor_path(
                self.PROJECT_ID, self.LOCATION, self.PROCESSOR_ID
            )
            
            raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)
            request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
            result = self.doc_ai_client.process_document(request=request)
            document = result.document
            
            extracted = {'text': document.text, 'entities': {}}
            for entity in document.entities:
                if entity.type_ not in extracted['entities']:
                    extracted['entities'][entity.type_] = []
                extracted['entities'][entity.type_].append({
                    'value': entity.mention_text,
                    'confidence': entity.confidence
                })
            
            return extracted
        except Exception as e:
            logger.error(f"Document AI error: {e}")
            return {}
    
    def _get_rag_context(self, doc_ai_result: Dict) -> Dict[str, Any]:
        """Layer 2: Get historical context"""
        vendor_hint = None
        if 'entities' in doc_ai_result:
            suppliers = doc_ai_result['entities'].get('supplier_name', [])
            if suppliers:
                vendor_hint = suppliers[0].get('value')
        
        if not vendor_hint or not self.bq_client:
            return {}
        
        try:
            query = f"""
                SELECT vendor_name, category, payment_type
                FROM `{self.PROJECT_ID}.{self.DATASET_ID}.invoices`
                WHERE LOWER(vendor_name) LIKE LOWER('%{vendor_hint[:20]}%')
                ORDER BY created_at DESC LIMIT 5
            """
            results = list(self.bq_client.query(query).result())
            if results:
                return {
                    'typical_category': results[0].get('category'),
                    'typical_payment_type': results[0].get('payment_type')
                }
        except Exception as e:
            logger.warning(f"RAG lookup failed: {e}")
        
        return {}
    
    def _semantic_extraction(self, doc_ai_result: Dict, rag_context: Dict) -> Dict[str, Any]:
        """Layer 3: Gemini semantic extraction"""
        if not self.gemini_model:
            return self._fallback_extraction(doc_ai_result)
        
        doc_text = doc_ai_result.get('text', '')[:8000]
        rag_info = f"Historical: Category={rag_context.get('typical_category')}, Payment={rag_context.get('typical_payment_type')}" if rag_context else ""
        
        prompt = f"""Extract invoice data from this document. {rag_info}

DOCUMENT:
{doc_text}

Return JSON with: vendor_name, invoice_number, invoice_date (YYYY-MM-DD), due_date, amount, subtotal, tax_amount, currency, description, line_items, category, confidence (0-1).

Return ONLY valid JSON."""

        try:
            response = self.gemini_model.generate_content(prompt)
            result_text = response.text
            
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            return json.loads(result_text.strip())
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            return self._fallback_extraction(doc_ai_result)
    
    def _fallback_extraction(self, doc_ai_result: Dict) -> Dict[str, Any]:
        """Fallback extraction from Document AI"""
        entities = doc_ai_result.get('entities', {})
        return {
            'vendor_name': self._get_first_entity(entities, 'supplier_name'),
            'invoice_number': self._get_first_entity(entities, 'invoice_id'),
            'invoice_date': self._get_first_entity(entities, 'invoice_date'),
            'due_date': self._get_first_entity(entities, 'due_date'),
            'amount': self._parse_amount(self._get_first_entity(entities, 'total_amount')),
            'currency': self._get_first_entity(entities, 'currency') or 'USD',
            'confidence': 0.5
        }
    
    def _get_first_entity(self, entities: Dict, key: str) -> Optional[str]:
        values = entities.get(key, [])
        return values[0].get('value') if values else None
    
    def _parse_amount(self, amount_str: Optional[str]) -> Optional[float]:
        if not amount_str:
            return None
        try:
            cleaned = amount_str.replace('$', '').replace('€', '').replace('£', '').replace(',', '')
            return float(cleaned.strip())
        except:
            return None
    
    def _validate_extraction(self, gemini_result: Dict, doc_ai_result: Dict) -> Dict[str, Any]:
        """Layer 4: Validation"""
        validated = gemini_result.copy()
        
        subtotal = gemini_result.get('subtotal')
        tax = gemini_result.get('tax_amount')
        total = gemini_result.get('amount')
        
        if subtotal and tax and total:
            if abs((subtotal + tax) - total) > 0.01:
                validated['validation_warning'] = 'Math verification failed'
                validated['confidence'] = min(validated.get('confidence', 1.0), 0.7)
        
        if not validated.get('vendor_name'):
            validated['vendor_name'] = 'Unknown Vendor'
            validated['confidence'] = min(validated.get('confidence', 1.0), 0.5)
        
        if not validated.get('amount'):
            validated['amount'] = 0.0
            validated['confidence'] = min(validated.get('confidence', 1.0), 0.5)
        
        return validated
    
    def _store_invoice(self, invoice_id: str, data: Dict, gcs_path: str, 
                       user_email: str, filename: str):
        """Store invoice in BigQuery"""
        if not self.bq_client:
            return
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        
        row = {
            'invoice_id': invoice_id,
            'invoice_number': data.get('invoice_number'),
            'vendor_name': data.get('vendor_name'),
            'amount': data.get('amount'),
            'currency': data.get('currency', 'USD'),
            'tax_amount': data.get('tax_amount'),
            'subtotal': data.get('subtotal'),
            'invoice_date': data.get('invoice_date'),
            'due_date': data.get('due_date'),
            'description': data.get('description'),
            'category': data.get('category'),
            'line_items': json.dumps(data.get('line_items', [])),
            'status': 'pending',
            'payment_status': 'pending',
            'source': 'upload',
            'original_filename': filename,
            'gcs_path': gcs_path,
            'extraction_confidence': data.get('confidence', 0.0),
            'extraction_method': '4-layer-hybrid',
            'raw_extraction': json.dumps(data),
            'user_email': user_email,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        errors = self.bq_client.insert_rows_json(table_id, [row])
        if errors:
            logger.error(f"BigQuery insert errors: {errors}")

    def list_invoices(self, user_email: str = None, page: int = 1, limit: int = 50,
                      status: str = None, payment_type: str = None, currency: str = None,
                      date_from: str = None, date_to: str = None, search: str = '',
                      sort_by: str = 'created_at', sort_order: str = 'desc') -> Dict[str, Any]:
        """Get paginated list of invoices"""
        if not self.bq_client:
            return {'invoices': [], 'pagination': {}, 'summary': {}}
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        offset = (page - 1) * limit
        
        where_clauses = []
        if user_email:
            where_clauses.append(f"user_email = '{user_email}'")
        if status:
            where_clauses.append(f"status = '{status}'")
        if payment_type:
            where_clauses.append(f"payment_type = '{payment_type}'")
        if currency:
            where_clauses.append(f"currency = '{currency}'")
        if date_from:
            where_clauses.append(f"invoice_date >= '{date_from}'")
        if date_to:
            where_clauses.append(f"invoice_date <= '{date_to}'")
        if search:
            where_clauses.append(f"(LOWER(vendor_name) LIKE LOWER('%{search}%') OR LOWER(invoice_number) LIKE LOWER('%{search}%'))")
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        valid_sorts = ['created_at', 'invoice_date', 'amount', 'vendor_name', 'status']
        sort_by = sort_by if sort_by in valid_sorts else 'created_at'
        sort_order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        
        query = f"""
            SELECT * FROM `{table_id}`
            {where_sql}
            ORDER BY {sort_by} {sort_order}
            LIMIT {limit} OFFSET {offset}
        """
        
        count_query = f"SELECT COUNT(*) as total FROM `{table_id}` {where_sql}"
        
        try:
            invoices = [dict(row) for row in self.bq_client.query(query).result()]
            total = list(self.bq_client.query(count_query).result())[0]['total']
            
            summary = self._get_summary_stats(user_email)
            
            return {
                'invoices': invoices,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit
                },
                'summary': summary
            }
        except Exception as e:
            logger.error(f"List invoices error: {e}")
            return {'invoices': [], 'pagination': {}, 'summary': {}}
    
    def _get_summary_stats(self, user_email: str = None) -> Dict[str, Any]:
        """Get summary statistics"""
        if not self.bq_client:
            return {}
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        user_filter = f"WHERE user_email = '{user_email}'" if user_email else ""
        
        query = f"""
            SELECT
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as total_pending,
                SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) as total_due,
                COUNT(CASE WHEN status = 'pending' AND due_date < CURRENT_DATE() THEN 1 END) as overdue,
                COUNT(CASE WHEN status = 'pending' AND approval_status IS NULL THEN 1 END) as awaiting_approval,
                SUM(CASE WHEN status = 'paid' AND EXTRACT(MONTH FROM updated_at) = EXTRACT(MONTH FROM CURRENT_DATE()) THEN amount ELSE 0 END) as paid_this_month,
                COUNT(CASE WHEN scheduled_date IS NOT NULL AND status = 'approved' THEN 1 END) as scheduled
            FROM `{table_id}`
            {user_filter}
        """
        
        try:
            result = list(self.bq_client.query(query).result())[0]
            return dict(result)
        except Exception as e:
            logger.error(f"Summary stats error: {e}")
            return {}
    
    def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Get single invoice by ID"""
        if not self.bq_client:
            return None
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        query = f"SELECT * FROM `{table_id}` WHERE invoice_id = @invoice_id"
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)]
        )
        
        result = list(self.bq_client.query(query, job_config=job_config).result())
        return dict(result[0]) if result else None
    
    def update_invoice(self, invoice_id: str, data: Dict, user_email: str) -> Dict[str, Any]:
        """Update invoice fields"""
        if not self.bq_client:
            return {'status': 'error', 'message': 'Database not available'}
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        
        allowed_fields = ['vendor_name', 'invoice_number', 'amount', 'currency', 
                          'invoice_date', 'due_date', 'description', 'category',
                          'payment_type', 'scheduled_date']
        
        set_clauses = []
        for field in allowed_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    set_clauses.append(f"{field} = '{value}'")
                elif value is None:
                    set_clauses.append(f"{field} = NULL")
                else:
                    set_clauses.append(f"{field} = {value}")
        
        if not set_clauses:
            return {'status': 'error', 'message': 'No valid fields to update'}
        
        set_clauses.append(f"updated_at = CURRENT_TIMESTAMP()")
        
        query = f"""
            UPDATE `{table_id}`
            SET {', '.join(set_clauses)}
            WHERE invoice_id = '{invoice_id}'
        """
        
        try:
            self.bq_client.query(query).result()
            return {'status': 'success', 'message': 'Invoice updated', 'invoice_id': invoice_id}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def approve_invoice(self, invoice_id: str, user_email: str, 
                        scheduled_date: str = None, notes: str = None) -> Dict[str, Any]:
        """Approve invoice for payment"""
        if not self.bq_client:
            return {'status': 'error', 'message': 'Database not available'}
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        
        scheduled_sql = f", scheduled_date = '{scheduled_date}'" if scheduled_date else ""
        
        query = f"""
            UPDATE `{table_id}`
            SET status = 'approved',
                approval_status = 'approved',
                approved_by = '{user_email}',
                approved_at = CURRENT_TIMESTAMP(),
                updated_at = CURRENT_TIMESTAMP()
                {scheduled_sql}
            WHERE invoice_id = '{invoice_id}'
        """
        
        try:
            self.bq_client.query(query).result()
            return {
                'status': 'success',
                'message': 'Invoice approved',
                'invoice_id': invoice_id,
                'approved_by': user_email,
                'approved_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def reject_invoice(self, invoice_id: str, user_email: str, reason: str) -> Dict[str, Any]:
        """Reject invoice"""
        if not self.bq_client:
            return {'status': 'error', 'message': 'Database not available'}
        
        table_id = f"{self.PROJECT_ID}.{self.DATASET_ID}.invoices"
        
        query = f"""
            UPDATE `{table_id}`
            SET status = 'rejected',
                approval_status = 'rejected',
                rejected_by = '{user_email}',
                rejected_at = CURRENT_TIMESTAMP(),
                rejection_reason = '{reason}',
                updated_at = CURRENT_TIMESTAMP()
            WHERE invoice_id = '{invoice_id}'
        """
        
        try:
            self.bq_client.query(query).result()
            return {
                'status': 'success',
                'message': 'Invoice rejected',
                'invoice_id': invoice_id,
                'rejected_by': user_email,
                'rejected_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def get_download_url(self, invoice_id: str) -> Optional[str]:
        """Get signed URL for PDF download"""
        if not self.bq_client or not self.storage_client:
            return None
        
        invoice = self.get_invoice(invoice_id)
        if not invoice or not invoice.get('gcs_path'):
            return None
        
        try:
            blob = self.bucket.blob(invoice['gcs_path'])
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET"
            )
            return url
        except Exception as e:
            logger.error(f"Download URL error: {e}")
            return None
    
    def get_summary(self, user_email: str = None) -> Dict[str, Any]:
        """Get comprehensive invoice summary"""
        return {
            'status': 'success',
            'summary': self._get_summary_stats(user_email)
        }
