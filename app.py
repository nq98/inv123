import os
import json
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, stream_with_context
from werkzeug.utils import secure_filename
from invoice_processor import InvoiceProcessor
from services.gmail_service import GmailService
from services.token_storage import SecureTokenStorage
from config import config

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

_processor = None
_gmail_service = None
_token_storage = None

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

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'gif'}
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
        auth_url, state = gmail_service.get_authorization_url()
        
        session['oauth_state'] = state
        
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
        credentials = gmail_service.exchange_code_for_token(code)
        
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

@app.route('/api/ap-automation/gmail/import/stream', methods=['POST'])
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
            
            data = json.loads(request.data.decode('utf-8')) if request.data else {}
            max_results = data.get('max_results', 20)
            
            yield f"data: {json.dumps({'type': 'status', 'message': '✓ Gmail Scanner Initialized'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Lookback period: Last 30 days'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': 'Authenticating with Gmail...'})}\n\n"
            
            gmail_service = get_gmail_service()
            service = gmail_service.build_service(credentials)
            
            email = credentials.get('email', 'Gmail account')
            yield f"data: {json.dumps({'type': 'success', 'message': f'Connected to {email}'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': f'Counting total emails from the last 30 days...'})}\n\n"
            
            messages = gmail_service.search_invoice_emails(service, max_results)
            
            total_found = len(messages)
            yield f"data: {json.dumps({'type': 'success', 'message': f'Found {total_found} total emails in the last 30 days'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': 'Filtering for potential invoices...'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Found {total_found} potential invoice emails out of {total_found} total'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': f'Analyzing {total_found} potential invoice emails (filtered from {total_found} total)...'})}\n\n"
            
            processor = get_processor()
            processed_count = 0
            imported_count = 0
            skipped_count = 0
            
            for idx, msg_ref in enumerate(messages, 1):
                try:
                    yield f"data: {json.dumps({'type': 'analyzing', 'message': f'Analyzing email {idx} of {total_found}'})}\n\n"
                    
                    message = gmail_service.get_message_details(service, msg_ref['id'])
                    
                    if not message:
                        yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ Failed to fetch message'})}\n\n"
                        skipped_count += 1
                        continue
                    
                    metadata = gmail_service.get_email_metadata(message)
                    subject = metadata.get('subject', 'No subject')
                    subject_msg = f'  Subject: "{subject}"'
                    
                    yield f"data: {json.dumps({'type': 'info', 'message': subject_msg})}\n\n"
                    
                    is_invoice, confidence, reasoning = gmail_service.classify_invoice_email(metadata)
                    
                    if not is_invoice or confidence < 0.3:
                        yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ Not an invoice - {reasoning}'})}\n\n"
                        skipped_count += 1
                        continue
                    
                    sender = metadata.get('from', 'Unknown sender')
                    yield f"data: {json.dumps({'type': 'success', 'message': f'  ✓ Invoice detected: {sender}'})}\n\n"
                    
                    attachments = gmail_service.extract_attachments(service, message)
                    
                    if not attachments:
                        yield f"data: {json.dumps({'type': 'warning', 'message': f'  ⚠️ No PDF attachments found'})}\n\n"
                        skipped_count += 1
                        continue
                    
                    for filename, file_data in attachments:
                        yield f"data: {json.dumps({'type': 'status', 'message': f'  Downloading: {filename}'})}\n\n"
                        
                        secure_name = secure_filename(filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        yield f"data: {json.dumps({'type': 'status', 'message': f'  Processing through AI pipeline...'})}\n\n"
                        
                        invoice_result = processor.process_local_file(filepath, 'application/pdf')
                        
                        os.remove(filepath)
                        
                        vendor = invoice_result.get('validated', {}).get('vendor', {}).get('name', 'Unknown')
                        total = invoice_result.get('validated', {}).get('totals', {}).get('total', 0)
                        currency = invoice_result.get('validated', {}).get('currency', '')
                        
                        yield f"data: {json.dumps({'type': 'success', 'message': f'  ✓ Extracted: {vendor} | {currency} {total}'})}\n\n"
                        imported_count += 1
                    
                    processed_count += 1
                    
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'  ❌ Error: {str(e)}'})}\n\n"
            
            complete_msg = '\n✅ Import Complete!'
            yield f"data: {json.dumps({'type': 'success', 'message': complete_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Total processed: {processed_count}'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Invoices imported: {imported_count}'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'Emails skipped: {skipped_count}'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'imported': imported_count, 'skipped': skipped_count, 'total': total_found})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Import failed: {str(e)}'})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
