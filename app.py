import os
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, stream_with_context
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from google.cloud import bigquery
from invoice_processor import InvoiceProcessor
from services.gmail_service import GmailService
from services.token_storage import SecureTokenStorage
from services.bigquery_service import BigQueryService
from services.vendor_csv_mapper import VendorCSVMapper
from services.vendor_matcher import VendorMatcher
from services.vertex_search_service import VertexSearchService
from services.gemini_service import GeminiService
from services.semantic_entity_classifier import SemanticEntityClassifier
from services.agent_auth_service import require_agent_auth
from services.agent_search_service import AgentSearchService
from services.issue_detector import IssueDetector
from services.action_manager import ActionManager
from services.pdf_generator import PDFInvoiceGenerator
from services.invoice_composer import InvoiceComposer
from services.netsuite_service import NetSuiteService
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

def _parse_structured_evidence(structured_evidence, invoice_vendor, database_vendor, confidence):
    """
    Parse Gemini's structured evidence breakdown (AI-First approach)
    
    Args:
        structured_evidence: dict with Gemini's evidence_breakdown structure
        invoice_vendor: Invoice vendor data dict
        database_vendor: Database vendor data dict
        confidence: Overall confidence score (0.0-1.0)
    
    Returns:
        dict: Evidence breakdown with tiers and field-level analysis
    """
    evidence = {
        'gold_tier': [],
        'silver_tier': [],
        'bronze_tier': [],
        'total_confidence': round(confidence * 100, 1)
    }
    
    # Helper to get tier list
    def get_tier_list(tier_name):
        tier_map = {
            'GOLD': evidence['gold_tier'],
            'SILVER': evidence['silver_tier'],
            'BRONZE': evidence['bronze_tier']
        }
        return tier_map.get(tier_name, evidence['bronze_tier'])
    
    # Parse Email Domain (AI-First Semantic Classification)
    if 'email_domain' in structured_evidence:
        email_evidence = structured_evidence['email_domain']
        domain_type = email_evidence.get('domain_type', 'NOT_AVAILABLE')
        tier = email_evidence.get('tier', 'BRONZE')
        contribution = email_evidence.get('confidence_contribution', 0.0)
        reasoning = email_evidence.get('reasoning', 'No reasoning provided')
        
        if domain_type != 'NOT_AVAILABLE':
            tier_list = get_tier_list(tier)
            
            # Set icon based on domain type
            icon_map = {
                'CORPORATE_UNIQUE': '✅',
                'GENERIC_PROVIDER': '⚠️',
                'RESELLER': '🔄'
            }
            icon = icon_map.get(domain_type, '❓')
            
            inv_email = invoice_vendor.get('email', 'Unknown')
            db_email = database_vendor.get('email', 'Unknown') if database_vendor else 'Unknown'
            
            tier_list.append({
                'field': 'Email Domain',
                'matched': True,
                'invoice_value': inv_email,
                'database_value': db_email,
                'domain_type': domain_type,
                'reason': reasoning,
                'confidence_contribution': contribution,
                'icon': icon
            })
    
    # Parse Tax ID
    if 'tax_id' in structured_evidence:
        tax_evidence = structured_evidence['tax_id']
        tier = tax_evidence.get('tier', 'BRONZE')
        matched = tax_evidence.get('matched', False)
        contribution = tax_evidence.get('confidence_contribution', 0.0)
        reasoning = tax_evidence.get('reasoning', 'No reasoning provided')
        
        tier_list = get_tier_list(tier)
        inv_tax = invoice_vendor.get('tax_id', 'Unknown')
        db_tax = database_vendor.get('tax_id', 'Unknown') if database_vendor else 'Unknown'
        
        tier_list.append({
            'field': 'Tax ID',
            'matched': matched,
            'invoice_value': inv_tax,
            'database_value': db_tax,
            'reason': reasoning,
            'confidence_contribution': contribution,
            'icon': '✅' if matched else '❌'
        })
    
    # Parse Name
    if 'name' in structured_evidence:
        name_evidence = structured_evidence['name']
        tier = name_evidence.get('tier', 'BRONZE')
        matched = name_evidence.get('matched', False)
        contribution = name_evidence.get('confidence_contribution', 0.0)
        reasoning = name_evidence.get('reasoning', 'No reasoning provided')
        
        tier_list = get_tier_list(tier)
        inv_name = invoice_vendor.get('name', 'Unknown')
        db_name = database_vendor.get('name', 'Unknown') if database_vendor else 'Unknown'
        
        tier_list.append({
            'field': 'Name',
            'matched': matched,
            'invoice_value': inv_name,
            'database_value': db_name,
            'reason': reasoning,
            'confidence_contribution': contribution,
            'icon': '✅' if matched else '❌'
        })
    
    # Parse Address
    if 'address' in structured_evidence:
        addr_evidence = structured_evidence['address']
        tier = addr_evidence.get('tier', 'BRONZE')
        matched = addr_evidence.get('matched', False)
        contribution = addr_evidence.get('confidence_contribution', 0.0)
        reasoning = addr_evidence.get('reasoning', 'No reasoning provided')
        
        tier_list = get_tier_list(tier)
        inv_addr = invoice_vendor.get('address', 'Unknown')
        db_addr = database_vendor.get('address', 'Unknown') if database_vendor else 'Unknown'
        
        # Truncate long addresses for display
        inv_addr_display = inv_addr[:50] + '...' if len(inv_addr) > 50 else inv_addr
        db_addr_display = db_addr[:50] + '...' if len(db_addr) > 50 else db_addr
        
        tier_list.append({
            'field': 'Address',
            'matched': matched,
            'invoice_value': inv_addr_display,
            'database_value': db_addr_display,
            'reason': reasoning,
            'confidence_contribution': contribution,
            'icon': '✅' if matched else '❌'
        })
    
    # Parse Phone
    if 'phone' in structured_evidence:
        phone_evidence = structured_evidence['phone']
        tier = phone_evidence.get('tier', 'BRONZE')
        matched = phone_evidence.get('matched', False)
        contribution = phone_evidence.get('confidence_contribution', 0.0)
        reasoning = phone_evidence.get('reasoning', 'No reasoning provided')
        
        tier_list = get_tier_list(tier)
        inv_phone = invoice_vendor.get('phone', 'Unknown')
        db_phone = database_vendor.get('phone', 'Unknown') if database_vendor else 'Unknown'
        
        tier_list.append({
            'field': 'Phone',
            'matched': matched,
            'invoice_value': inv_phone,
            'database_value': db_phone,
            'reason': reasoning,
            'confidence_contribution': contribution,
            'icon': '✅' if matched else '❌'
        })
    
    return evidence

def parse_evidence_breakdown(reasoning, invoice_vendor, database_vendor, confidence, verdict, structured_evidence=None):
    """
    Parse Supreme Judge reasoning to generate evidence breakdown
    
    AI-FIRST: Prefers Gemini's structured evidence breakdown over fallback parsing.
    
    Args:
        reasoning: Supreme Judge reasoning text (fallback)
        invoice_vendor: Invoice vendor data dict
        database_vendor: Database vendor data dict
        confidence: Overall confidence score (0.0-1.0)
        verdict: Match verdict (MATCH, NEW_VENDOR, etc.)
        structured_evidence: Optional dict with Gemini's structured evidence breakdown
    
    Returns:
        dict: Evidence breakdown with tiers and field-level analysis
    """
    # PRIORITY 1: Use Gemini's structured evidence if available
    if structured_evidence:
        print("✅ Using Gemini's structured evidence breakdown (AI-First)")
        return _parse_structured_evidence(structured_evidence, invoice_vendor, database_vendor, confidence)
    
    # PRIORITY 2: Fallback to reasoning-based parsing (no hardcoded lists)
    if not reasoning:
        return None
    
    print("⚠️ Falling back to reasoning-based parsing (Gemini didn't return structured evidence)")
    reasoning_lower = reasoning.lower()
    
    # Initialize evidence structure
    evidence = {
        'gold_tier': [],
        'silver_tier': [],
        'bronze_tier': [],
        'total_confidence': round(confidence * 100, 1)
    }
    
    # Helper function to check if a field was mentioned and matched
    def check_field_match(field_keywords, field_name):
        for keyword in field_keywords:
            if keyword in reasoning_lower and ('match' in reasoning_lower or 'same' in reasoning_lower or 'identical' in reasoning_lower):
                return True
        return False
    
    # GOLD TIER EVIDENCE (Definitive Proof)
    # Tax ID Match
    if invoice_vendor.get('tax_id') and invoice_vendor['tax_id'] != 'Unknown':
        if check_field_match(['tax id', 'vat', 'ein', 'tax number'], 'Tax ID'):
            inv_tax = invoice_vendor.get('tax_id', 'Unknown')
            db_tax = database_vendor.get('tax_id', 'Unknown') if database_vendor else 'Unknown'
            evidence['gold_tier'].append({
                'field': 'Tax ID',
                'matched': True,
                'invoice_value': inv_tax,
                'database_value': db_tax,
                'confidence_contribution': 50.0,
                'icon': '✅'
            })
        elif database_vendor and database_vendor.get('tax_id'):
            evidence['bronze_tier'].append({
                'field': 'Tax ID',
                'matched': False,
                'reason': 'Not matched in reasoning',
                'confidence_contribution': 0.0,
                'icon': '❌'
            })
    else:
        evidence['bronze_tier'].append({
            'field': 'Tax ID',
            'matched': False,
            'reason': 'Unknown on both sides',
            'confidence_contribution': 0.0,
            'icon': '❌'
        })
    
    # Name Match
    if invoice_vendor.get('name') and invoice_vendor['name'] != 'Unknown':
        if check_field_match(['name', 'company name', 'vendor name'], 'Name'):
            inv_name = invoice_vendor.get('name', 'Unknown')
            db_name = database_vendor.get('name', 'Unknown') if database_vendor else 'Unknown'
            evidence['gold_tier'].append({
                'field': 'Name',
                'matched': True,
                'invoice_value': inv_name,
                'database_value': db_name,
                'confidence_contribution': 40.0,
                'icon': '✅'
            })
        elif verdict == 'NEW_VENDOR':
            evidence['bronze_tier'].append({
                'field': 'Name',
                'matched': False,
                'reason': 'New vendor - not in database',
                'confidence_contribution': 0.0,
                'icon': '❌'
            })
    
    # Address Match
    if invoice_vendor.get('address') and invoice_vendor['address'] != 'Unknown':
        if check_field_match(['address', 'location', 'street'], 'Address'):
            inv_addr = invoice_vendor.get('address', 'Unknown')
            db_addr = database_vendor.get('address', 'Unknown') if database_vendor else 'Unknown'
            evidence['silver_tier'].append({
                'field': 'Address',
                'matched': True,
                'invoice_value': inv_addr[:50] + '...' if len(inv_addr) > 50 else inv_addr,
                'database_value': db_addr[:50] + '...' if len(db_addr) > 50 else db_addr,
                'confidence_contribution': 30.0,
                'icon': '✅'
            })
        elif database_vendor and database_vendor.get('address'):
            evidence['bronze_tier'].append({
                'field': 'Address',
                'matched': False,
                'reason': 'Not matched in reasoning',
                'confidence_contribution': 0.0,
                'icon': '❌'
            })
    else:
        evidence['bronze_tier'].append({
            'field': 'Address',
            'matched': False,
            'reason': 'Not available in invoice',
            'confidence_contribution': 0.0,
            'icon': '❌'
        })
    
    # SILVER TIER EVIDENCE (Strong Evidence)
    # Email Domain Match - AI will classify domain type in structured evidence
    if invoice_vendor.get('email') and invoice_vendor['email'] != 'Unknown':
        inv_email = invoice_vendor.get('email', 'Unknown')
        
        if check_field_match(['email', 'domain', '@'], 'Email'):
            # Email domain matched - tier depends on AI's semantic classification
            db_email = database_vendor.get('email', 'Unknown') if database_vendor else 'Unknown'
            
            # Check if reasoning mentions "generic" or "corporate" domain
            if 'generic' in reasoning_lower and ('gmail' in reasoning_lower or 'yahoo' in reasoning_lower):
                # AI indicated generic domain - BRONZE TIER
                evidence['bronze_tier'].append({
                    'field': 'Email Domain',
                    'matched': True,
                    'invoice_value': inv_email,
                    'database_value': db_email,
                    'reason': 'Generic email provider (from AI reasoning)',
                    'confidence_contribution': 0.0,
                    'icon': '⚠️'
                })
            elif 'corporate' in reasoning_lower or 'business' in reasoning_lower or 'unique' in reasoning_lower:
                # AI indicated corporate/unique domain - GOLD TIER
                evidence['gold_tier'].append({
                    'field': 'Email Domain',
                    'matched': True,
                    'invoice_value': inv_email,
                    'database_value': db_email,
                    'reason': 'Corporate domain (from AI reasoning)',
                    'confidence_contribution': 45.0,
                    'icon': '✅'
                })
            else:
                # Unclear from reasoning - SILVER TIER by default
                evidence['silver_tier'].append({
                    'field': 'Email Domain',
                    'matched': True,
                    'invoice_value': inv_email,
                    'database_value': db_email,
                    'reason': 'Domain matched (tier unclear from reasoning)',
                    'confidence_contribution': 20.0,
                    'icon': '✅'
                })
        else:
            evidence['silver_tier'].append({
                'field': 'Email Domain',
                'matched': False,
                'reason': 'Not matched',
                'confidence_contribution': 0.0,
                'icon': '❌'
            })
    else:
        evidence['silver_tier'].append({
            'field': 'Email Domain',
            'matched': False,
            'reason': 'Not available in invoice',
            'confidence_contribution': 0.0,
            'icon': '❌'
        })
    
    # Phone Match
    if invoice_vendor.get('phone') and invoice_vendor['phone'] != 'Unknown':
        if check_field_match(['phone', 'telephone', 'contact'], 'Phone'):
            inv_phone = invoice_vendor.get('phone', 'Unknown')
            db_phone = database_vendor.get('phone', 'Unknown') if database_vendor else 'Unknown'
            evidence['silver_tier'].append({
                'field': 'Phone',
                'matched': True,
                'invoice_value': inv_phone,
                'database_value': db_phone,
                'confidence_contribution': 15.0,
                'icon': '✅'
            })
        else:
            evidence['silver_tier'].append({
                'field': 'Phone',
                'matched': False,
                'reason': 'Not matched',
                'confidence_contribution': 0.0,
                'icon': '❌'
            })
    else:
        evidence['silver_tier'].append({
            'field': 'Phone',
            'matched': False,
            'reason': 'Not available in invoice',
            'confidence_contribution': 0.0,
            'icon': '❌'
        })
    
    return evidence

_processor = None
_gmail_service = None
_token_storage = None
_bigquery_service = None
_csv_mapper = None
_vertex_search_service = None
_agent_search_service = None
_issue_detector = None
_action_manager = None

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

def get_vertex_search_service():
    """Lazy initialization of VertexSearchService"""
    global _vertex_search_service
    if _vertex_search_service is None:
        _vertex_search_service = VertexSearchService()
    return _vertex_search_service

def get_agent_services():
    """Lazy initialization of agent services"""
    global _agent_search_service, _issue_detector, _action_manager
    if not _agent_search_service:
        bq = get_bigquery_service()
        vertex = get_vertex_search_service()
        gmail = get_gmail_service()
        
        _agent_search_service = AgentSearchService(vertex, bq)
        _issue_detector = IssueDetector(bq)
        _action_manager = ActionManager(bq, gmail)
    
    return _agent_search_service, _issue_detector, _action_manager

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
        
        # FIX: Use ORIGINAL OCR data (before Layer 3.5 resolution) for UI display
        # But search using BOTH original and resolved names for matching
        # Layer 3.5 saves original data in 'original_ocr_name' before resolving legal beneficiary
        original_vendor_name = vendor_data.get('original_ocr_name') or vendor_data.get('original_supplier_name') or vendor_data.get('name', '')
        resolved_vendor_name = vendor_data.get('name', '')  # This is the Layer 3.5 resolved name
        
        # Use original for UI display, but we'll search with BOTH names
        vendor_name = original_vendor_name
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
                
                # AI-FIRST ENTITY CLASSIFICATION (before vendor matching)
                print(f"\n🤖 Step 0: Semantic Entity Classification")
                print(f"-" * 60)
                classifier = SemanticEntityClassifier(processor.gemini_service)
                
                classification = classifier.classify_entity(
                    entity_name=vendor_name,
                    entity_context=f"Email: {email}, Phone: {phone}, Country: {country}"
                )
                
                # Log classification
                print(f"🤖 Entity Classification: {classification['entity_type']} ({classification['confidence']})")
                print(f"   Reasoning: {classification['reasoning']}")
                
                # Reject non-vendors (banks, payment processors, government entities)
                if not classification.get('is_valid_vendor', True):
                    print(f"❌ Rejected: {vendor_name} is classified as {classification['entity_type']}")
                    
                    # Store rejected entity for RAG learning
                    vertex_service = get_vertex_search_service()
                    try:
                        vertex_service.store_rejected_entity(
                            entity_name=vendor_name,
                            entity_type=classification['entity_type'],
                            reasoning=classification['reasoning']
                        )
                        print(f"✓ Rejected entity stored in Vertex Search for learning")
                    except Exception as store_error:
                        print(f"⚠️ Failed to store rejected entity: {store_error}")
                    
                    vendor_match_result = {
                        'verdict': 'INVALID_VENDOR',
                        'entity_type': classification['entity_type'],
                        'reasoning': classification['reasoning'],
                        'confidence': classification['confidence'],
                        'vendor_id': None,
                        'method': 'SEMANTIC_ENTITY_CLASSIFICATION',
                        'risk_analysis': 'HIGH',
                        'database_updates': {},
                        'parent_child_logic': {
                            'is_subsidiary': False,
                            'parent_company_detected': None
                        },
                        'invoice_vendor': {
                            'name': vendor_name,  # Original OCR name
                            'tax_id': tax_id or 'Unknown',
                            'address': address or 'Unknown',
                            'country': country or 'Unknown',
                            'email': email or 'Unknown',
                            'phone': phone or 'Unknown'
                        },
                        'resolved_vendor_name': resolved_vendor_name if resolved_vendor_name != original_vendor_name else None,
                        'database_vendor': None
                    }
                else:
                    # Entity is valid, proceed with vendor matching
                    print(f"✓ Entity is valid vendor, proceeding with matching...")
                    
                    # FIX ISSUE 1: Reuse cached processor instance (no re-entrancy)
                    bigquery_service = get_bigquery_service()
                    
                    # Create VendorMatcher instance
                    matcher = VendorMatcher(
                        bigquery_service=bigquery_service,
                        vertex_search_service=processor.vertex_search_service,
                        gemini_service=processor.gemini_service
                    )
                    
                    # Prepare vendor data for matching
                    # CRITICAL: Include BOTH original OCR name AND resolved legal name for semantic matching
                    matching_input = {
                        'vendor_name': vendor_name,  # Original OCR ("Fully Booked")
                        'resolved_legal_name': resolved_vendor_name if resolved_vendor_name != vendor_name else None,  # Layer 3.5 result ("Artem Andreevitch Revva")
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
                            'name': vendor_name,  # Original OCR name (e.g., "Fully-Booked")
                            'tax_id': tax_id or 'Unknown',
                            'address': address or 'Unknown',
                            'country': country or 'Unknown',
                            'email': email or 'Unknown',
                            'phone': phone or 'Unknown'
                        },
                        'resolved_vendor_name': resolved_vendor_name if resolved_vendor_name != original_vendor_name else None,  # Layer 3.5 resolution (e.g., "Artem Andreevitch Revva")
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
                                # Try 'addresses' (plural) first, then 'address' (singular)
                                if custom_attrs:
                                    if custom_attrs.get('addresses') and isinstance(custom_attrs.get('addresses'), list):
                                        addresses = custom_attrs['addresses']
                                    elif custom_attrs.get('address'):
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
                    
                    # Generate evidence breakdown (AI-First: use structured evidence if available)
                    evidence_breakdown = parse_evidence_breakdown(
                        reasoning=match_result.get('reasoning', ''),
                        invoice_vendor=vendor_match_result['invoice_vendor'],
                        database_vendor=vendor_match_result.get('database_vendor'),
                        confidence=match_result.get('confidence', 0.0),
                        verdict=verdict,
                        structured_evidence=match_result.get('evidence_breakdown')
                    )
                    if evidence_breakdown:
                        vendor_match_result['evidence_breakdown'] = evidence_breakdown
                    
                    print(f"✓ Vendor matching complete: {match_result.get('verdict')}")
                
                # Log completion for rejected entities
                if vendor_match_result and vendor_match_result.get('verdict') == 'INVALID_VENDOR':
                    print(f"✓ Entity classification complete: INVALID_VENDOR ({vendor_match_result.get('entity_type')})")
                
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
                        'name': vendor_name,  # Original OCR name
                        'tax_id': tax_id or 'Unknown',
                        'address': address or 'Unknown',
                        'country': country or 'Unknown',
                        'email': email or 'Unknown',
                        'phone': phone or 'Unknown'
                    },
                    'resolved_vendor_name': resolved_vendor_name if resolved_vendor_name != original_vendor_name else None,
                    'database_vendor': None,
                    'error': str(e)
                }
        else:
            print("ℹ️ Skipping vendor matching: No vendor name extracted from invoice")
    
    # Add vendor matching result to response
    if vendor_match_result:
        result['vendor_match'] = vendor_match_result
    
    # SAVE INVOICE-VENDOR MATCH TO BIGQUERY
    if result.get('status') == 'completed' and 'validated_data' in result:
        validated_data = result.get('validated_data', {})
        
        # Extract invoice data (try multiple possible keys for invoice_id)
        invoice_id = validated_data.get('invoiceId') or validated_data.get('invoiceNumber') or 'Unknown'
        total_amount = validated_data.get('totalAmount', 0)
        currency_code = validated_data.get('currencyCode', 'USD')
        invoice_date = validated_data.get('invoiceDate', None)
        vendor_data = validated_data.get('vendor', {})
        vendor_name = vendor_data.get('name', 'Unknown')
        
        # Determine status from vendor match verdict
        status = 'unmatched'
        vendor_id = None
        
        if vendor_match_result:
            verdict = vendor_match_result.get('verdict', 'NEW_VENDOR')
            vendor_id = vendor_match_result.get('vendor_id')
            
            if verdict == 'MATCH':
                status = 'matched'
            elif verdict == 'NEW_VENDOR':
                status = 'unmatched'
            elif verdict == 'AMBIGUOUS':
                status = 'ambiguous'
        
        # Prepare invoice data for BigQuery
        invoice_data = {
            'invoice_id': invoice_id,
            'vendor_id': vendor_id,
            'vendor_name': vendor_name,
            'client_id': 'default_client',
            'amount': total_amount,
            'currency': currency_code,
            'invoice_date': invoice_date,
            'status': status,
            'gcs_uri': result.get('gcs_uri'),
            'file_type': result.get('file_type'),
            'file_size': result.get('file_size'),
            'metadata': {
                'vendor_match': vendor_match_result if vendor_match_result else {},
                'file_name': result.get('file_name'),
                'validated_data': validated_data
            }
        }
        
        # Insert into BigQuery
        try:
            bigquery_service = get_bigquery_service()
            bigquery_service.insert_invoice(invoice_data)
        except Exception as e:
            print(f"⚠️ Warning: Could not save invoice to BigQuery: {e}")
    
    return jsonify(result), 200

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

@app.route('/api/invoices/matches', methods=['GET'])
def get_invoice_matches():
    """
    Get invoice match history with pagination and filtering
    
    Query parameters:
    - page: Page number (default 1)
    - limit: Number of invoices per page (default 20)
    - status: Optional status filter (matched/unmatched/ambiguous)
    
    Response:
    {
        "invoices": [...],
        "total_count": 50,
        "page": 1,
        "limit": 20
    }
    """
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        status = request.args.get('status', None, type=str)
        
        # Validate parameters
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 20
        
        # Fetch invoices from BigQuery
        bigquery_service = get_bigquery_service()
        result = bigquery_service.get_invoices(page=page, limit=limit, status=status)
        
        return jsonify({
            'invoices': result['invoices'],
            'total_count': result['total_count'],
            'page': page,
            'limit': limit
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching invoice matches: {e}")
        return jsonify({
            'error': str(e),
            'invoices': [],
            'total_count': 0,
            'page': page,
            'limit': limit
        }), 500

@app.route('/api/invoices/<invoice_id>/download', methods=['GET'])
def get_invoice_download_url(invoice_id):
    """
    Get a signed URL to download/view the original invoice file from GCS
    
    Args:
        invoice_id: Invoice ID from BigQuery
    
    Query parameters:
        - expiration: URL expiration time in seconds (default 3600, max 86400)
    
    Response:
    {
        "success": true,
        "invoice_id": "INV-2025-001",
        "download_url": "https://storage.googleapis.com/...",
        "file_type": "pdf",
        "file_size": 1024567,
        "expires_in": 3600
    }
    """
    try:
        from google.cloud import storage
        from google.oauth2 import service_account
        import datetime
        import os
        import json
        
        # Get expiration parameter (default 1 hour, max 24 hours)
        expiration_seconds = min(request.args.get('expiration', 3600, type=int), 86400)
        
        # Fetch invoice data from BigQuery to get GCS URI
        bigquery_service = get_bigquery_service()
        
        query = f"""
        SELECT invoice_id, gcs_uri, file_type, file_size, vendor_name
        FROM `{config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai.invoices`
        WHERE invoice_id = @invoice_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)
            ]
        )
        
        query_job = bigquery_service.client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            return jsonify({
                'success': False,
                'error': f'Invoice {invoice_id} not found'
            }), 404
        
        row = results[0]
        gcs_uri = row.gcs_uri
        file_type = row.file_type
        file_size = row.file_size
        vendor_name = row.vendor_name
        
        if not gcs_uri:
            return jsonify({
                'success': False,
                'error': 'No file stored for this invoice'
            }), 404
        
        # Parse GCS URI (format: gs://bucket/path/to/file)
        if not gcs_uri.startswith('gs://'):
            return jsonify({
                'success': False,
                'error': 'Invalid GCS URI format'
            }), 500
        
        uri_parts = gcs_uri[5:].split('/', 1)
        bucket_name = uri_parts[0]
        blob_name = uri_parts[1] if len(uri_parts) > 1 else ''
        
        # Initialize GCS client with credentials
        credentials = None
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
            except json.JSONDecodeError:
                print("Warning: Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH
            )
        
        storage_client = storage.Client(
            project=config.GOOGLE_CLOUD_PROJECT_ID,
            credentials=credentials
        )
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Check if blob exists
        if not blob.exists():
            return jsonify({
                'success': False,
                'error': 'File not found in storage'
            }), 404
        
        # Generate signed URL
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="GET"
        )
        
        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'vendor_name': vendor_name,
            'download_url': signed_url,
            'file_type': file_type,
            'file_size': file_size,
            'expires_in': expiration_seconds
        }), 200
        
    except Exception as e:
        print(f"❌ Error generating download URL: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
        def send_event(event_type, data_dict):
            return f"event: {event_type}\ndata: {json.dumps(data_dict)}\n\n"
        
        try:
            session_token = session.get('gmail_session_token')
            
            if not session_token:
                yield send_event('error', {'message': 'Gmail not connected'})
                return
            
            token_storage = get_token_storage()
            credentials = token_storage.get_credentials(session_token)
            
            if not credentials:
                yield send_event('error', {'message': 'Gmail session expired'})
                return
            
            days = request.args.get('days', 7, type=int)
            
            time_label = f'{days} days' if days < 9999 else 'all time'
            
            yield send_event('progress', {'type': 'status', 'message': '🚀 Gmail Invoice Scanner Initialized'})
            yield send_event('progress', {'type': 'status', 'message': f'⏰ Time range: Last {time_label}'})
            yield send_event('progress', {'type': 'status', 'message': 'Authenticating with Gmail API...'})
            
            gmail_service = get_gmail_service()
            service = gmail_service.build_service(credentials)
            
            email = credentials.get('email', 'Gmail account')
            yield send_event('progress', {'type': 'status', 'message': f'Connected to {email}'})
            
            # Get ACCURATE total count by fetching all message IDs in time range
            from datetime import datetime, timedelta
            after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
            yield send_event('progress', {'type': 'status', 'message': f'\n📊 Counting total emails in last {time_label}...'})
            
            try:
                # Paginate through ALL emails in time range to get accurate count
                all_messages = []
                page_token = None
                
                while True:
                    params = {
                        'userId': 'me',
                        'q': f'after:{after_date}',
                        'maxResults': 500  # Max per page
                    }
                    if page_token:
                        params['pageToken'] = page_token
                    
                    response = service.users().messages().list(**params).execute()
                    messages_page = response.get('messages', [])
                    all_messages.extend(messages_page)
                    
                    page_token = response.get('nextPageToken')
                    if not page_token:
                        break
                    
                    # Show progress for large mailboxes - more frequent updates to prevent timeout
                    if len(all_messages) % 250 == 0:  # Update every 250 messages instead of 1000
                        yield send_event('progress', {'type': 'status', 'message': f'  Counted {len(all_messages):,} emails so far...'})
                        yield send_event('keepalive', {'type': 'ping', 'message': 'Still counting...'})
                
                total_inbox_count = len(all_messages)
            except Exception as e:
                total_inbox_count = 0
                yield send_event('progress', {'type': 'status', 'message': f'⚠️ Could not count emails: {str(e)}'})
            
            yield send_event('progress', {'type': 'status', 'message': f'📬 Total emails in selected time range ({time_label}): {total_inbox_count:,} emails'})
            
            # Stage 1: Broad Net Gmail Query
            stage1_msg = '\n🔍 STAGE 1: Broad Net Gmail Query (Multi-Language)'
            yield send_event('progress', {'type': 'status', 'message': stage1_msg})
            yield send_event('progress', {'type': 'status', 'message': 'Casting wide net: English, Hebrew, French, German, Spanish keywords...'})
            yield send_event('progress', {'type': 'status', 'message': 'Excluding: newsletters, webinars, invitations...'})
            
            messages = gmail_service.search_invoice_emails(service, 500, days)  # Get up to 500 for filtering
            
            total_found = len(messages)
            stage1_percent = round((total_found / max(total_inbox_count, 1)) * 100, 2)
            yield send_event('progress', {'type': 'status', 'message': f'📧 Found {total_found} emails matching broad financial patterns ({stage1_percent}% of inbox)'})
            
            # Stage 2: Elite Gatekeeper AI Filter
            stage2_msg = '\n🧠 STAGE 2: Elite Gatekeeper AI Filter (Gemini 1.5 Flash)'
            yield send_event('progress', {'type': 'status', 'message': stage2_msg})
            yield send_event('progress', {'type': 'status', 'message': f'AI analyzing {total_found} emails for semantic context...'})
            yield send_event('progress', {'type': 'status', 'message': 'Filtering: Marketing spam, newsletters, logistics, false positives...'})
            
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
                        yield send_event('progress', {'type': 'status', 'message': invoice_msg})
                    else:
                        non_invoices.append((subject, reasoning))
                        skip_msg = f'  ✗ [{idx}/{total_found}] KILL: "{subject[:50]}..." ({reasoning[:80]})'
                        yield send_event('progress', {'type': 'status', 'message': skip_msg})
                    
                except Exception as e:
                    non_invoices.append((f'Error: {str(e)}', None))
                    yield send_event('progress', {'type': 'status', 'message': f'  ⚠️ Error classifying email: {str(e)[:60]}'})
            
            invoice_count = len(classified_invoices)
            non_invoice_count = len(non_invoices)
            
            # Calculate filtering funnel statistics
            after_language_filter_percent = round((total_found / max(total_found, 1)) * 100, 1)
            after_ai_filter_percent = round((invoice_count / max(total_found, 1)) * 100, 1)
            
            # Send structured filtering funnel event
            funnel_stats = {
                'timeRange': time_label,
                'totalInboxCount': total_inbox_count,
                'totalEmails': total_found,
                'afterLanguageFilter': total_found,
                'languageFilterPercent': round((total_found / max(total_inbox_count, 1)) * 100, 2),
                'afterAIFilter': invoice_count,
                'aiFilterPercent': after_ai_filter_percent,
                'invoicesFound': 0,  # Will be updated after extraction
                'invoicesPercent': 0.0
            }
            yield send_event('funnel_stats', funnel_stats)
            
            filter_results_msg = '\n📊 FILTERING RESULTS:'
            yield send_event('progress', {'type': 'status', 'message': filter_results_msg})
            yield send_event('progress', {'type': 'status', 'message': f'  • Total inbox emails: {total_inbox_count:,}'})
            yield send_event('progress', {'type': 'status', 'message': f'  • After Stage 1 filter: {total_found} ({stage1_percent}%)'})
            yield send_event('progress', {'type': 'status', 'message': f'  • After Stage 2 AI filter: {invoice_count} ({after_ai_filter_percent}% of {total_found})'})
            yield send_event('progress', {'type': 'status', 'message': f'  • Rejected: {non_invoice_count} emails'})
            
            # Stage 3: Extract invoice data through 3-layer AI
            stage3_msg = f'\n🤖 STAGE 3: Deep AI Extraction ({invoice_count} invoices)'
            yield send_event('progress', {'type': 'status', 'message': stage3_msg})
            yield send_event('progress', {'type': 'info', 'message': '3-Layer Pipeline: Document AI OCR → Vertex Search RAG → Gemini Semantic'})
            
            imported_invoices = []
            extraction_failures = []
            
            for idx, (message, metadata, confidence) in enumerate(classified_invoices, 1):
                try:
                    subject = metadata.get('subject', 'No subject')
                    sender = metadata.get('from', 'Unknown')
                    
                    processing_msg = f'\n[{idx}/{invoice_count}] Processing: "{subject[:50]}..."'
                    yield send_event('progress', {'type': 'analyzing', 'message': processing_msg})
                    yield send_event('progress', {'type': 'info', 'message': f'  From: {sender}'})
                    
                    # Extract attachments
                    attachments = gmail_service.extract_attachments(service, message)
                    
                    # Extract links
                    links = gmail_service.extract_links_from_body(message)
                    
                    if not attachments and not links:
                        yield send_event('progress', {'type': 'warning', 'message': f'  ⚠️ No PDFs or download links found'})
                        extraction_failures.append(subject)
                        continue
                    
                    # Process attachments
                    for filename, file_data in attachments:
                        yield send_event('progress', {'type': 'status', 'message': f'  📎 Attachment: {filename}'})
                        
                        secure_name = secure_filename(filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        yield send_event('progress', {'type': 'status', 'message': '    → Layer 1: Document AI OCR...'})
                        yield send_event('progress', {'type': 'status', 'message': '    → Layer 2: Vertex Search RAG...'})
                        yield send_event('progress', {'type': 'status', 'message': '    → Layer 3: Gemini Semantic Extraction...'})
                        yield send_event('progress', {'type': 'keepalive', 'message': '⏳ Processing invoice (this may take 30-60 seconds)...'})
                        
                        try:
                            invoice_result = processor.process_local_file(filepath, 'application/pdf')
                        except Exception as proc_error:
                            os.remove(filepath)
                            yield send_event('progress', {'type': 'error', 'message': f'  ❌ Processing failed: {str(proc_error)[:100]}'})
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
                            yield send_event('progress', {'type': 'success', 'message': f'  ✅ SUCCESS: {vendor} | Invoice #{invoice_num} | {currency} {total}'})
                            
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
                            yield send_event('progress', {'type': 'warning', 'message': f'  ⚠️ Extraction incomplete: Vendor={vendor}, Total={total}'})
                            extraction_failures.append(subject)
                    
                    # Process links with AI-semantic intelligent processing
                    for link_url in links[:2]:  # Limit to first 2 links per email
                        yield send_event('progress', {'type': 'status', 'message': f'  🔗 Analyzing link: {link_url[:80]}...'})
                        
                        # AI-semantic intelligent link processing
                        email_context = f"{subject} - {metadata.get('snippet', '')[:100]}"
                        link_result = gmail_service.process_link_intelligently(link_url, email_context, gemini_service)
                        
                        if link_result['success']:
                            filename = link_result['filename']
                            file_data = link_result['data']
                            link_type = link_result['type']  # 'pdf' or 'screenshot'
                            classification = link_result['link_classification']
                            
                            # Show appropriate message based on processing type
                            if link_type == 'screenshot':
                                yield send_event('progress', {'type': 'success', 'message': f'  📸 Screenshot captured: {filename}'})
                                yield send_event('progress', {'type': 'info', 'message': f'  ℹ️ Source: Web receipt (screenshot)'})
                            else:
                                yield send_event('progress', {'type': 'success', 'message': f'  ✓ Downloaded: {filename}'})
                            
                            secure_name = secure_filename(filename)
                            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
                            
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            
                            # Determine file type for processing
                            if link_type == 'screenshot':
                                file_mimetype = 'image/png'
                                yield send_event('progress', {'type': 'status', 'message': '    → Layer 1: Document AI OCR (Image)...'})
                            else:
                                file_mimetype = 'application/pdf'
                                yield send_event('progress', {'type': 'status', 'message': '    → Layer 1: Document AI OCR...'})
                            
                            yield send_event('progress', {'type': 'status', 'message': '    → Layer 2: Vertex Search RAG...'})
                            yield send_event('progress', {'type': 'status', 'message': '    → Layer 3: Gemini Semantic Extraction...'})
                            yield send_event('progress', {'type': 'keepalive', 'message': '⏳ Processing file...'})
                            
                            try:
                                invoice_result = processor.process_local_file(filepath, file_mimetype)
                            except Exception as link_proc_error:
                                os.remove(filepath)
                                yield send_event('progress', {'type': 'error', 'message': f'  ❌ Processing failed: {str(link_proc_error)[:100]}'})
                                continue
                            
                            os.remove(filepath)
                            
                            validated = invoice_result.get('validated_data', {})
                            vendor = validated.get('vendor', {}).get('name', 'Unknown')
                            invoice_num = validated.get('invoiceNumber', 'N/A')
                            totals = validated.get('totals', {})
                            total = totals.get('total', 0)
                            currency = validated.get('currency', 'USD')
                            
                            # Save to BigQuery if extraction succeeded
                            if invoice_result.get('status') == 'completed' and validated:
                                invoice_id = validated.get('invoiceId', 'Unknown')
                                total_amount = validated.get('totalAmount', 0)
                                currency_code = validated.get('currencyCode', 'USD')
                                invoice_date = validated.get('invoiceDate', None)
                                
                                invoice_data = {
                                    'invoice_id': invoice_id,
                                    'vendor_id': None,
                                    'vendor_name': vendor,
                                    'client_id': 'default_client',
                                    'amount': total_amount,
                                    'currency': currency_code,
                                    'invoice_date': invoice_date,
                                    'status': 'unmatched',
                                    'gcs_uri': invoice_result.get('gcs_uri'),
                                    'file_type': invoice_result.get('file_type'),
                                    'file_size': invoice_result.get('file_size'),
                                    'metadata': {
                                        'file_name': invoice_result.get('file_name'),
                                        'validated_data': validated,
                                        'gmail_metadata': {
                                            'subject': subject,
                                            'from': sender,
                                            'date': metadata.get('date'),
                                            'source_type': link_type
                                        }
                                    }
                                }
                                
                                try:
                                    bigquery_service = get_bigquery_service()
                                    bigquery_service.insert_invoice(invoice_data)
                                except Exception as bq_error:
                                    print(f"⚠️ Warning: Could not save Gmail invoice to BigQuery: {bq_error}")
                            
                            if vendor and vendor != 'Unknown' and total and total > 0:
                                source_label = '📸 Screenshot' if link_type == 'screenshot' else '🔗 Link'
                                yield send_event('progress', {'type': 'success', 'message': f'  ✅ Extracted from {source_label}: {vendor} | Invoice #{invoice_num} | {currency} {total}'})
                                imported_invoices.append({
                                    'subject': subject,
                                    'sender': sender,
                                    'date': metadata.get('date'),
                                    'vendor': vendor,
                                    'invoice_number': invoice_num,
                                    'total': total,
                                    'currency': currency,
                                    'line_items': validated.get('lineItems', []),
                                    'full_data': validated,
                                    'source_type': link_type  # Track if from screenshot or PDF
                                })
                        else:
                            # Processing failed - show why
                            reasoning = link_result['reasoning']
                            yield send_event('progress', {'type': 'warning', 'message': f'  ⚠️ Failed: {reasoning[:120]}'})
                    
                except Exception as e:
                    yield send_event('progress', {'type': 'error', 'message': f'  ❌ Extraction error: {str(e)}'})
                    extraction_failures.append(subject)
            
            imported_count = len(imported_invoices)
            failed_extraction = len(extraction_failures)
            
            complete_msg = '\n✅ Import Complete!'
            yield send_event('progress', {'type': 'success', 'message': complete_msg})
            final_results_msg = '\n📈 FINAL RESULTS:'
            yield send_event('progress', {'type': 'info', 'message': final_results_msg})
            yield send_event('progress', {'type': 'info', 'message': f'  • Emails scanned: {total_found}'})
            yield send_event('progress', {'type': 'info', 'message': f'  • Clean invoices found: {invoice_count}'})
            yield send_event('progress', {'type': 'success', 'message': f'  • Successfully extracted: {imported_count} ✓'})
            yield send_event('progress', {'type': 'warning', 'message': f'  • Extraction failed: {failed_extraction}'})
            yield send_event('complete', {'imported': imported_count, 'skipped': non_invoice_count, 'total': total_found, 'invoices': imported_invoices})
            
        except Exception as e:
            yield send_event('error', {'message': f'Import failed: {str(e)}'})
    
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
                        
                        # Save to BigQuery if extraction succeeded
                        if invoice_result.get('status') == 'completed' and 'validated_data' in invoice_result:
                            validated_data = invoice_result.get('validated_data', {})
                            
                            # Extract invoice data
                            invoice_id = validated_data.get('invoiceId', 'Unknown')
                            total_amount = validated_data.get('totalAmount', 0)
                            currency_code = validated_data.get('currencyCode', 'USD')
                            invoice_date = validated_data.get('invoiceDate', None)
                            vendor_data = validated_data.get('vendor', {})
                            vendor_name = vendor_data.get('name', 'Unknown')
                            
                            # Prepare invoice data for BigQuery
                            invoice_data = {
                                'invoice_id': invoice_id,
                                'vendor_id': None,  # Not doing vendor matching in Gmail import for now
                                'vendor_name': vendor_name,
                                'client_id': 'default_client',
                                'amount': total_amount,
                                'currency': currency_code,
                                'invoice_date': invoice_date,
                                'status': 'unmatched',
                                'gcs_uri': invoice_result.get('gcs_uri'),
                                'file_type': invoice_result.get('file_type'),
                                'file_size': invoice_result.get('file_size'),
                                'metadata': {
                                    'file_name': invoice_result.get('file_name'),
                                    'validated_data': validated_data,
                                    'gmail_metadata': {
                                        'subject': metadata.get('subject'),
                                        'from': metadata.get('from'),
                                        'date': metadata.get('date')
                                    }
                                }
                            }
                            
                            # Insert into BigQuery
                            try:
                                bigquery_service = get_bigquery_service()
                                bigquery_service.insert_invoice(invoice_data)
                            except Exception as e:
                                print(f"⚠️ Warning: Could not save Gmail invoice to BigQuery: {e}")
                        
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
        
        # CRITICAL FIX 1: AI-FIRST SEMANTIC ENTITY CLASSIFICATION
        # Classify each vendor BEFORE adding to database to prevent banks/payment processors
        print(f"\n{'='*60}")
        print(f"🤖 AI-FIRST ENTITY CLASSIFICATION: Validating {len(transformed_vendors)} vendors")
        print(f"{'='*60}\n")
        
        processor = get_processor()
        classifier = SemanticEntityClassifier(processor.gemini_service)
        vertex_service = get_vertex_search_service()
        
        valid_vendors = []
        rejected_vendors = []
        
        for vendor in transformed_vendors:
            vendor_name = vendor.get('global_name', '')
            emails = vendor.get('emails', [])
            domains = vendor.get('domains', [])
            
            # Build context for classifier
            email_str = ', '.join(emails) if emails else 'None'
            domain_str = ', '.join(domains) if domains else 'None'
            entity_context = f"Emails: {email_str}, Domains: {domain_str}"
            
            # Classify entity
            classification = classifier.classify_entity(
                entity_name=vendor_name,
                entity_context=entity_context
            )
            
            print(f"🤖 {vendor_name}: {classification['entity_type']} ({classification['confidence']})")
            print(f"   Reasoning: {classification['reasoning']}")
            
            # Separate valid vendors from rejected entities
            if classification.get('is_valid_vendor', True):
                valid_vendors.append(vendor)
                print(f"   ✅ VALID VENDOR - Will be imported")
            else:
                rejected_vendors.append({
                    'vendor_name': vendor_name,
                    'entity_type': classification['entity_type'],
                    'reasoning': classification['reasoning'],
                    'confidence': classification['confidence']
                })
                
                # Store rejected entity in Vertex Search for RAG learning
                try:
                    vertex_service.store_rejected_entity(
                        entity_name=vendor_name,
                        entity_type=classification['entity_type'],
                        reasoning=classification['reasoning']
                    )
                    print(f"   ❌ REJECTED ({classification['entity_type']}) - Stored in RAG for learning")
                except Exception as store_error:
                    print(f"   ⚠️ Could not store rejected entity: {store_error}")
        
        print(f"\n📊 Classification Results:")
        print(f"   ✅ Valid vendors: {len(valid_vendors)}")
        print(f"   ❌ Rejected entities: {len(rejected_vendors)}\n")
        
        # Initialize BigQuery and ensure table exists
        bq_service = get_bigquery_service()
        bq_service.ensure_table_schema()
        
        # Only merge VALID vendors into BigQuery
        merge_result = bq_service.merge_vendors(valid_vendors, source_system)
        
        # Add rejection info to result
        merge_result['rejected_count'] = len(rejected_vendors)
        merge_result['rejected_vendors'] = rejected_vendors
        
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
            'validVendors': len(valid_vendors),
            'rejectedEntities': len(rejected_vendors),
            'inserted': merge_result['inserted'],
            'updated': merge_result['updated'],
            'errors': merge_result['errors'],
            'rejections': rejected_vendors
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
    Get paginated list of all vendors from BigQuery with optional search
    
    Query parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20)
        - search: Optional search term to filter vendors
    
    Returns:
        {
            "vendors": [...],
            "total_count": int,
            "page": int,
            "limit": int,
            "total_pages": int,
            "search": str (if provided)
        }
    """
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        search_term = request.args.get('search', '').strip()
        
        # Validate parameters
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 20
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Get vendors from BigQuery with optional search
        bq_service = get_bigquery_service()
        result = bq_service.get_all_vendors(
            limit=limit, 
            offset=offset,
            search_term=search_term if search_term else None
        )
        
        # Calculate total pages
        total_count = result['total_count']
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
        
        response = {
            'vendors': result['vendors'],
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        }
        
        # Include search term in response if provided
        if search_term:
            response['search'] = search_term
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"❌ Error listing vendors: {e}")
        return jsonify({'error': str(e)}), 500

# AGENT API ENDPOINTS (Phase 2 & 3)

# API KEY GENERATION ENDPOINT (No auth required - this creates auth)
@app.route('/api/agent/generate-key', methods=['POST'])
def generate_api_key():
    """Generate a new API key for a client (UI-only endpoint)"""
    from services.agent_auth_service import AgentAuthService
    
    try:
        data = request.json
        client_id = data.get('client_id', '').strip()
        description = data.get('description', 'Generated from UI')
        
        if not client_id:
            return jsonify({'success': False, 'error': 'client_id is required'}), 400
        
        # Initialize auth service
        bq = get_bigquery_service()
        auth_service = AgentAuthService(bq)
        
        # Generate API key
        api_key = auth_service.generate_api_key(client_id, description)
        
        return jsonify({
            'success': True,
            'api_key': api_key,
            'client_id': client_id,
            'description': description,
            'created_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error generating API key: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ENDPOINT 1: Search
@app.route('/api/agent/search', methods=['POST'])
@require_agent_auth
def agent_search():
    """Unified search across vendors, invoices, and documents"""
    data = request.json
    search_service, _, _ = get_agent_services()
    
    page = data.get('page', 1)
    limit = data.get('max_results', 50)
    offset = (page - 1) * limit
    
    all_results = search_service.search(
        query=data['query'],
        client_id=request.client_id,
        filters=data.get('filters'),
        max_results=limit + offset + 50
    )
    
    results = all_results[offset:offset + limit]
    
    return jsonify({
        'success': True,
        'results': results,
        'total_count': len(all_results),
        'page': page,
        'limit': limit,
        'has_more': len(all_results) > offset + limit
    })

# ENDPOINT 2: Get Vendor Details
@app.route('/api/agent/vendor/<vendor_id>', methods=['GET'])
@require_agent_auth
def get_vendor_details(vendor_id):
    """Get detailed vendor information including invoice stats"""
    bq = get_bigquery_service()
    
    query = """
    SELECT * FROM vendors_ai.global_vendors 
    WHERE vendor_id = @vendor_id AND client_id = @client_id
    """
    results = list(bq.query(query, {
        'vendor_id': vendor_id,
        'client_id': request.client_id
    }))
    
    if not results:
        return jsonify({'success': False, 'error': 'Vendor not found'}), 404
    
    vendor = results[0]
    
    stats_query = """
    SELECT 
        COUNT(*) as invoice_count,
        SUM(amount) as total_spend,
        MAX(invoice_date) as last_invoice_date
    FROM vendors_ai.invoices
    WHERE vendor_id = @vendor_id AND client_id = @client_id
    """
    stats_results = list(bq.query(stats_query, {
        'vendor_id': vendor_id,
        'client_id': request.client_id
    }))
    stats = stats_results[0] if stats_results else {}
    
    return jsonify({
        'vendor_id': vendor_id,
        'global_name': vendor.get('global_name', 'Unknown'),
        'emails': vendor.get('emails', []),
        'countries': vendor.get('countries', []),
        'invoice_count': stats.get('invoice_count', 0) if stats else 0,
        'total_spend': float(stats.get('total_spend', 0)) if stats and stats.get('total_spend') else 0,
        'last_invoice_date': str(stats.get('last_invoice_date')) if stats and stats.get('last_invoice_date') else None
    })

# ENDPOINT 3: Get Invoice Details
@app.route('/api/agent/invoice/<invoice_id>', methods=['GET'])
@require_agent_auth
def get_invoice_details(invoice_id):
    """Get detailed invoice information"""
    bq = get_bigquery_service()
    
    query = """
    SELECT * FROM vendors_ai.invoices 
    WHERE invoice_id = @invoice_id AND client_id = @client_id
    """
    results = list(bq.query(query, {
        'invoice_id': invoice_id,
        'client_id': request.client_id
    }))
    
    if not results:
        return jsonify({'success': False, 'error': 'Invoice not found'}), 404
    
    invoice = results[0]
    return jsonify(invoice)

# ENDPOINT 4: Client Summary
@app.route('/api/agent/client/<client_id>/summary', methods=['GET'])
@require_agent_auth
def get_client_summary(client_id):
    """Get summary statistics for a client"""
    if client_id != request.client_id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    bq = get_bigquery_service()
    
    query = """
    SELECT 
        COUNT(DISTINCT vendor_id) as total_vendors,
        COUNT(*) as total_invoices,
        COUNTIF(status = 'pending') as pending_invoices
    FROM vendors_ai.invoices
    WHERE client_id = @client_id
    """
    stats_results = list(bq.query(query, {'client_id': client_id}))
    stats = stats_results[0] if stats_results else {}
    
    _, issue_detector, _ = get_agent_services()
    issues = issue_detector.detect_all_issues(client_id)
    
    return jsonify({
        'client_id': client_id,
        'total_vendors': stats.get('total_vendors', 0) if stats else 0,
        'total_invoices': stats.get('total_invoices', 0) if stats else 0,
        'pending_invoices': stats.get('pending_invoices', 0) if stats else 0,
        'compliance_issues': len(issues),
        'last_sync': datetime.now().isoformat()
    })

# ENDPOINT 5: Get Issues
@app.route('/api/agent/issues', methods=['GET'])
@require_agent_auth
def get_issues():
    """Get compliance issues with optional filtering"""
    severity = request.args.get('severity', '').split(',') if request.args.get('severity') else None
    
    _, issue_detector, _ = get_agent_services()
    issues = issue_detector.detect_all_issues(request.client_id)
    
    if severity:
        issues = [i for i in issues if i['severity'] in severity]
    
    return jsonify({'issues': issues})

# ENDPOINT 6: Resolve Issue
@app.route('/api/agent/issues/<issue_id>/resolve', methods=['POST'])
@require_agent_auth
def resolve_issue(issue_id):
    """Mark an issue as resolved"""
    data = request.json
    bq = get_bigquery_service()
    
    query = """
    UPDATE vendors_ai.agent_issues
    SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP(), 
        resolved_by = @resolved_by
    WHERE issue_id = @issue_id AND client_id = @client_id
    """
    bq.execute_query(query, {
        'issue_id': issue_id,
        'client_id': request.client_id,
        'resolved_by': data.get('resolution', 'agent')
    })
    
    return jsonify({'success': True, 'issue_id': issue_id, 'status': 'resolved'})

# ENDPOINT 7: Send Vendor Email
@app.route('/api/agent/vendor/send-email', methods=['POST'])
@require_agent_auth
def send_vendor_email():
    """Send email to vendor and log action"""
    data = request.json
    gmail = get_gmail_service()
    
    success = gmail.send_email(
        to=data['to'],
        subject=data['subject'],
        body=data['body']
    )
    
    _, _, action_manager = get_agent_services()
    action_id = action_manager.create_action(
        action_type='send_vendor_email',
        vendor_id=data['vendor_id'],
        vendor_email=data['to'],
        email_subject=data['subject'],
        email_body=data['body'],
        client_id=request.client_id,
        issue_id=data.get('track_as_issue'),
        priority='high'
    )
    
    return jsonify({'success': success, 'email_sent': success, 'action_id': action_id})

# ENDPOINT 8: Send Client Notification
@app.route('/api/agent/client/notify', methods=['POST'])
@require_agent_auth
def notify_client():
    """Send notification email to client"""
    data = request.json
    gmail = get_gmail_service()
    
    success = gmail.send_email(
        to=data['to'],
        subject=data['subject'],
        body=data['body']
    )
    
    return jsonify({'success': success, 'notification_sent': success})

# ENDPOINT 9: Create Pending Action
@app.route('/api/agent/actions/create', methods=['POST'])
@require_agent_auth
def create_action():
    """Create a pending action for client approval"""
    data = request.json
    _, _, action_manager = get_agent_services()
    
    action_id = action_manager.create_action(
        action_type=data['action_type'],
        vendor_id=data['vendor_id'],
        vendor_email=data['vendor_email'],
        email_subject=data['suggested_email']['subject'],
        email_body=data['suggested_email']['body'],
        client_id=request.client_id,
        issue_id=data.get('issue_id'),
        priority=data.get('priority', 'medium')
    )
    
    return jsonify({
        'success': True,
        'action_id': action_id,
        'status': 'pending_approval'
    })

# ENDPOINT 10: Get Pending Actions
@app.route('/api/agent/actions/pending', methods=['GET'])
@require_agent_auth
def get_pending_actions():
    """Get all pending actions for a client"""
    _, _, action_manager = get_agent_services()
    
    actions = action_manager.get_pending_actions(request.client_id)
    
    return jsonify({'pending_actions': actions})

# ENDPOINT 11: Approve/Reject Action
@app.route('/api/agent/actions/<action_id>/approve', methods=['POST'])
@require_agent_auth
def approve_action(action_id):
    """Approve or reject a pending action"""
    data = request.json
    _, _, action_manager = get_agent_services()
    
    result = action_manager.approve_action(
        action_id=action_id,
        client_id=request.client_id,
        approved=data.get('approved', True),
        modified_email=data.get('modified_email')
    )
    
    return jsonify(result)

# ENDPOINT 12: Update Client Settings
@app.route('/api/agent/client/<client_id>/settings', methods=['POST'])
@require_agent_auth
def update_client_settings(client_id):
    """Update client settings for agent automation"""
    if client_id != request.client_id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    data = request.json
    bq = get_bigquery_service()
    
    query = """
    MERGE vendors_ai.client_settings AS target
    USING (SELECT @client_id AS client_id) AS source
    ON target.client_id = source.client_id
    WHEN MATCHED THEN
        UPDATE SET auto_send_vendor_emails = @auto_send,
                   auto_send_threshold = @threshold,
                   updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (client_id, auto_send_vendor_emails, auto_send_threshold, created_at)
        VALUES (@client_id, @auto_send, @threshold, CURRENT_TIMESTAMP())
    """
    
    bq.execute_query(query, {
        'client_id': client_id,
        'auto_send': data.get('auto_send_vendor_emails', False),
        'threshold': data.get('auto_send_threshold', 'high_priority_only')
    })
    
    return jsonify({'success': True, 'settings_updated': True})

@app.route('/api/agent/test', methods=['GET'])
@require_agent_auth
def agent_test():
    """Test endpoint to verify Agent API authentication is working"""
    return jsonify({
        'success': True,
        'message': 'Agent API authentication working',
        'client_id': request.client_id
    })

# ==================== INVOICE GENERATION API ENDPOINTS ====================

# Initialize invoice generation services
pdf_generator = PDFInvoiceGenerator()
invoice_composer = InvoiceComposer()

@app.route('/api/invoice/search-vendors', methods=['GET'])
def search_vendors_for_invoice():
    """
    Search vendors for invoice generation autocomplete
    """
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify({'vendors': []})
    
    try:
        vendors = invoice_composer.search_vendors(query, limit=10)
        return jsonify({'vendors': vendors})
    except Exception as e:
        print(f"Error searching vendors: {e}")
        return jsonify({'error': str(e), 'vendors': []}), 500

@app.route('/api/invoice/magic-fill', methods=['POST'])
def invoice_magic_fill():
    """
    Use AI to parse natural language input and fill invoice fields
    """
    data = request.get_json()
    description = data.get('description', '')
    vendor = data.get('vendor', None)
    
    if not description:
        return jsonify({'error': 'Description is required'}), 400
    
    try:
        result = invoice_composer.magic_fill(description, vendor)
        return jsonify(result)
    except Exception as e:
        print(f"Magic fill error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/invoice/validate', methods=['POST'])
def validate_invoice():
    """
    Perform semantic validation on invoice data
    """
    invoice_data = request.get_json()
    
    try:
        result = invoice_composer.validate_invoice(invoice_data)
        return jsonify(result)
    except Exception as e:
        print(f"Validation error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/invoice/generate', methods=['POST'])
def generate_invoice():
    """
    Generate a professional PDF invoice
    """
    data = request.get_json()
    
    # Prepare invoice data structure
    invoice_data = {
        'vendor': data.get('vendor', {}),
        'buyer': data.get('buyer', {}),
        'currency': data.get('currency', 'USD'),
        'tax_type': data.get('tax_type', 'None'),
        'payment_terms': data.get('payment_terms', 'Net 30'),
        'notes': data.get('notes', '')
    }
    
    # Handle simple mode
    if data.get('mode') == 'simple':
        # Create line items from simple description and amount
        description = data.get('description', 'Services')
        amount = float(data.get('amount', 0))
        
        # Determine tax rate based on vendor country
        tax_rate = 0
        if data.get('tax_type') != 'none':
            vendor_country = invoice_data['vendor'].get('country', '')
            tax_info = invoice_composer.get_tax_info_for_country(vendor_country)
            tax_rate = tax_info['rate']
        
        invoice_data['line_items'] = [{
            'description': description,
            'quantity': 1,
            'unit_price': amount,
            'discount_percent': 0,
            'tax_rate': tax_rate,
            'tracking_category': 'General'
        }]
        
        # Generate invoice number
        invoice_data['invoice_number'] = invoice_composer.generate_invoice_number()
        
        # Set dates
        invoice_data['issue_date'] = datetime.now()
        invoice_data['due_date'] = datetime.now() + timedelta(days=30)
    
    else:  # Advanced mode
        invoice_data.update({
            'invoice_number': data.get('invoice_number') or invoice_composer.generate_invoice_number(),
            'po_number': data.get('po_number', ''),
            'issue_date': data.get('issue_date', datetime.now()),
            'due_date': data.get('due_date', datetime.now() + timedelta(days=30)),
            'line_items': data.get('line_items', []),
            'exchange_rate': data.get('exchange_rate', 1.0)
        })
    
    try:
        print("\n" + "="*60)
        print("🚀 Starting Invoice Generation")
        print("="*60)
        
        # Generate the PDF
        pdf_result = pdf_generator.generate_invoice(invoice_data)
        
        # Calculate total amount for display
        total_amount = 0
        currency = invoice_data.get('currency', 'USD')
        
        for item in invoice_data.get('line_items', []):
            quantity = item.get('quantity', 1)
            unit_price = item.get('unit_price', 0)
            discount_percent = item.get('discount_percent', 0)
            tax_rate = item.get('tax_rate', 0)
            
            subtotal = quantity * unit_price
            discount = subtotal * (discount_percent / 100)
            after_discount = subtotal - discount
            tax = after_discount * (tax_rate / 100)
            total_amount += after_discount + tax
        
        # Save invoice metadata to BigQuery
        try:
            file_info = {
                'file_size': os.path.getsize(pdf_result['local_path']) if pdf_result.get('local_path') else 0
            }
            
            bigquery_data = invoice_composer.prepare_invoice_for_bigquery(
                invoice_data,
                pdf_result['gcs_uri'],
                file_info
            )
            
            bq_service = BigQueryService()
            bq_service.insert_invoice(bigquery_data)
            print("✅ Invoice metadata saved to BigQuery")
        except Exception as bq_error:
            print(f"⚠️ BigQuery insert error (non-critical): {bq_error}")
            # Continue even if BigQuery insert fails
        
        # Prepare download URL
        download_url = f"/download/invoice/{pdf_result['filename']}"
        view_url = f"/view/invoice/{pdf_result['filename']}"
        
        print(f"✅ Invoice generation completed successfully!")
        print(f"   Invoice Number: {pdf_result['invoice_number']}")
        print(f"   Total Amount: {total_amount:.2f} {currency}")
        print(f"   GCS URI: {pdf_result.get('gcs_uri', 'N/A')}")
        print(f"   Download URL: {download_url}")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'invoice_number': pdf_result['invoice_number'],
            'filename': pdf_result['filename'],
            'gcs_uri': pdf_result.get('gcs_uri'),
            'public_url': pdf_result.get('public_url'),
            'local_path': pdf_result.get('local_path'),
            'download_url': download_url,
            'view_url': view_url,
            'vendor_name': invoice_data.get('vendor', {}).get('name', 'Unknown'),
            'total_amount': round(total_amount, 2),
            'currency': currency,
            'message': 'Invoice generated successfully!'
        })
        
    except Exception as e:
        print(f"❌ Invoice generation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/download/invoice/<filename>', methods=['GET'])
def download_generated_invoice(filename):
    """
    Download a generated invoice PDF
    """
    try:
        filepath = os.path.join('uploads', secure_filename(filename))
        if os.path.exists(filepath):
            from flask import send_file
            return send_file(filepath, as_attachment=True, download_name=filename, mimetype='application/pdf')
        else:
            return jsonify({'error': 'Invoice file not found'}), 404
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/view/invoice/<filename>', methods=['GET'])
def view_generated_invoice(filename):
    """
    View a generated invoice PDF in browser
    """
    try:
        filepath = os.path.join('uploads', secure_filename(filename))
        if os.path.exists(filepath):
            from flask import send_file
            return send_file(filepath, mimetype='application/pdf')
        else:
            return jsonify({'error': 'Invoice file not found'}), 404
    except Exception as e:
        print(f"View error: {e}")
        return jsonify({'error': str(e)}), 500

# NetSuite API Endpoints
@app.route('/api/netsuite/test', methods=['GET'])
def test_netsuite_connection():
    """
    Test NetSuite connection and authentication
    Returns connection status and available metadata
    """
    try:
        netsuite = NetSuiteService()
        result = netsuite.test_connection()
        
        # Try to ensure BigQuery tables have NetSuite fields (optional, non-critical)
        bigquery_status = 'Not tested'
        try:
            bigquery_service = BigQueryService()
            bigquery_service.ensure_table_schema()
            bigquery_service.ensure_invoices_table_with_netsuite()
            bigquery_status = 'NetSuite tracking fields ensured in BigQuery tables'
        except Exception as bq_error:
            print(f"❌ Error checking/creating BigQuery tables (non-critical): {bq_error}")
            bigquery_status = f'BigQuery update skipped: {str(bq_error)[:100]}'
        
        # Return NetSuite connection status (the main purpose of this endpoint)
        return jsonify({
            'success': result.get('connected', False),
            'connection_details': result,
            'message': 'NetSuite connection successful' if result.get('connected') else 'NetSuite connection failed',
            'bigquery_status': bigquery_status
        })
    except Exception as e:
        print(f"NetSuite test error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to test NetSuite connection'
        }), 500

@app.route('/api/netsuite/sync/vendor/<vendor_id>', methods=['POST'])
def sync_vendor_to_netsuite(vendor_id):
    """
    Manually sync a specific vendor to NetSuite
    Creates vendor in NetSuite if not exists, updates BigQuery with NetSuite ID
    """
    try:
        # Get vendor from BigQuery
        bigquery_service = BigQueryService()
        vendors = bigquery_service.search_vendor_by_id(vendor_id)
        
        if not vendors:
            return jsonify({
                'success': False,
                'error': 'Vendor not found in database',
                'vendor_id': vendor_id
            }), 404
        
        vendor = vendors[0]
        
        # Check if vendor already has NetSuite ID
        if vendor.get('netsuite_internal_id'):
            return jsonify({
                'success': True,
                'message': 'Vendor already synced to NetSuite',
                'vendor_id': vendor_id,
                'netsuite_id': vendor['netsuite_internal_id'],
                'action': 'already_synced'
            })
        
        # Sync to NetSuite
        netsuite = NetSuiteService()
        
        # Prepare vendor data for NetSuite
        vendor_data = {
            'name': vendor.get('global_name', ''),
            'external_id': vendor_id,
            'email': vendor.get('emails', [''])[0] if vendor.get('emails') else None
        }
        
        # Extract tax ID from custom attributes if available
        custom_attrs = vendor.get('custom_attributes', {})
        if custom_attrs:
            vendor_data['tax_id'] = custom_attrs.get('tax_id') or custom_attrs.get('vat_number')
            vendor_data['phone'] = custom_attrs.get('phone')
            
            # Extract address if available
            if custom_attrs.get('address'):
                vendor_data['address'] = {
                    'line1': custom_attrs.get('address'),
                    'city': custom_attrs.get('city', ''),
                    'state': custom_attrs.get('state', ''),
                    'postal_code': custom_attrs.get('postal_code', ''),
                    'country': custom_attrs.get('country', 'US')
                }
        
        # Sync to NetSuite
        sync_result = netsuite.sync_vendor_to_netsuite(vendor_data)
        
        if sync_result.get('success'):
            # Update BigQuery with NetSuite ID
            netsuite_id = sync_result.get('netsuite_id')
            if netsuite_id:
                bigquery_service.update_vendor_netsuite_id(vendor_id, netsuite_id)
            
            return jsonify({
                'success': True,
                'message': f"Vendor successfully synced to NetSuite",
                'vendor_id': vendor_id,
                'netsuite_id': netsuite_id,
                'action': sync_result.get('action', 'synced'),
                'vendor_name': vendor.get('global_name')
            })
        else:
            return jsonify({
                'success': False,
                'error': sync_result.get('error', 'Failed to sync vendor to NetSuite'),
                'vendor_id': vendor_id
            }), 500
            
    except Exception as e:
        print(f"NetSuite vendor sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'vendor_id': vendor_id
        }), 500

@app.route('/api/netsuite/sync/invoice/<invoice_id>', methods=['POST'])
def sync_invoice_to_netsuite(invoice_id):
    """
    Manually sync a specific invoice to NetSuite as a vendor bill
    Creates vendor in NetSuite if needed, then creates vendor bill
    """
    try:
        # Get invoice from BigQuery
        bigquery_service = BigQueryService()
        
        # Query invoice details
        query = f"""
        SELECT 
            invoice_id,
            vendor_id,
            vendor_name,
            amount,
            currency,
            invoice_date,
            metadata,
            netsuite_bill_id,
            netsuite_sync_status
        FROM `{config.GOOGLE_CLOUD_PROJECT_ID}.{bigquery_service.dataset_id}.invoices`
        WHERE invoice_id = @invoice_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id),
            ]
        )
        
        results = bigquery_service.client.query(query, job_config=job_config).result()
        invoice = None
        
        for row in results:
            # Parse metadata JSON
            metadata = {}
            if row.metadata:
                if isinstance(row.metadata, str):
                    try:
                        metadata = json.loads(row.metadata)
                    except:
                        metadata = {}
                elif isinstance(row.metadata, dict):
                    metadata = row.metadata
            
            invoice = {
                'invoice_id': row.invoice_id,
                'vendor_id': row.vendor_id,
                'vendor_name': row.vendor_name,
                'amount': float(row.amount) if row.amount else 0,
                'currency': row.currency or 'USD',
                'invoice_date': row.invoice_date.isoformat() if row.invoice_date else datetime.now().strftime('%Y-%m-%d'),
                'metadata': metadata,
                'netsuite_bill_id': row.netsuite_bill_id,
                'netsuite_sync_status': row.netsuite_sync_status
            }
            break
        
        if not invoice:
            return jsonify({
                'success': False,
                'error': 'Invoice not found in database',
                'invoice_id': invoice_id
            }), 404
        
        # Check if already synced
        if invoice.get('netsuite_bill_id'):
            return jsonify({
                'success': True,
                'message': 'Invoice already synced to NetSuite',
                'invoice_id': invoice_id,
                'netsuite_bill_id': invoice['netsuite_bill_id'],
                'action': 'already_synced'
            })
        
        netsuite = NetSuiteService()
        
        # First, ensure vendor is synced to NetSuite
        vendor_netsuite_id = None
        
        if invoice.get('vendor_id'):
            # Get vendor NetSuite ID
            vendor_netsuite_id = bigquery_service.get_vendor_netsuite_id(invoice['vendor_id'])
            
            if not vendor_netsuite_id:
                # Vendor not synced, sync it first
                print(f"Vendor {invoice['vendor_id']} not synced to NetSuite, syncing now...")
                
                # Get vendor details
                vendors = bigquery_service.search_vendor_by_id(invoice['vendor_id'])
                if vendors:
                    vendor = vendors[0]
                    vendor_data = {
                        'name': vendor.get('global_name', invoice.get('vendor_name', '')),
                        'external_id': invoice['vendor_id'],
                        'email': vendor.get('emails', [''])[0] if vendor.get('emails') else None
                    }
                    
                    # Extract additional fields from custom attributes
                    custom_attrs = vendor.get('custom_attributes', {})
                    if custom_attrs:
                        vendor_data['tax_id'] = custom_attrs.get('tax_id') or custom_attrs.get('vat_number')
                        vendor_data['phone'] = custom_attrs.get('phone')
                    
                    # Sync vendor to NetSuite
                    vendor_sync_result = netsuite.sync_vendor_to_netsuite(vendor_data)
                    
                    if vendor_sync_result.get('success'):
                        vendor_netsuite_id = vendor_sync_result.get('netsuite_id')
                        # Update vendor NetSuite ID in BigQuery
                        bigquery_service.update_vendor_netsuite_id(invoice['vendor_id'], vendor_netsuite_id)
                    else:
                        return jsonify({
                            'success': False,
                            'error': f"Failed to sync vendor to NetSuite: {vendor_sync_result.get('error')}",
                            'invoice_id': invoice_id
                        }), 500
        
        if not vendor_netsuite_id:
            # Try to find vendor by name if no ID
            if invoice.get('vendor_name'):
                search_results = netsuite.search_vendors(name=invoice['vendor_name'])
                if search_results:
                    vendor_netsuite_id = search_results[0].get('id')
        
        if not vendor_netsuite_id:
            return jsonify({
                'success': False,
                'error': 'Could not find or create vendor in NetSuite',
                'invoice_id': invoice_id
            }), 400
        
        # Prepare invoice data for NetSuite
        invoice_data = {
            'invoice_id': invoice_id,
            'invoiceNumber': metadata.get('invoice_number', invoice_id),
            'invoiceDate': invoice.get('invoice_date'),
            'currency': invoice.get('currency', 'USD'),
            'totals': {
                'total': invoice.get('amount', 0)
            }
        }
        
        # Add line items if available in metadata
        if metadata.get('line_items'):
            invoice_data['lineItems'] = metadata['line_items']
        
        # Sync invoice to NetSuite
        sync_result = netsuite.sync_invoice_to_netsuite(invoice_data, vendor_netsuite_id)
        
        if sync_result.get('success'):
            # Update BigQuery with NetSuite bill ID
            netsuite_bill_id = sync_result.get('netsuite_bill_id')
            if netsuite_bill_id:
                bigquery_service.update_invoice_netsuite_sync(
                    invoice_id, 
                    netsuite_bill_id,
                    'synced'
                )
            
            return jsonify({
                'success': True,
                'message': f"Invoice successfully synced to NetSuite as vendor bill",
                'invoice_id': invoice_id,
                'netsuite_bill_id': netsuite_bill_id,
                'vendor_netsuite_id': vendor_netsuite_id,
                'action': sync_result.get('action', 'synced'),
                'amount': invoice.get('amount'),
                'currency': invoice.get('currency')
            })
        else:
            # Update sync status as failed
            bigquery_service.update_invoice_netsuite_sync(
                invoice_id, 
                '',
                'failed'
            )
            
            return jsonify({
                'success': False,
                'error': sync_result.get('error', 'Failed to sync invoice to NetSuite'),
                'invoice_id': invoice_id
            }), 500
            
    except Exception as e:
        print(f"NetSuite invoice sync error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'invoice_id': invoice_id
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
