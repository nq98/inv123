import os
import json
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, stream_with_context
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from invoice_processor import InvoiceProcessor
from services.gmail_service import GmailService
from services.token_storage import SecureTokenStorage
from services.bigquery_service import BigQueryService
from services.vendor_csv_mapper import VendorCSVMapper
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
    Upload and process an invoice file
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
    
    result = get_processor().process_local_file(filepath, mime_type)
    
    os.remove(filepath)
    
    return jsonify(result), 200

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
            
            # Stage 1: Smart pre-filtering with Gmail queries
            stage1_msg = '\n🔍 STAGE 1: Smart Pre-Filtering (Gmail semantic search)'
            yield f"data: {json.dumps({'type': 'status', 'message': stage1_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': 'Filtering by: invoice keywords, billing senders, PDF attachments...'})}\n\n"
            
            messages = gmail_service.search_invoice_emails(service, 500, days)  # Get up to 500 for filtering
            
            total_found = len(messages)
            yield f"data: {json.dumps({'type': 'success', 'message': f'📧 Found {total_found} emails matching invoice patterns'})}\n\n"
            
            # Stage 2: AI Classification - which are REAL invoices
            stage2_msg = '\n🧠 STAGE 2: AI Semantic Classification'
            yield f"data: {json.dumps({'type': 'status', 'message': stage2_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Analyzing {total_found} emails to identify real invoices/receipts...'})}\n\n"
            
            processor = get_processor()
            classified_invoices = []
            non_invoices = []
            
            # First pass: Classify all emails
            for idx, msg_ref in enumerate(messages, 1):
                try:
                    message = gmail_service.get_message_details(service, msg_ref['id'])
                    
                    if not message:
                        non_invoices.append(('Failed to fetch', None))
                        continue
                    
                    metadata = gmail_service.get_email_metadata(message)
                    subject = metadata.get('subject', 'No subject')
                    
                    is_invoice, confidence, reasoning = gmail_service.classify_invoice_email(metadata)
                    
                    if is_invoice and confidence >= 0.3:
                        classified_invoices.append((message, metadata, confidence))
                        invoice_msg = f'  ✓ [{idx}/{total_found}] Invoice: "{subject[:60]}..."'
                        yield f"data: {json.dumps({'type': 'success', 'message': invoice_msg})}\n\n"
                    else:
                        non_invoices.append((subject, reasoning))
                        skip_msg = f'  ⚠️ [{idx}/{total_found}] Skipped: "{subject[:60]}..." - {reasoning}'
                        yield f"data: {json.dumps({'type': 'warning', 'message': skip_msg})}\n\n"
                    
                except Exception as e:
                    non_invoices.append((f'Error: {str(e)}', None))
                    yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ Error classifying email: {str(e)[:60]}'})}\n\n"
            
            invoice_count = len(classified_invoices)
            non_invoice_count = len(non_invoices)
            
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
        
        # Store CSV content in session for step 2
        session['pending_csv_content'] = csv_content.decode('utf-8-sig')
        session['pending_csv_filename'] = file.filename
        
        return jsonify({
            'success': True,
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
        # Get CSV content from session
        csv_content = session.get('pending_csv_content')
        filename = session.get('pending_csv_filename', 'upload.csv')
        
        if not csv_content:
            return jsonify({'error': 'No pending CSV upload found. Please analyze CSV first.'}), 400
        
        # Get mapping from request (user can override AI mapping if needed)
        data = request.get_json()
        column_mapping = data.get('columnMapping')
        source_system = data.get('sourceSystem', 'csv_upload')
        
        if not column_mapping:
            return jsonify({'error': 'Column mapping required'}), 400
        
        # Transform CSV data using mapping
        csv_mapper = get_csv_mapper()
        transformed_vendors = csv_mapper.transform_csv_data(csv_content, {
            'columnMapping': column_mapping,
            'sourceSystemGuess': source_system
        })
        
        if not transformed_vendors:
            return jsonify({'error': 'No valid vendor records found in CSV'}), 400
        
        # Initialize BigQuery and ensure table exists
        bq_service = get_bigquery_service()
        bq_service.ensure_table_schema()
        
        # Merge vendors into BigQuery
        merge_result = bq_service.merge_vendors(transformed_vendors, source_system)
        
        # Clear session
        session.pop('pending_csv_content', None)
        session.pop('pending_csv_filename', None)
        
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
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
