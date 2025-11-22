import os
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, stream_with_context
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from invoice_processor import InvoiceProcessor
from services.gmail_service import GmailService
from services.token_storage import SecureTokenStorage
from services.bigquery_service import BigQueryService
from services.vendor_csv_mapper import VendorCSVMapper
from services.vendor_matcher import VendorMatcher
from services.vertex_search_service import VertexSearchService
from services.gemini_service import GeminiService
from config import config

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'payouts_invoice_static_secret_key_2024_production')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['PERMANENT_SESSION_LIFETIME'] = 300

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

csv_uploads = {}

def cleanup_old_uploads():
    """Remove CSV uploads older than 1 hour to prevent memory leaks"""
    cutoff = datetime.now() - timedelta(hours=1)
    to_delete = [uid for uid, data in csv_uploads.items() 
                 if data['timestamp'] < cutoff]
    for uid in to_delete:
        del csv_uploads[uid]
    if to_delete:
        print(f"🧹 Cleaned up {len(to_delete)} old CSV uploads")

_processor = None
_gmail_service = None
_token_storage = None
_bigquery_service = None
_csv_mapper = None

def get_processor():
    """Lazy initialization of InvoiceProcessor to avoid blocking app startup"""
    global _processor
    if _processor is None:
        _processor = InvoiceProcessor()
    return _processor

def get_gmail_service():
    """Lazy initialization of GmailService"""
    global _gmail_service
    if _gmail_service is None:
        _gmail_service = GmailService()
    return _gmail_service

def get_token_storage():
    """Lazy initialization of SecureTokenStorage"""
    global _token_storage
    if _token_storage is None:
        _token_storage = SecureTokenStorage()
    return _token_storage

def get_bigquery_service():
    """Lazy initialization of BigQueryService"""
    global _bigquery_service
    if _bigquery_service is None:
        _bigquery_service = BigQueryService()
    return _bigquery_service

def get_csv_mapper():
    """Lazy initialization of VendorCSVMapper"""
    global _csv_mapper
    if _csv_mapper is None:
        _csv_mapper = VendorCSVMapper()
    return _csv_mapper

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'gif'}
ALLOWED_CSV_EXTENSIONS = {'csv', 'txt'}
MIME_TYPES = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'tiff': 'image/tiff',
    'gif': 'image/gif'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_csv_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_CSV_EXTENSIONS

@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    response.cache_control.no_cache = True
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 0
    return response

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/api', methods=['GET'])
def api_info():
    return jsonify({
        'service': 'Enterprise Invoice Extraction API',
        'version': '1.0.0',
        'architecture': '3-layer hybrid (Document AI + Vertex Search + Gemini)',
        'endpoints': {
            'POST /process': 'Process invoice from GCS URI',
            'POST /upload': 'Upload and process invoice file',
            'GET /health': 'Health check'
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'project_id': config.GOOGLE_CLOUD_PROJECT_ID,
        'document_ai_processor': config.DOCAI_PROCESSOR_ID,
        'vertex_search_datastore': config.VERTEX_SEARCH_DATA_STORE_ID
    })

@app.route('/process', methods=['POST'])
def process_invoice():
    """
    Process an invoice from GCS URI
    
    Request body:
    {
        "gcs_uri": "gs://bucket/invoice.pdf",
        "mime_type": "application/pdf"
    }
    """
    data = request.get_json()
    
    if not data or 'gcs_uri' not in data:
        return jsonify({'error': 'gcs_uri is required'}), 400
    
    gcs_uri = data['gcs_uri']
    mime_type = data.get('mime_type', 'application/pdf')
    
    result = get_processor().process_invoice(gcs_uri, mime_type)
    
    return jsonify(result), 200

@app.route('/upload', methods=['POST'])
def upload_invoice():
    """
    Upload and process an invoice file with automatic vendor matching
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if not file.filename or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    ext = filename.rsplit('.', 1)[1].lower()
    mime_type = MIME_TYPES.get(ext, 'application/pdf')
    
    # FIX ISSUE 1: Cache processor instance to prevent re-entrancy deadlock
    processor = get_processor()
    result = processor.process_local_file(filepath, mime_type)
    
    os.remove(filepath)
    
    # AUTOMATIC VENDOR MATCHING: Trigger vendor matching if invoice extraction succeeded
    vendor_match_result = None
    if result.get('status') == 'completed' and 'validated_data' in result:
        validated_data = result.get('validated_data', {})
        vendor_data = validated_data.get('vendor', {})
        
        # Extract vendor information from invoice
        vendor_name = vendor_data.get('name', '')
        tax_id = vendor_data.get('taxId', '') or vendor_data.get('tax_id', '')
        address = vendor_data.get('address', '')
        country = vendor_data.get('country', '')
        email = vendor_data.get('email', '')
        phone = vendor_data.get('phone', '')
        
        # Extract email domain if email is available
        email_domain = ''
        if email and '@' in email:
            email_domain = '@' + email.split('@')[1]
        
        # Only run vendor matching if we have at least a vendor name
        if vendor_name and vendor_name != 'Unknown':
            print(f"\n{'='*60}")
            print(f"AUTOMATIC VENDOR MATCHING: {vendor_name}")
            print(f"{'='*60}\n")
            
            try:
                # FIX ISSUE 3: Add logging for troubleshooting
                print(f"⚡ Starting automatic vendor matching for vendor: {vendor_name}")
                
                # FIX ISSUE 1: Reuse cached processor instance (no re-entrancy)
                bigquery_service = get_bigquery_service()
                
                # Create VendorMatcher instance
                matcher = VendorMatcher(
                    bigquery_service=bigquery_service,
                    vertex_search_service=processor.vertex_search_service,
                    gemini_service=processor.gemini_service
                )
                
                # Prepare vendor data for matching
                matching_input = {
                    'vendor_name': vendor_name,
                    'tax_id': tax_id or 'Unknown',
                    'address': address or '',
                    'email_domain': email_domain or '',
                    'phone': phone or '',
                    'country': country or ''
                }
                
                # Run vendor matching
                match_result = matcher.match_vendor(matching_input)
                
                # Build vendor match response with invoice and database vendor data
                verdict = match_result.get('verdict')
                vendor_id = match_result.get('vendor_id')
                
                vendor_match_result = {
                    'verdict': verdict,
                    'vendor_id': vendor_id,
                    'confidence': match_result.get('confidence'),
                    'reasoning': match_result.get('reasoning'),
                    'method': match_result.get('method'),
                    'risk_analysis': match_result.get('risk_analysis'),
                    'database_updates': match_result.get('database_updates', {}),
                    'parent_child_logic': match_result.get('parent_child_logic', {
                        'is_subsidiary': False,
                        'parent_company_detected': None
                    }),
                    'invoice_vendor': {
                        'name': vendor_name,
                        'tax_id': tax_id or 'Unknown',
                        'address': address or 'Unknown',
                        'country': country or 'Unknown',
                        'email': email or 'Unknown',
                        'phone': phone or 'Unknown'
                    },
                    'database_vendor': None  # FIX ISSUE 1: Always initialize, will be populated if MATCH
                }
                
                # If match found, fetch database vendor details
                if verdict == 'MATCH' and vendor_id:
                    try:
                        vendor_id = match_result['vendor_id']
                        print(f"✓ Fetching database vendor details for {vendor_id}...")
                        
                        # Query BigQuery for vendor details
                        query = f"""
                        SELECT 
                            vendor_id,
                            global_name,
                            normalized_name,
                            emails,
                            domains,
                            countries,
                            custom_attributes
                        FROM `{bigquery_service.full_table_id}`
                        WHERE vendor_id = @vendor_id
                        LIMIT 1
                        """
                        
                        from google.cloud import bigquery as bq
                        job_config = bq.QueryJobConfig(
                            query_parameters=[
                                bq.ScalarQueryParameter("vendor_id", "STRING", vendor_id)
                            ]
                        )
                        
                        results = list(bigquery_service.client.query(query, job_config=job_config).result())
                        
                        if results:
                            row = results[0]
                            
                            # Parse custom attributes if it's a JSON string
                            custom_attrs = row.custom_attributes
                            if isinstance(custom_attrs, str):
                                try:
                                    custom_attrs = json.loads(custom_attrs)
                                except:
                                    custom_attrs = {}
                            
                            # Extract addresses from custom attributes
                            addresses = []
                            if custom_attrs and custom_attrs.get('address'):
                                addresses.append(custom_attrs['address'])
                            
                            vendor_match_result['database_vendor'] = {
                                'vendor_id': row.vendor_id,
                                'name': row.global_name,
                                'normalized_name': row.normalized_name or '',
                                'tax_id': custom_attrs.get('tax_id', 'Unknown') if custom_attrs else 'Unknown',
                                'addresses': addresses,
                                'countries': row.countries if isinstance(row.countries, list) else [],
                                'emails': row.emails if isinstance(row.emails, list) else [],
                                'domains': row.domains if isinstance(row.domains, list) else []
                            }
                        
                    except Exception as e:
                        print(f"⚠️ Warning: Could not fetch database vendor details: {e}")
                        vendor_match_result['database_vendor_error'] = str(e)
                
                print(f"✓ Vendor matching complete: {match_result.get('verdict')}")
                
            except Exception as e:
                # FIX ISSUE 3: Add explicit error logging
                print(f"❌ Vendor matching failed: {e}")
                
                # FIX ISSUE 2: Complete error fallback with all required fields
                vendor_match_result = {
                    'verdict': 'ERROR',
                    'vendor_id': None,
                    'confidence': 0.0,
                    'method': 'ERROR',
                    'reasoning': f'Vendor matching error: {str(e)}',
                    'risk_analysis': 'HIGH',
                    'database_updates': {},
                    'parent_child_logic': {
                        'is_subsidiary': False,
                        'parent_company_detected': None
                    },
                    'invoice_vendor': {
                        'name': vendor_name,
                        'tax_id': tax_id or 'Unknown',
                        'address': address or 'Unknown',
                        'country': country or 'Unknown',
                        'email': email or 'Unknown',
                        'phone': phone or 'Unknown'
                    },
                    'database_vendor': None,
                    'error': str(e)
                }
        else:
            print("ℹ️ Skipping vendor matching: No vendor name extracted from invoice")
    
    # Add vendor matching result to response
    if vendor_match_result:
        result['vendor_match'] = vendor_match_result
    
    return jsonify(result), 200

@app.route('/upload/stream', methods=['GET'])
def upload_invoice_stream():
    """
    Upload and process an invoice file with SSE progress tracking (7 steps)
    Requires: file parameter in multipart form data
    Query params: filename (base64 encoded temp filename for retrieval)
    """
    def generate():
        try:
            # Get filename from query params (uploaded via separate endpoint)
            import base64
            encoded_filename = request.args.get('filename')
            if not encoded_filename:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No filename provided'})}\n\n"
                return
            
            filename = base64.b64decode(encoded_filename.encode()).decode()
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            if not os.path.exists(filepath):
                yield f"data: {json.dumps({'type': 'error', 'message': 'File not found'})}\n\n"
                return
            
            ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
            mime_type = MIME_TYPES.get(ext, 'application/pdf')
            
            # Step 0: Initialize
            yield f"data: {json.dumps({'type': 'progress', 'step': 0, 'total_steps': 7, 'message': 'Initializing invoice processing...'})}\n\n"
            
            # Step 1: Upload to Cloud Storage
            yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 7, 'message': 'Uploading to Cloud Storage...', 'details': f'File: {filename}'})}\n\n"
            
            from google.cloud import storage
            from google.oauth2 import service_account
            
            credentials = service_account.Credentials.from_service_account_file(config.VERTEX_RUNNER_SA_PATH)
            storage_client = storage.Client(project=config.GOOGLE_CLOUD_PROJECT_ID, credentials=credentials)
            bucket = storage_client.bucket(config.GCS_INPUT_BUCKET)
            blob = bucket.blob(f"uploads/{filename}")
            blob.upload_from_filename(filepath, content_type=mime_type)
            gcs_uri = f"gs://{config.GCS_INPUT_BUCKET}/uploads/{filename}"
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 7, 'message': 'Uploaded to Cloud Storage', 'details': 'File uploaded successfully', 'completed': True})}\n\n"
            
            # Get processor instance
            processor = get_processor()
            
            # Step 2: Document AI Extraction
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 7, 'message': 'Layer 1: Document AI Extraction...'})}\n\n"
            
            document = processor.doc_ai_service.process_document(gcs_uri, mime_type)
            raw_text = processor.doc_ai_service.get_raw_text(document)
            extracted_entities = processor.doc_ai_service.extract_entities(document)
            text_length = len(raw_text)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 7, 'message': 'Document AI Extraction Complete', 'details': f'Extracted {text_length} characters', 'completed': True})}\n\n"
            
            # Step 3: Multi-Currency Detection
            yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 7, 'message': 'Layer 1.5: Multi-Currency Detection...'})}\n\n"
            
            currency_context = processor.multi_currency_detector.analyze_invoice_currencies(raw_text, extracted_entities)
            currencies_found = currency_context.get('currency_symbols_found', [])
            currency_str = currencies_found[0] if currencies_found else 'USD'
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 7, 'message': 'Multi-Currency Detection Complete', 'details': f'Currency: {currency_str}', 'completed': True})}\n\n"
            
            # Step 4: Vertex Search RAG
            yield f"data: {json.dumps({'type': 'progress', 'step': 4, 'total_steps': 7, 'message': 'Layer 2: Vertex AI Search RAG...'})}\n\n"
            
            from utils import extract_vendor_name
            vendor_name = extract_vendor_name(extracted_entities)
            vendor_search_results = []
            if vendor_name:
                vendor_search_results = processor.vertex_search_service.search_vendor(vendor_name)
            matches_count = len(vendor_search_results)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 4, 'total_steps': 7, 'message': 'Vertex Search Complete', 'details': f'Found {matches_count} vendor matches', 'completed': True})}\n\n"
            
            # Get full RAG context
            vendor_context = processor.vertex_search_service.format_context(vendor_search_results)
            invoice_extraction_results = processor.vertex_search_service.search_similar_invoices(raw_text, vendor_name, limit=3)
            invoice_extraction_context = processor.vertex_search_service.format_invoice_extraction_context(invoice_extraction_results)
            rag_context = f"{vendor_context}\n\n{invoice_extraction_context}"
            
            # Step 5: Gemini Validation
            yield f"data: {json.dumps({'type': 'progress', 'step': 5, 'total_steps': 7, 'message': 'Layer 3: Gemini Validation...'})}\n\n"
            
            validated_data = processor.gemini_service.validate_invoice(gcs_uri, raw_text, extracted_entities, rag_context, currency_context=currency_context)
            
            invoice_num = validated_data.get('invoiceNumber', 'N/A')
            vendor = validated_data.get('vendor', {}).get('name', 'N/A')
            total = validated_data.get('totals', {}).get('total', 'N/A')
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 5, 'total_steps': 7, 'message': 'Gemini Validation Complete', 'details': f'Invoice #{invoice_num} from {vendor}', 'completed': True})}\n\n"
            
            # Step 6: Automatic Vendor Matching
            yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Running automatic vendor matching...'})}\n\n"
            
            vendor_match_result = None
            if validated_data.get('vendor', {}).get('name'):
                try:
                    bigquery_service = get_bigquery_service()
                    matcher = VendorMatcher(bigquery_service=bigquery_service, vertex_search_service=processor.vertex_search_service, gemini_service=processor.gemini_service)
                    
                    vendor_data = validated_data.get('vendor', {})
                    tax_id = vendor_data.get('taxId', '') or vendor_data.get('tax_id', '')
                    email = vendor_data.get('email', '')
                    email_domain = '@' + email.split('@')[1] if email and '@' in email else ''
                    
                    matching_input = {
                        'vendor_name': vendor_data.get('name', ''),
                        'tax_id': tax_id or 'Unknown',
                        'address': vendor_data.get('address', ''),
                        'email_domain': email_domain,
                        'phone': vendor_data.get('phone', ''),
                        'country': vendor_data.get('country', '')
                    }
                    
                    match_result = matcher.match_vendor(matching_input)
                    verdict = match_result.get('verdict', 'ERROR')
                    vendor_match_result = match_result
                    
                    yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Vendor Matching Complete', 'details': f'Verdict: {verdict}', 'completed': True})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Vendor Matching Failed', 'details': str(e), 'error': True})}\n\n"
                    vendor_match_result = {'verdict': 'ERROR', 'error': str(e)}
            else:
                yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Vendor Matching Skipped', 'details': 'No vendor name found', 'completed': True})}\n\n"
            
            # Step 7: Complete
            yield f"data: {json.dumps({'type': 'progress', 'step': 7, 'total_steps': 7, 'message': 'Processing Complete!', 'completed': True})}\n\n"
            
            # Send final result
            result = {
                'gcs_uri': gcs_uri,
                'status': 'completed',
                'validated_data': validated_data,
                'layers': {
                    'layer1_document_ai': {'status': 'success', 'text_length': text_length},
                    'layer1_5_multi_currency': {'status': 'success', 'currency': currency_str},
                    'layer2_vertex_search': {'status': 'success', 'matches_found': matches_count},
                    'layer3_gemini': {'status': 'success'}
                }
            }
            
            if vendor_match_result:
                result['vendor_match'] = vendor_match_result
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
            except:
                pass
            
            yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Processing failed: {str(e)}'})}\n\n"
    
    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/api/vendor/match', methods=['POST'])
def match_vendor():
    """
    Match invoice vendor data to database vendor using semantic reasoning
    
    3-Step Matching Pipeline:
    - Step 0: Hard Tax ID match (100% confidence)
    - Step 1: Semantic search (Vertex AI Search RAG)
    - Step 2: Supreme Judge decision (Gemini 1.5 Pro)
    
    Request body:
    {
        "vendor_name": "Amazon AWS",
        "tax_id": "US123456789",
        "address": "410 Terry Ave N, Seattle, WA",
        "email_domain": "@aws.com",
        "phone": "+1-206-555-0100",
        "country": "US"
    }
    
    Response:
    {
        "success": true,
        "result": {
            "verdict": "MATCH" | "NEW_VENDOR" | "AMBIGUOUS",
            "vendor_id": "vendor_abc123",
            "confidence": 0.95,
            "reasoning": "Matched via corporate domain + fuzzy name",
            "risk_analysis": "NONE" | "LOW" | "HIGH",
            "database_updates": {...},
            "parent_child_logic": {...},
            "method": "TAX_ID_HARD_MATCH" | "SEMANTIC_MATCH" | "NEW_VENDOR"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        # Validate required fields
        if not data.get('vendor_name'):
            return jsonify({
                'success': False,
                'error': 'vendor_name is required'
            }), 400
        
        # Initialize services for VendorMatcher
        processor = get_processor()
        bigquery_service = get_bigquery_service()
        
        # Create VendorMatcher instance
        matcher = VendorMatcher(
            bigquery_service=bigquery_service,
            vertex_search_service=processor.vertex_search_service,
            gemini_service=processor.gemini_service
        )
        
        # Run matching pipeline
        result = matcher.match_vendor(data)
        
        return jsonify({
            'success': True,
            'result': result
        }), 200
        
    except Exception as e:
        print(f"❌ Vendor matching error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vendor/match/stream', methods=['POST'])
def match_vendor_stream():
    """
    Match invoice vendor to database with SSE progress tracking (4 steps)
    """
    def generate():
        try:
            data = request.get_json()
            
            if not data or not data.get('vendor_name'):
                yield f"data: {json.dumps({'type': 'error', 'message': 'vendor_name is required'})}\n\n"
                return
            
            # Step 0: Hard Tax ID Match
            yield f"data: {json.dumps({'type': 'progress', 'step': 0, 'total_steps': 4, 'message': 'Step 0: Hard Tax ID Match...'})}\n\n"
            
            processor = get_processor()
            bigquery_service = get_bigquery_service()
            matcher = VendorMatcher(bigquery_service=bigquery_service, vertex_search_service=processor.vertex_search_service, gemini_service=processor.gemini_service)
            
            tax_id = data.get('tax_id', '')
            hard_match_result = None
            if tax_id and tax_id != 'Unknown':
                hard_match = matcher._hard_match_by_tax_id(tax_id)
                if hard_match:
                    matched_vendor = hard_match['vendor_name']
                    yield f"data: {json.dumps({'type': 'progress', 'step': 0, 'total_steps': 4, 'message': 'Hard Tax ID match found!', 'details': f'Matched vendor: {matched_vendor}', 'completed': True})}\n\n"
                    result = {
                        "verdict": "MATCH",
                        "vendor_id": hard_match['vendor_id'],
                        "confidence": 1.0,
                        "reasoning": f"Exact Tax ID match: {tax_id}",
                        "risk_analysis": "NONE",
                        "database_updates": {},
                        "parent_child_logic": {"is_subsidiary": False, "parent_company_detected": None},
                        "method": "TAX_ID_HARD_MATCH"
                    }
                    yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
                    return
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 0, 'total_steps': 4, 'message': 'No hard Tax ID match', 'details': 'Proceeding to semantic search', 'completed': True})}\n\n"
            
            # Step 1: Semantic Search
            yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 4, 'message': 'Step 1: Semantic Search...'})}\n\n"
            
            vendor_name = data.get('vendor_name', '')
            country = data.get('country')
            candidates = matcher._get_semantic_candidates(vendor_name, country, top_k=5)
            candidates_count = len(candidates)
            
            if not candidates:
                yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 4, 'message': 'No candidates found', 'details': 'This appears to be a new vendor', 'completed': True})}\n\n"
                result = {
                    "verdict": "NEW_VENDOR",
                    "vendor_id": None,
                    "confidence": 0.0,
                    "reasoning": f"No similar vendors found in database for '{vendor_name}'",
                    "risk_analysis": "LOW",
                    "database_updates": {},
                    "parent_child_logic": {"is_subsidiary": False, "parent_company_detected": None},
                    "method": "NEW_VENDOR"
                }
                yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
                return
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 4, 'message': 'Semantic search complete', 'details': f'Found {candidates_count} candidates', 'completed': True})}\n\n"
            
            # Step 2: Supreme Judge Decision
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 4, 'message': 'Step 2: Supreme Judge AI Reasoning...'})}\n\n"
            
            judge_decision = matcher._supreme_judge_decision(data, candidates)
            verdict = judge_decision.get('verdict', 'NEW_VENDOR')
            confidence = judge_decision.get('confidence', 0.0)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 4, 'message': 'Supreme Judge decision complete', 'details': f'Verdict: {verdict} ({int(confidence*100)}% confidence)', 'completed': True})}\n\n"
            
            # Step 3: Fetch Database Vendor Details (if MATCH)
            if verdict == 'MATCH' and judge_decision.get('vendor_id'):
                yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 4, 'message': 'Step 3: Fetching vendor details from BigQuery...'})}\n\n"
                
                vendor_id = judge_decision['vendor_id']
                query = f"""
                SELECT vendor_id, global_name, normalized_name, emails, domains, countries, custom_attributes
                FROM `{bigquery_service.full_table_id}`
                WHERE vendor_id = @vendor_id
                LIMIT 1
                """
                
                from google.cloud import bigquery as bq
                job_config = bq.QueryJobConfig(query_parameters=[bq.ScalarQueryParameter("vendor_id", "STRING", vendor_id)])
                results = list(bigquery_service.client.query(query, job_config=job_config).result())
                
                if results:
                    yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 4, 'message': 'Database vendor details fetched', 'details': f'Retrieved {results[0].global_name}', 'completed': True})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 4, 'message': 'Database vendor details not found', 'completed': True})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 4, 'message': 'Skipped (no match to fetch)', 'completed': True})}\n\n"
            
            # Step 4: Complete
            yield f"data: {json.dumps({'type': 'progress', 'step': 4, 'total_steps': 4, 'message': 'Vendor matching complete!', 'completed': True})}\n\n"
            
            # Add method to result
            if judge_decision['verdict'] == 'MATCH':
                judge_decision['method'] = 'SEMANTIC_MATCH'
            elif judge_decision['verdict'] == 'NEW_VENDOR':
                judge_decision['method'] = 'NEW_VENDOR'
            else:
                judge_decision['method'] = 'SEMANTIC_MATCH'
            
            yield f"data: {json.dumps({'type': 'complete', 'result': judge_decision})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Vendor matching failed: {str(e)}'})}\n\n"
    
    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/api/ap-automation/gmail/auth', methods=['GET'])
def gmail_auth():
    """Initiate Gmail OAuth flow"""
    try:
        gmail_service = get_gmail_service()
        redirect_uri = request.host_url.rstrip('/') + '/api/ap-automation/gmail/callback'
        auth_url, state = gmail_service.get_authorization_url(redirect_uri=redirect_uri)
        
        session['oauth_state'] = state
        session['oauth_redirect_uri'] = redirect_uri
        
        return redirect(auth_url)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ap-automation/gmail/callback', methods=['GET'])
def gmail_callback():
    """Handle Gmail OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code:
            return jsonify({'error': 'No authorization code received'}), 400
        
        stored_state = session.get('oauth_state')
        if state != stored_state:
            return jsonify({'error': 'State mismatch - possible CSRF attack'}), 400
        
        gmail_service = get_gmail_service()
        redirect_uri = session.get('oauth_redirect_uri') or (request.host_url.rstrip('/') + '/api/ap-automation/gmail/callback')
        credentials = gmail_service.exchange_code_for_token(code, redirect_uri=redirect_uri)
        
        # Store credentials securely server-side
        token_storage = get_token_storage()
        session_token = token_storage.store_credentials(credentials)
        
        # Only store opaque session token in cookie (NOT the actual credentials)
        session['gmail_session_token'] = session_token
        
        return redirect('/?gmail_connected=true')
    except Exception as e:
        return jsonify({'error': f'OAuth callback failed: {str(e)}'}), 500

@app.route('/api/ap-automation/gmail/status', methods=['GET'])
def gmail_status():
    """Check if Gmail is connected"""
    session_token = session.get('gmail_session_token')
    
    if not session_token:
        return jsonify({'connected': False})
    
    # Verify token exists in secure storage
    token_storage = get_token_storage()
    credentials = token_storage.get_credentials(session_token)
    
    connected = credentials is not None
    return jsonify({'connected': connected})

@app.route('/api/ap-automation/gmail/disconnect', methods=['POST'])
def gmail_disconnect():
    """Disconnect Gmail"""
    session_token = session.get('gmail_session_token')
    
    if session_token:
        # Delete credentials from secure storage
        token_storage = get_token_storage()
        token_storage.delete_credentials(session_token)
        
        # Remove session token from cookie
        session.pop('gmail_session_token')
    
    return jsonify({'status': 'disconnected'})

@app.route('/api/ap-automation/gmail/import/stream', methods=['GET'])
def gmail_import_stream():
    """
    Stream real-time progress of Gmail invoice import using Server-Sent Events
    """
    def generate():
        try:
            session_token = session.get('gmail_session_token')
            
            if not session_token:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Gmail not connected'})}\n\n"
                return
            
            token_storage = get_token_storage()
            credentials = token_storage.get_credentials(session_token)
            
            if not credentials:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Gmail session expired'})}\n\n"
                return
            
            days = request.args.get('days', 7, type=int)
            
            time_label = f'{days} days' if days < 9999 else 'all time'
            
            yield f"data: {json.dumps({'type': 'status', 'message': '🚀 Gmail Invoice Scanner Initialized'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'⏰ Time range: Last {time_label}'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': 'Authenticating with Gmail API...'})}\n\n"
            
            gmail_service = get_gmail_service()
            service = gmail_service.build_service(credentials)
            
            email = credentials.get('email', 'Gmail account')
            yield f"data: {json.dumps({'type': 'success', 'message': f'Connected to {email}'})}\n\n"
            
            # Stage 1: Broad Net Gmail Query
            stage1_msg = '\n🔍 STAGE 1: Broad Net Gmail Query (Multi-Language)'
            yield f"data: {json.dumps({'type': 'status', 'message': stage1_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': 'Casting wide net: English, Hebrew, French, German, Spanish keywords...'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': 'Excluding: newsletters, webinars, invitations...'})}\n\n"
            
            messages = gmail_service.search_invoice_emails(service, 500, days)  # Get up to 500 for filtering
            
            total_found = len(messages)
            yield f"data: {json.dumps({'type': 'success', 'message': f'📧 Found {total_found} emails matching broad financial patterns'})}\n\n"
            
            # Stage 2: Elite Gatekeeper AI Filter
            stage2_msg = '\n🧠 STAGE 2: Elite Gatekeeper AI Filter (Gemini 1.5 Flash)'
            yield f"data: {json.dumps({'type': 'status', 'message': stage2_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'AI analyzing {total_found} emails for semantic context...'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': 'Filtering: Marketing spam, newsletters, logistics, false positives...'})}\n\n"
            
            processor = get_processor()
            gemini_service = processor.gemini_service
            classified_invoices = []
            non_invoices = []
            
            # First pass: Classify all emails using AI Gatekeeper
            for idx, msg_ref in enumerate(messages, 1):
                try:
                    message = gmail_service.get_message_details(service, msg_ref['id'])
                    
                    if not message:
                        non_invoices.append(('Failed to fetch', None))
                        continue
                    
                    metadata = gmail_service.get_email_metadata(message)
                    subject = metadata.get('subject', 'No subject')
                    
                    is_invoice, confidence, reasoning = gmail_service.classify_invoice_email(metadata, gemini_service)
                    
                    if is_invoice and confidence >= 0.3:
                        classified_invoices.append((message, metadata, confidence))
                        invoice_msg = f'  ✓ [{idx}/{total_found}] KEEP: "{subject[:50]}..." ({reasoning[:80]})'
                        yield f"data: {json.dumps({'type': 'success', 'message': invoice_msg})}\n\n"
                    else:
                        non_invoices.append((subject, reasoning))
                        skip_msg = f'  ✗ [{idx}/{total_found}] KILL: "{subject[:50]}..." ({reasoning[:80]})'
                        yield f"data: {json.dumps({'type': 'warning', 'message': skip_msg})}\n\n"
                    
                except Exception as e:
                    non_invoices.append((f'Error: {str(e)}', None))
                    yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ Error classifying email: {str(e)[:60]}'})}\n\n"
            
            invoice_count = len(classified_invoices)
            non_invoice_count = len(non_invoices)
            
            # Calculate filtering funnel statistics
            after_language_filter_percent = round((total_found / max(total_found, 1)) * 100, 1)
            after_ai_filter_percent = round((invoice_count / max(total_found, 1)) * 100, 1)
            
            # Send structured filtering funnel event
            funnel_stats = {
                'timeRange': time_label,
                'totalEmails': total_found,
                'afterLanguageFilter': total_found,
                'languageFilterPercent': after_language_filter_percent,
                'afterAIFilter': invoice_count,
                'aiFilterPercent': after_ai_filter_percent,
                'invoicesFound': 0,  # Will be updated after extraction
                'invoicesPercent': 0.0
            }
            yield f"data: {json.dumps({'type': 'funnel_stats', 'stats': funnel_stats})}\n\n"
            
            filter_results_msg = '\n📊 FILTERING RESULTS:'
            yield f"data: {json.dumps({'type': 'success', 'message': filter_results_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'  • Total emails scanned: {total_found}'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'  • Relevant (potential invoices): {total_found}'})}\n\n"
            yield f"data: {json.dumps({'type': 'success', 'message': f'  • Clean invoices/receipts: {invoice_count} ✓'})}\n\n"
            yield f"data: {json.dumps({'type': 'warning', 'message': f'  • Filtered out (not invoices): {non_invoice_count}'})}\n\n"
            
            # Stage 3: Extract invoice data through 3-layer AI
            stage3_msg = f'\n🤖 STAGE 3: Deep AI Extraction ({invoice_count} invoices)'
            yield f"data: {json.dumps({'type': 'status', 'message': stage3_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': '3-Layer Pipeline: Document AI OCR → Vertex Search RAG → Gemini Semantic'})}\n\n"
            
            imported_invoices = []
            extraction_failures = []
            
            for idx, (message, metadata, confidence) in enumerate(classified_invoices, 1):
                try:
                    subject = metadata.get('subject', 'No subject')
                    sender = metadata.get('from', 'Unknown')
                    
                    processing_msg = f'\n[{idx}/{invoice_count}] Processing: "{subject[:50]}..."'
                    yield f"data: {json.dumps({'type': 'analyzing', 'message': processing_msg})}\n\n"
                    yield f"data: {json.dumps({'type': 'info', 'message': f'  From: {sender}'})}\n\n"
                    
                    # Extract attachments
                    attachments = gmail_service.extract_attachments(service, message)
                    
                    # Extract links
                    links = gmail_service.extract_links_from_body(message)
                    
                    if not attachments and not links:
                        yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ No PDFs or download links found'})}\n\n"
                        extraction_failures.append(subject)
                        continue
                    
                    # Process attachments
                    for filename, file_data in attachments:
                        yield f"data: {json.dumps({'type': 'status', 'message': f'  📎 Attachment: {filename}'})}\n\n"
                        
                        secure_name = secure_filename(filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        yield f"data: {json.dumps({'type': 'status', 'message': '    → Layer 1: Document AI OCR...'})}\n\n"
                        yield f"data: {json.dumps({'type': 'status', 'message': '    → Layer 2: Vertex Search RAG...'})}\n\n"
                        yield f"data: {json.dumps({'type': 'status', 'message': '    → Layer 3: Gemini Semantic Extraction...'})}\n\n"
                        yield f"data: {json.dumps({'type': 'keepalive', 'message': '⏳ Processing invoice (this may take 30-60 seconds)...'})}\n\n"
                        
                        try:
                            invoice_result = processor.process_local_file(filepath, 'application/pdf')
                        except Exception as proc_error:
                            os.remove(filepath)
                            yield f"data: {json.dumps({'type': 'error', 'message': f'  ❌ Processing failed: {str(proc_error)[:100]}'})}\n\n"
                            extraction_failures.append(subject)
                            continue
                        
                        os.remove(filepath)
                        
                        validated = invoice_result.get('validated_data', {})
                        vendor_data = validated.get('vendor', {})
                        totals = validated.get('totals', {})
                        
                        vendor = vendor_data.get('name', 'Unknown')
                        total = totals.get('total', 0)
                        currency = validated.get('currency', 'USD')
                        invoice_num = validated.get('invoiceNumber', 'N/A')
                        
                        if vendor and vendor != 'Unknown' and total and total > 0:
                            yield f"data: {json.dumps({'type': 'success', 'message': f'  ✅ SUCCESS: {vendor} | Invoice #{invoice_num} | {currency} {total}'})}\n\n"
                            
                            imported_invoices.append({
                                'subject': subject,
                                'sender': sender,
                                'date': metadata.get('date'),
                                'vendor': vendor,
                                'invoice_number': invoice_num,
                                'total': total,
                                'currency': currency,
                                'line_items': validated.get('lineItems', []),
                                'full_data': validated
                            })
                        else:
                            yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ Extraction incomplete: Vendor={vendor}, Total={total}'})}\n\n"
                            extraction_failures.append(subject)
                    
                    # Process links
                    for link_url in links[:2]:  # Limit to first 2 links per email
                        yield f"data: {json.dumps({'type': 'status', 'message': f'  🔗 Downloading from link...'})}\n\n"
                        
                        pdf_result = gmail_service.download_pdf_from_link(link_url)
                        
                        if pdf_result:
                            filename, file_data = pdf_result
                            yield f"data: {json.dumps({'type': 'success', 'message': f'  ✓ Downloaded: {filename}'})}\n\n"
                            
                            secure_name = secure_filename(filename)
                            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                            
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            
                            yield f"data: {json.dumps({'type': 'status', 'message': '    → Processing through 3-layer AI...'})}\n\n"
                            yield f"data: {json.dumps({'type': 'keepalive', 'message': '⏳ Processing downloaded file...'})}\n\n"
                            
                            try:
                                invoice_result = processor.process_local_file(filepath, 'application/pdf')
                            except Exception as link_proc_error:
                                os.remove(filepath)
                                yield f"data: {json.dumps({'type': 'error', 'message': f'  ❌ Link processing failed: {str(link_proc_error)[:100]}'})}\n\n"
                                continue
                            
                            os.remove(filepath)
                            
                            validated = invoice_result.get('validated_data', {})
                            vendor = validated.get('vendor', {}).get('name', 'Unknown')
                            invoice_num = validated.get('invoiceNumber', 'N/A')
                            totals = validated.get('totals', {})
                            total = totals.get('total', 0)
                            currency = validated.get('currency', 'USD')
                            
                            if vendor and vendor != 'Unknown' and total and total > 0:
                                yield f"data: {json.dumps({'type': 'success', 'message': f'  ✅ Extracted from link: {vendor} | Invoice #{invoice_num} | {currency} {total}'})}\n\n"
                                imported_invoices.append({
                                    'subject': subject,
                                    'sender': sender,
                                    'date': metadata.get('date'),
                                    'vendor': vendor,
                                    'invoice_number': invoice_num,
                                    'total': total,
                                    'currency': currency,
                                    'line_items': validated.get('lineItems', []),
                                    'full_data': validated
                                })
                    
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'  ❌ Extraction error: {str(e)}'})}\n\n"
                    extraction_failures.append(subject)
            
            imported_count = len(imported_invoices)
            failed_extraction = len(extraction_failures)
            
            complete_msg = '\n✅ Import Complete!'
            yield f"data: {json.dumps({'type': 'success', 'message': complete_msg})}\n\n"
            final_results_msg = '\n📈 FINAL RESULTS:'
            yield f"data: {json.dumps({'type': 'info', 'message': final_results_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'  • Emails scanned: {total_found}'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'  • Clean invoices found: {invoice_count}'})}\n\n"
            yield f"data: {json.dumps({'type': 'success', 'message': f'  • Successfully extracted: {imported_count} ✓'})}\n\n"
            yield f"data: {json.dumps({'type': 'warning', 'message': f'  • Extraction failed: {failed_extraction}'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'imported': imported_count, 'skipped': non_invoice_count, 'total': total_found, 'invoices': imported_invoices})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Import failed: {str(e)}'})}\n\n"
    
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/api/ap-automation/gmail/import', methods=['POST'])
def gmail_import():
    """
    Import invoices from Gmail
    
    Request body:
    {
        "max_results": 20,
        "days_back": 30
    }
    """
    try:
        session_token = session.get('gmail_session_token')
        
        if not session_token:
            return jsonify({'error': 'Gmail not connected. Please authenticate first.'}), 401
        
        # Retrieve credentials from secure server-side storage
        token_storage = get_token_storage()
        credentials = token_storage.get_credentials(session_token)
        
        if not credentials:
            return jsonify({'error': 'Gmail session expired. Please reconnect.'}), 401
        data = request.get_json() or {}
        max_results = data.get('max_results', 20)
        
        gmail_service = get_gmail_service()
        service = gmail_service.build_service(credentials)
        
        messages = gmail_service.search_invoice_emails(service, max_results)
        
        results = {
            'total_found': len(messages),
            'processed': [],
            'skipped': [],
            'errors': []
        }
        
        processor = get_processor()
        
        for msg_ref in messages:
            try:
                message = gmail_service.get_message_details(service, msg_ref['id'])
                
                if not message:
                    results['skipped'].append({
                        'id': msg_ref['id'],
                        'reason': 'Failed to fetch message'
                    })
                    continue
                
                metadata = gmail_service.get_email_metadata(message)
                
                is_invoice, confidence, reasoning = gmail_service.classify_invoice_email(metadata)
                
                if not is_invoice or confidence < 0.3:
                    results['skipped'].append({
                        'id': msg_ref['id'],
                        'subject': metadata.get('subject'),
                        'reason': f'Not an invoice (confidence: {confidence:.2f})',
                        'reasoning': reasoning
                    })
                    continue
                
                attachments = gmail_service.extract_attachments(service, message)
                
                if not attachments:
                    results['skipped'].append({
                        'id': msg_ref['id'],
                        'subject': metadata.get('subject'),
                        'reason': 'No PDF attachments found'
                    })
                    continue
                
                for filename, file_data in attachments:
                    try:
                        secure_name = secure_filename(filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        invoice_result = processor.process_local_file(filepath, 'application/pdf')
                        
                        os.remove(filepath)
                        
                        results['processed'].append({
                            'gmail_id': msg_ref['id'],
                            'subject': metadata.get('subject'),
                            'from': metadata.get('from'),
                            'date': metadata.get('date'),
                            'filename': filename,
                            'confidence': confidence,
                            'extraction': invoice_result
                        })
                        
                    except Exception as e:
                        results['errors'].append({
                            'gmail_id': msg_ref['id'],
                            'filename': filename,
                            'error': str(e)
                        })
            
            except Exception as e:
                results['errors'].append({
                    'gmail_id': msg_ref.get('id', 'unknown'),
                    'error': str(e)
                })
        
        return jsonify(results), 200
        
    except Exception as e:
        return jsonify({'error': f'Gmail import failed: {str(e)}'}), 500

# ===== VENDOR CSV UPLOAD ENDPOINTS =====

@app.route('/api/vendors/csv/analyze', methods=['POST'])
def analyze_vendor_csv():
    """
    Analyze uploaded CSV file and generate AI-powered column mapping
    Step 1 of 2-step CSV import process
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_csv_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only CSV files allowed.'}), 400
        
        # Read CSV content
        csv_content = file.read()
        
        # Get AI-powered column mapping
        csv_mapper = get_csv_mapper()
        analysis_result = csv_mapper.analyze_csv_headers(csv_content, file.filename)
        
        if not analysis_result.get('success'):
            return jsonify({'error': analysis_result.get('error', 'Analysis failed')}), 400
        
        # Generate unique upload ID
        upload_id = str(uuid.uuid4())
        
        # Store CSV content and analysis server-side (not in session)
        csv_uploads[upload_id] = {
            'csv_content': csv_content.decode('utf-8-sig'),
            'filename': file.filename,
            'analysis': analysis_result['mapping'],
            'headers': analysis_result['headers'],
            'timestamp': datetime.now()
        }
        
        # Cleanup old uploads to prevent memory leaks
        cleanup_old_uploads()
        
        print(f"✓ CSV analysis complete. Upload ID: {upload_id} ({len(csv_uploads)} uploads in memory)")
        
        return jsonify({
            'success': True,
            'uploadId': upload_id,
            'filename': file.filename,
            'analysis': analysis_result['mapping'],
            'headers': analysis_result['headers'],
            'sampleRows': analysis_result['sampleRows']
        }), 200
        
    except Exception as e:
        print(f"❌ Error analyzing CSV: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vendors/csv/import', methods=['POST'])
def import_vendor_csv():
    """
    Import vendor CSV data using AI-generated mapping
    Step 2 of 2-step CSV import process
    """
    try:
        # Get request data
        data = request.get_json()
        upload_id = data.get('uploadId')
        column_mapping = data.get('columnMapping')
        source_system = data.get('sourceSystem', 'csv_upload')
        
        if not upload_id:
            return jsonify({'error': 'Upload ID required. Please analyze CSV first.'}), 400
        
        if not column_mapping:
            return jsonify({'error': 'Column mapping required'}), 400
        
        # Retrieve CSV data from server-side storage
        upload_data = csv_uploads.get(upload_id)
        if not upload_data:
            return jsonify({'error': 'No pending CSV upload found. Upload may have expired. Please analyze CSV again.'}), 400
        
        csv_content = upload_data['csv_content']
        filename = upload_data['filename']
        original_analysis = upload_data['analysis']
        original_headers = upload_data['headers']
        
        print(f"✓ Retrieved CSV upload {upload_id} for import")
        
        # Transform CSV data using mapping
        csv_mapper = get_csv_mapper()
        transformed_vendors = csv_mapper.transform_csv_data(csv_content, {
            'columnMapping': column_mapping,
            'sourceSystemGuess': source_system
        })
        
        if not transformed_vendors:
            # Clean up upload data even on error
            csv_uploads.pop(upload_id, None)
            return jsonify({'error': 'No valid vendor records found in CSV'}), 400
        
        # Initialize BigQuery and ensure table exists
        bq_service = get_bigquery_service()
        bq_service.ensure_table_schema()
        
        # Merge vendors into BigQuery
        merge_result = bq_service.merge_vendors(transformed_vendors, source_system)
        
        # VERTEX AI SEARCH RAG FEEDBACK LOOP: Store mapping for future learning
        import_success = len(merge_result.get('errors', [])) == 0
        
        if import_success:
            try:
                if original_headers and original_analysis:
                    csv_mapper.store_mapping_to_knowledge_base(
                        headers=original_headers,
                        column_mapping=original_analysis,
                        success=True
                    )
                    print("✓ Stored successful mapping to Vertex AI Search knowledge base")
            except Exception as e:
                print(f"⚠️ Could not store mapping to knowledge base: {e}")
        
        # Clean up server-side storage after successful import
        csv_uploads.pop(upload_id, None)
        print(f"🧹 Cleaned up upload {upload_id} ({len(csv_uploads)} uploads remaining)")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'vendorsProcessed': len(transformed_vendors),
            'inserted': merge_result['inserted'],
            'updated': merge_result['updated'],
            'errors': merge_result['errors']
        }), 200
        
    except Exception as e:
        print(f"❌ Error importing CSV: {e}")
        # Clean up upload data on error if upload_id is available
        try:
            upload_id = request.get_json().get('uploadId') if request.get_json() else None
            if upload_id:
                csv_uploads.pop(upload_id, None)
        except:
            pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/vendors/csv/import/stream', methods=['POST'])
def import_vendor_csv_stream():
    """
    Import vendor CSV with SSE progress tracking (7 steps)
    """
    def generate():
        try:
            data = request.get_json()
            upload_id = data.get('uploadId')
            column_mapping = data.get('columnMapping')
            source_system = data.get('sourceSystem', 'csv_upload')
            
            if not upload_id or not column_mapping:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Upload ID and column mapping required'})}\n\n"
                return
            
            # Retrieve CSV data
            upload_data = csv_uploads.get(upload_id)
            if not upload_data:
                yield f"data: {json.dumps({'type': 'error', 'message': 'CSV upload expired. Please analyze again.'})}\n\n"
                return
            
            csv_content = upload_data['csv_content']
            filename = upload_data['filename']
            original_headers = upload_data['headers']
            original_analysis = upload_data['analysis']
            
            # Step 1: Retrieved CSV file
            file_size = len(csv_content.encode('utf-8')) / (1024 * 1024)  # MB
            yield f"data: {json.dumps({'type': 'progress', 'step': 1, 'total_steps': 7, 'message': 'Retrieved CSV file', 'details': f'{filename} ({file_size:.2f} MB)', 'completed': True})}\n\n"
            
            # Step 2: AI analyzing columns
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 7, 'message': 'AI analyzing columns...'})}\n\n"
            
            column_count = len(original_headers) if original_headers else len(column_mapping)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 2, 'total_steps': 7, 'message': 'AI analysis complete', 'details': f'Analyzed {column_count} columns', 'completed': True})}\n\n"
            
            # Step 3: Mapping to schema
            yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 7, 'message': 'Mapping to vendor schema...'})}\n\n"
            
            mapped_fields = len([v for v in column_mapping.values() if v.get('targetField') and not v['targetField'].startswith('custom_attributes')])
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 3, 'total_steps': 7, 'message': 'Schema mapping complete', 'details': f'Mapped {mapped_fields} fields', 'completed': True})}\n\n"
            
            # Step 4: Transforming data
            yield f"data: {json.dumps({'type': 'progress', 'step': 4, 'total_steps': 7, 'message': 'Transforming CSV data...'})}\n\n"
            
            csv_mapper = get_csv_mapper()
            transformed_vendors = csv_mapper.transform_csv_data(csv_content, {
                'columnMapping': column_mapping,
                'sourceSystemGuess': source_system
            })
            
            if not transformed_vendors:
                csv_uploads.pop(upload_id, None)
                yield f"data: {json.dumps({'type': 'error', 'message': 'No valid vendor records found in CSV'})}\n\n"
                return
            
            row_count = len(transformed_vendors)
            yield f"data: {json.dumps({'type': 'progress', 'step': 4, 'total_steps': 7, 'message': 'Data transformation complete', 'details': f'Transformed {row_count} rows', 'completed': True})}\n\n"
            
            # Step 5: Uploading to BigQuery
            yield f"data: {json.dumps({'type': 'progress', 'step': 5, 'total_steps': 7, 'message': 'Uploading to BigQuery...'})}\n\n"
            
            bq_service = get_bigquery_service()
            bq_service.ensure_table_schema()
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 5, 'total_steps': 7, 'message': 'BigQuery upload complete', 'details': 'Data uploaded successfully', 'completed': True})}\n\n"
            
            # Step 6: Smart deduplication
            yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Running smart deduplication...'})}\n\n"
            
            merge_result = bq_service.merge_vendors(transformed_vendors, source_system)
            inserted = merge_result.get('inserted', 0)
            updated = merge_result.get('updated', 0)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 6, 'total_steps': 7, 'message': 'Deduplication complete', 'details': f'{inserted} new, {updated} updated', 'completed': True})}\n\n"
            
            # Store mapping to knowledge base
            import_success = len(merge_result.get('errors', [])) == 0
            if import_success and original_headers and original_analysis:
                try:
                    csv_mapper.store_mapping_to_knowledge_base(headers=original_headers, column_mapping=original_analysis, success=True)
                except Exception as e:
                    print(f"⚠️ Could not store mapping to knowledge base: {e}")
            
            # Step 7: Complete
            yield f"data: {json.dumps({'type': 'progress', 'step': 7, 'total_steps': 7, 'message': 'Import complete!', 'completed': True})}\n\n"
            
            # Clean up
            csv_uploads.pop(upload_id, None)
            
            # Send final result
            result = {
                'success': True,
                'filename': filename,
                'vendorsProcessed': len(transformed_vendors),
                'inserted': inserted,
                'updated': updated,
                'errors': merge_result.get('errors', [])
            }
            
            yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'CSV import failed: {str(e)}'})}\n\n"
            try:
                upload_id = request.get_json().get('uploadId') if request.get_json() else None
                if upload_id:
                    csv_uploads.pop(upload_id, None)
            except:
                pass
    
    return Response(stream_with_context(generate()), content_type='text/event-stream')

@app.route('/api/vendors/search', methods=['GET'])
def search_vendors():
    """Search vendors in BigQuery database by name"""
    try:
        query = request.args.get('q', '')
        limit = int(request.args.get('limit', 10))
        
        if not query:
            return jsonify({'vendors': []}), 200
        
        bq_service = get_bigquery_service()
        vendors = bq_service.search_vendor_by_name(query, limit)
        
        return jsonify({'vendors': vendors}), 200
        
    except Exception as e:
        print(f"❌ Error searching vendors: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vendors/list', methods=['GET'])
def list_vendors():
    """
    Get paginated list of all vendors from BigQuery
    
    Query parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20)
    
    Returns:
        {
            "vendors": [...],
            "total_count": int,
            "page": int,
            "limit": int,
            "total_pages": int
        }
    """
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # Validate parameters
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 20
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Get vendors from BigQuery
        bq_service = get_bigquery_service()
        result = bq_service.get_all_vendors(limit=limit, offset=offset)
        
        # Calculate total pages
        total_count = result['total_count']
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
        
        return jsonify({
            'vendors': result['vendors'],
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        }), 200
        
    except Exception as e:
        print(f"❌ Error listing vendors: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
