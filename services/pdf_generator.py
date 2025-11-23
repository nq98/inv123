"""
PDF Invoice Generator Service
Generates professional A4 PDF invoices using ReportLab
"""

import os
import io
import json
import uuid
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, KeepTogether
from google.cloud import storage
from google.oauth2 import service_account
from config import config


class PDFInvoiceGenerator:
    """
    Generates professional PDF invoices with support for:
    - Multi-currency
    - Multiple tax rates (VAT, Sales Tax, GST)
    - Line items with discounts
    - Professional formatting
    """
    
    def __init__(self):
        """Initialize the PDF generator with GCS credentials"""
        # Set up Google Cloud Storage client
        credentials = None
        
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except json.JSONDecodeError:
                print("Warning: Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        
        self.storage_client = storage.Client(
            project=config.GOOGLE_CLOUD_PROJECT_ID,
            credentials=credentials
        )
        self.bucket_name = config.GCS_INPUT_BUCKET
        self.bucket = self.storage_client.bucket(self.bucket_name)
        
        # Invoice styling
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles for the invoice"""
        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1E293B'),
            spaceAfter=30,
            alignment=TA_LEFT
        ))
        
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Normal'],
            fontSize=18,
            textColor=colors.HexColor('#1E293B'),
            fontName='Helvetica-Bold',
            spaceAfter=10
        ))
        
        self.styles.add(ParagraphStyle(
            name='CompanyDetails',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#64748B'),
            leading=14
        ))
        
        self.styles.add(ParagraphStyle(
            name='InvoiceInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1E293B'),
            alignment=TA_RIGHT
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1E293B'),
            fontName='Helvetica-Bold',
            spaceAfter=10,
            spaceBefore=20
        ))
    
    def generate_invoice(self, invoice_data):
        """
        Generate a professional PDF invoice
        
        Args:
            invoice_data: Dictionary containing invoice details with structure:
                {
                    'invoice_number': str,
                    'issue_date': datetime or str,
                    'due_date': datetime or str,
                    'vendor': {
                        'name': str,
                        'address': str,
                        'city': str,
                        'country': str,
                        'tax_id': str,
                        'email': str,
                        'phone': str
                    },
                    'buyer': {
                        'name': str,
                        'address': str,
                        'city': str,
                        'country': str,
                        'tax_id': str
                    },
                    'line_items': [
                        {
                            'description': str,
                            'quantity': float,
                            'unit_price': float,
                            'discount_percent': float,
                            'tax_rate': float,
                            'tracking_category': str
                        }
                    ],
                    'currency': str,
                    'exchange_rate': float,
                    'payment_terms': str,
                    'po_number': str,
                    'notes': str,
                    'tax_type': str  # 'VAT', 'Sales Tax', 'GST', 'None'
                }
        
        Returns:
            dict with 'gcs_uri' and 'local_path' of generated PDF
        """
        # Generate unique filename
        invoice_number = invoice_data.get('invoice_number', f"AUTO_GEN_{uuid.uuid4().hex[:8].upper()}")
        filename = f"invoice_{invoice_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Create PDF in memory
        buffer = io.BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        # Build the invoice content
        elements = []
        
        # Add invoice header
        elements.extend(self._create_header(invoice_data))
        
        # Add vendor and buyer information
        elements.extend(self._create_parties_section(invoice_data))
        
        # Add line items table
        elements.extend(self._create_line_items_table(invoice_data))
        
        # Add totals section
        elements.extend(self._create_totals_section(invoice_data))
        
        # Add notes and payment terms
        elements.extend(self._create_footer_section(invoice_data))
        
        # Build PDF
        doc.build(elements)
        
        # Save to GCS
        buffer.seek(0)
        gcs_path = f"generated/{filename}"
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_file(buffer, content_type='application/pdf')
        
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        
        # Also save locally for immediate access
        local_path = os.path.join('uploads', filename)
        buffer.seek(0)
        with open(local_path, 'wb') as f:
            f.write(buffer.getvalue())
        
        return {
            'gcs_uri': gcs_uri,
            'local_path': local_path,
            'filename': filename,
            'invoice_number': invoice_number
        }
    
    def _create_header(self, invoice_data):
        """Create the invoice header with title and invoice details"""
        elements = []
        
        # Invoice title
        elements.append(Paragraph("INVOICE", self.styles['InvoiceTitle']))
        
        # Invoice details table
        invoice_info_data = [
            ['Invoice Number:', invoice_data.get('invoice_number', 'AUTO_GEN_' + uuid.uuid4().hex[:8].upper())],
            ['Issue Date:', self._format_date(invoice_data.get('issue_date', datetime.now()))],
            ['Due Date:', self._format_date(invoice_data.get('due_date', datetime.now() + timedelta(days=30)))],
        ]
        
        if invoice_data.get('po_number'):
            invoice_info_data.append(['PO Number:', invoice_data.get('po_number')])
        
        invoice_info_table = Table(invoice_info_data, colWidths=[100, 150])
        invoice_info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1E293B')),
        ]))
        
        # Create a container table to align invoice info to the right
        container_data = [['', invoice_info_table]]
        container_table = Table(container_data, colWidths=[300, 250])
        container_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(container_table)
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _create_parties_section(self, invoice_data):
        """Create the vendor and buyer information section"""
        elements = []
        
        vendor = invoice_data.get('vendor', {})
        buyer = invoice_data.get('buyer', {})
        
        # Vendor information
        vendor_text = f"""<b>{vendor.get('name', 'Vendor Name')}</b><br/>
        {vendor.get('address', '')} <br/>
        {vendor.get('city', '')}, {vendor.get('country', '')} <br/>"""
        
        if vendor.get('tax_id'):
            vendor_text += f"Tax ID: {vendor.get('tax_id')}<br/>"
        if vendor.get('email'):
            vendor_text += f"Email: {vendor.get('email')}<br/>"
        if vendor.get('phone'):
            vendor_text += f"Phone: {vendor.get('phone')}"
        
        # Buyer information
        buyer_text = f"""<b>{buyer.get('name', 'Buyer Name')}</b><br/>
        {buyer.get('address', '')} <br/>
        {buyer.get('city', '')}, {buyer.get('country', '')} <br/>"""
        
        if buyer.get('tax_id'):
            buyer_text += f"Tax ID: {buyer.get('tax_id')}"
        
        # Create side-by-side layout
        parties_data = [
            [Paragraph("FROM", self.styles['SectionHeading']), 
             Paragraph("BILL TO", self.styles['SectionHeading'])],
            [Paragraph(vendor_text, self.styles['CompanyDetails']),
             Paragraph(buyer_text, self.styles['CompanyDetails'])]
        ]
        
        parties_table = Table(parties_data, colWidths=[275, 275])
        parties_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ]))
        
        elements.append(parties_table)
        elements.append(Spacer(1, 30))
        
        return elements
    
    def _create_line_items_table(self, invoice_data):
        """Create the line items table"""
        elements = []
        
        # Table headers
        headers = ['Description', 'Qty', 'Unit Price', 'Discount', 'Tax', 'Amount']
        
        # Prepare table data
        table_data = [headers]
        
        currency = invoice_data.get('currency', 'USD')
        currency_symbol = self._get_currency_symbol(currency)
        
        line_items = invoice_data.get('line_items', [])
        
        for item in line_items:
            quantity = item.get('quantity', 1)
            unit_price = item.get('unit_price', 0)
            discount_percent = item.get('discount_percent', 0)
            tax_rate = item.get('tax_rate', 0)
            
            # Calculate line total
            subtotal = quantity * unit_price
            discount_amount = subtotal * (discount_percent / 100)
            after_discount = subtotal - discount_amount
            tax_amount = after_discount * (tax_rate / 100)
            total = after_discount + tax_amount
            
            row = [
                item.get('description', ''),
                f"{quantity:.2f}",
                f"{currency_symbol}{unit_price:,.2f}",
                f"{discount_percent:.1f}%" if discount_percent > 0 else '-',
                f"{tax_rate:.1f}%" if tax_rate > 0 else '-',
                f"{currency_symbol}{total:,.2f}"
            ]
            table_data.append(row)
        
        # Create the table
        line_items_table = Table(table_data, colWidths=[200, 50, 80, 60, 60, 100])
        
        # Apply table styling
        style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),
            
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#475569')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ])
        
        # Add alternating row colors
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC'))
        
        line_items_table.setStyle(style)
        
        elements.append(Paragraph("Items", self.styles['SectionHeading']))
        elements.append(line_items_table)
        elements.append(Spacer(1, 20))
        
        return elements
    
    def _create_totals_section(self, invoice_data):
        """Create the totals section with subtotal, tax, and grand total"""
        elements = []
        
        currency = invoice_data.get('currency', 'USD')
        currency_symbol = self._get_currency_symbol(currency)
        
        # Calculate totals
        subtotal = 0
        total_tax = 0
        total_discount = 0
        
        for item in invoice_data.get('line_items', []):
            quantity = item.get('quantity', 1)
            unit_price = item.get('unit_price', 0)
            discount_percent = item.get('discount_percent', 0)
            tax_rate = item.get('tax_rate', 0)
            
            line_subtotal = quantity * unit_price
            discount_amount = line_subtotal * (discount_percent / 100)
            after_discount = line_subtotal - discount_amount
            tax_amount = after_discount * (tax_rate / 100)
            
            subtotal += line_subtotal
            total_discount += discount_amount
            total_tax += tax_amount
        
        grand_total = subtotal - total_discount + total_tax
        
        # Create totals table
        totals_data = []
        
        totals_data.append(['Subtotal:', f"{currency_symbol}{subtotal:,.2f}"])
        
        if total_discount > 0:
            totals_data.append(['Discount:', f"-{currency_symbol}{total_discount:,.2f}"])
        
        tax_type = invoice_data.get('tax_type', 'Tax')
        if total_tax > 0:
            totals_data.append([f"{tax_type}:", f"{currency_symbol}{total_tax:,.2f}"])
        
        # Add separator
        totals_data.append(['', ''])
        
        # Grand total
        totals_data.append(['TOTAL:', f"{currency_symbol}{grand_total:,.2f}"])
        
        totals_table = Table(totals_data, colWidths=[100, 150])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -3), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -3), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -3), 10),
            ('TEXTCOLOR', (0, 0), (-1, -3), colors.HexColor('#64748B')),
            
            # Separator line
            ('LINEBELOW', (0, -2), (-1, -2), 1, colors.HexColor('#CBD5E1')),
            
            # Grand total styling
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 14),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#1E293B')),
            ('TOPPADDING', (0, -1), (-1, -1), 10),
        ]))
        
        # Align to right
        container_data = [['', totals_table]]
        container_table = Table(container_data, colWidths=[300, 250])
        container_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(container_table)
        elements.append(Spacer(1, 30))
        
        return elements
    
    def _create_footer_section(self, invoice_data):
        """Create the footer with payment terms and notes"""
        elements = []
        
        # Payment terms
        payment_terms = invoice_data.get('payment_terms', 'Net 30')
        elements.append(Paragraph("Payment Terms", self.styles['SectionHeading']))
        elements.append(Paragraph(payment_terms, self.styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Notes
        notes = invoice_data.get('notes', '')
        if notes:
            elements.append(Paragraph("Notes", self.styles['SectionHeading']))
            elements.append(Paragraph(notes, self.styles['Normal']))
            elements.append(Spacer(1, 20))
        
        # Footer text
        footer_text = "This is a computer-generated invoice and does not require a signature."
        footer_style = ParagraphStyle(
            'Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#94A3B8'),
            alignment=TA_CENTER
        )
        elements.append(Spacer(1, 40))
        elements.append(Paragraph(footer_text, footer_style))
        
        return elements
    
    def _format_date(self, date_value):
        """Format date for display"""
        if isinstance(date_value, str):
            try:
                date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            except:
                return date_value
        
        if isinstance(date_value, datetime):
            return date_value.strftime('%B %d, %Y')
        
        return str(date_value)
    
    def _get_currency_symbol(self, currency_code):
        """Get currency symbol from currency code"""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'AUD': 'A$',
            'CHF': 'CHF',
            'CNY': '¥',
            'INR': '₹',
            'ILS': '₪',
            'MXN': '$',
            'BRL': 'R$',
            'ZAR': 'R',
            'SEK': 'kr',
            'NOK': 'kr',
            'DKK': 'kr',
            'NZD': 'NZ$',
            'SGD': 'S$',
            'HKD': 'HK$',
            'KRW': '₩',
            'TRY': '₺',
            'RUB': '₽',
            'PLN': 'zł',
            'THB': '฿',
            'MYR': 'RM',
            'PHP': '₱',
            'IDR': 'Rp',
            'CZK': 'Kč',
            'HUF': 'Ft',
            'AED': 'د.إ',
            'SAR': '﷼',
            'QAR': '﷼',
            'KWD': 'د.ك',
            'EGP': 'E£',
            'NGN': '₦',
            'KES': 'KSh',
            'GHS': '₵',
            'MAD': 'د.م.',
            'ARS': '$',
            'CLP': '$',
            'COP': '$',
            'PEN': 'S/',
            'UAH': '₴',
            'PKR': '₨',
            'BDT': '৳',
            'VND': '₫',
            'TWD': 'NT$'
        }
        
        return currency_symbols.get(currency_code, currency_code + ' ')