"""
Invoice Management API Endpoints
Ready-to-use Flask routes for Invoice Management

Copy these endpoints to your main Flask app file.
"""

import os
import json
import csv
import io
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_file, session

logger = logging.getLogger(__name__)


def login_required(f):
    """Decorator - replace with your auth system"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_email'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def register_invoice_routes(app):
    """Register all invoice management routes with the Flask app"""
    
    @app.route('/api/invoices/upload', methods=['POST'])
    @login_required
    def upload_invoice():
        """
        Upload and parse a single invoice PDF
        
        Request: multipart/form-data with 'file' field
        Returns: Extracted invoice data with invoice_id
        """
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
        
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400
        
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            file_content = file.read()
            user_email = session.get('user_email', 'unknown@example.com')
            
            result = parser.parse_invoice(file_content, file.filename, user_email)
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Invoice upload error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/upload/bulk', methods=['POST'])
    @login_required
    def upload_invoices_bulk():
        """
        Upload and parse multiple invoice PDFs
        
        Request: multipart/form-data with 'files[]' field (multiple files)
        Returns: Summary with results for each file
        """
        if 'files[]' not in request.files:
            return jsonify({'status': 'error', 'message': 'No files provided'}), 400
        
        files = request.files.getlist('files[]')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'status': 'error', 'message': 'No files selected'}), 400
        
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg'}
        
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            user_email = session.get('user_email', 'unknown@example.com')
            
            file_list = []
            for file in files:
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in allowed_extensions:
                    file_list.append((file.read(), file.filename))
            
            if not file_list:
                return jsonify({'status': 'error', 'message': 'No valid files'}), 400
            
            result = parser.parse_invoices_bulk(file_list, user_email)
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Bulk upload error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices', methods=['GET'])
    @login_required
    def list_invoices():
        """
        Get paginated list of invoices with filters
        
        Query params: page, limit, status, payment_type, currency, 
                      date_from, date_to, search, sort_by, sort_order
        """
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 50, type=int)
            status = request.args.get('status')
            payment_type = request.args.get('payment_type')
            currency = request.args.get('currency')
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            search = request.args.get('search', '')
            sort_by = request.args.get('sort_by', 'created_at')
            sort_order = request.args.get('sort_order', 'desc')
            
            user_email = session.get('user_email')
            
            result = parser.list_invoices(
                user_email=user_email,
                page=page,
                limit=limit,
                status=status,
                payment_type=payment_type,
                currency=currency,
                date_from=date_from,
                date_to=date_to,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"List invoices error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/<invoice_id>', methods=['GET'])
    @login_required
    def get_invoice(invoice_id):
        """Get detailed invoice information"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            result = parser.get_invoice(invoice_id)
            if not result:
                return jsonify({'status': 'error', 'message': 'Invoice not found'}), 404
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Get invoice error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/<invoice_id>', methods=['PUT'])
    @login_required
    def update_invoice(invoice_id):
        """Update invoice data"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            data = request.get_json()
            user_email = session.get('user_email')
            
            result = parser.update_invoice(invoice_id, data, user_email)
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Update invoice error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/<invoice_id>/approve', methods=['POST'])
    @login_required
    def approve_invoice(invoice_id):
        """Approve an invoice for payment"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            data = request.get_json() or {}
            user_email = session.get('user_email')
            scheduled_date = data.get('scheduled_date')
            notes = data.get('notes')
            
            result = parser.approve_invoice(
                invoice_id, 
                user_email, 
                scheduled_date=scheduled_date,
                notes=notes
            )
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Approve invoice error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/<invoice_id>/reject', methods=['POST'])
    @login_required
    def reject_invoice(invoice_id):
        """Reject an invoice"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            data = request.get_json()
            if not data or not data.get('reason'):
                return jsonify({'status': 'error', 'message': 'Rejection reason required'}), 400
            
            user_email = session.get('user_email')
            reason = data.get('reason')
            
            result = parser.reject_invoice(invoice_id, user_email, reason)
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Reject invoice error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/<invoice_id>/download', methods=['GET'])
    @login_required
    def download_invoice_pdf(invoice_id):
        """Get signed URL to download original invoice PDF"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            url = parser.get_download_url(invoice_id)
            if not url:
                return jsonify({'status': 'error', 'message': 'PDF not found'}), 404
            
            return jsonify({
                'status': 'success',
                'download_url': url,
                'expires_in': 3600
            })
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/export', methods=['GET'])
    @login_required
    def export_invoices():
        """Export invoices to CSV"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            user_email = session.get('user_email')
            status = request.args.get('status')
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            
            invoices = parser.list_invoices(
                user_email=user_email,
                status=status,
                date_from=date_from,
                date_to=date_to,
                limit=10000
            ).get('invoices', [])
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                'invoice_id', 'invoice_number', 'vendor_name', 'amount', 
                'currency', 'invoice_date', 'due_date', 'status', 
                'payment_type', 'category', 'description'
            ])
            writer.writeheader()
            
            for inv in invoices:
                writer.writerow({
                    'invoice_id': inv.get('invoice_id'),
                    'invoice_number': inv.get('invoice_number'),
                    'vendor_name': inv.get('vendor_name'),
                    'amount': inv.get('amount'),
                    'currency': inv.get('currency'),
                    'invoice_date': inv.get('invoice_date'),
                    'due_date': inv.get('due_date'),
                    'status': inv.get('status'),
                    'payment_type': inv.get('payment_type'),
                    'category': inv.get('category'),
                    'description': inv.get('description')
                })
            
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'invoices_{datetime.now().strftime("%Y%m%d")}.csv'
            )
            
        except Exception as e:
            logger.error(f"Export error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/invoices/summary', methods=['GET'])
    @login_required
    def get_invoice_summary():
        """Get invoice summary statistics"""
        try:
            from services.invoice_parser_service import InvoiceParserService
            parser = InvoiceParserService()
            
            user_email = session.get('user_email')
            result = parser.get_summary(user_email)
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Summary error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    return app
