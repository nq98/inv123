#!/usr/bin/env python3
"""Test script to generate a test invoice via the API"""

import json
import requests
from datetime import datetime, timedelta

# API endpoint
BASE_URL = "http://localhost:5000"

def test_generate_simple_invoice():
    """Test generating a simple invoice"""
    
    # Prepare test invoice data
    invoice_data = {
        "mode": "simple",
        "vendor": {
            "name": "Acme Corporation",
            "address": "123 Tech Street",
            "city": "San Francisco",
            "country": "USA",
            "tax_id": "TAX-123456",
            "email": "billing@acme.com",
            "phone": "+1 555-0123"
        },
        "description": "Web Development Services",
        "amount": 1500.00,
        "currency": "USD",
        "tax_type": "vat",
        "buyer": {
            "name": "MyCompany Inc.",
            "address": "",
            "city": "",
            "country": "",
            "tax_id": ""
        }
    }
    
    print("🚀 Testing invoice generation...")
    print(f"   Vendor: {invoice_data['vendor']['name']}")
    print(f"   Amount: ${invoice_data['amount']} {invoice_data['currency']}")
    print(f"   Tax Type: {invoice_data['tax_type'].upper()}")
    print()
    
    # Send request
    try:
        response = requests.post(
            f"{BASE_URL}/api/invoice/generate",
            json=invoice_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Invoice generated successfully!")
            print(f"   Invoice Number: {result.get('invoice_number', 'N/A')}")
            print(f"   Filename: {result.get('filename', 'N/A')}")
            print(f"   GCS URI: {result.get('gcs_uri', 'N/A')}")
            print(f"   Download URL: {result.get('download_url', 'N/A')}")
            print(f"   Total Amount: ${result.get('total_amount', 0)} {result.get('currency', 'USD')}")
            
            # Test download endpoint
            if result.get('download_url'):
                print(f"\n📥 Testing download from: {result['download_url']}")
                download_response = requests.get(BASE_URL + result['download_url'])
                if download_response.status_code == 200:
                    print("✅ Download endpoint works!")
                else:
                    print(f"❌ Download failed: {download_response.status_code}")
        else:
            print(f"❌ Generation failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_generate_simple_invoice()
