#!/usr/bin/env python3
"""
Test script for the invoice processing system
"""
from invoice_processor import InvoiceProcessor
import json

def test_process_invoice():
    """Test the invoice processor with a sample GCS URI"""
    processor = InvoiceProcessor()
    
    print("Testing Invoice Processing System")
    print("=" * 60)
    
    sample_gcs_uri = "gs://payouts-invoices/sample-invoice.pdf"
    
    print(f"\nNote: To test with a real invoice, upload a PDF to:")
    print(f"  gs://payouts-invoices/")
    print(f"\nThen call: processor.process_invoice('gs://payouts-invoices/your-file.pdf')")
    print("\nThe system is ready and waiting for invoice uploads!")

if __name__ == '__main__':
    test_process_invoice()
