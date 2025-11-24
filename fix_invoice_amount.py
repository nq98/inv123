#!/usr/bin/env python3
"""Fix invoice 0000212 amount in BigQuery"""

import os
from google.cloud import bigquery
from google.oauth2 import service_account
import json

# Setup BigQuery client
credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if credentials_json:
    credentials_dict = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
    client = bigquery.Client(credentials=credentials, project='invoicereader-477008')
else:
    client = bigquery.Client(project='invoicereader-477008')

# First, check current invoice data
query = """
SELECT 
    invoice_id,
    vendor_id,
    total_amount,
    subtotal,
    currency,
    invoice_date,
    raw_extracted_data
FROM `invoicereader-477008.vendors_ai.invoices`
WHERE invoice_id = '0000212'
"""

print("Checking current invoice data...")
results = client.query(query).result()

for row in results:
    print(f"\nInvoice found:")
    print(f"  Invoice ID: {row.invoice_id}")
    print(f"  Vendor ID: {row.vendor_id}")
    print(f"  Total Amount: {row.total_amount}")
    print(f"  Subtotal: {row.subtotal}")
    print(f"  Currency: {row.currency}")
    print(f"  Invoice Date: {row.invoice_date}")
    
    # Parse raw extracted data to see if amount is there
    if row.raw_extracted_data:
        try:
            raw_data = json.loads(row.raw_extracted_data) if isinstance(row.raw_extracted_data, str) else row.raw_extracted_data
            print(f"  Raw data contains: {list(raw_data.keys())}")
            
            # Check for amount in various fields
            for field in ['total_amount', 'total', 'amount', 'grand_total', 'subtotal']:
                if field in raw_data:
                    print(f"    {field}: {raw_data[field]}")
        except:
            pass

# Update the invoice with correct amount
update_query = """
UPDATE `invoicereader-477008.vendors_ai.invoices`
SET 
    total_amount = 67.25,
    subtotal = 67.25
WHERE invoice_id = '0000212'
"""

print("\nUpdating invoice amount to $67.25...")
try:
    client.query(update_query).result()
    print("✅ Invoice amount updated successfully!")
except Exception as e:
    print(f"❌ Error updating invoice: {e}")

# Verify the update
verify_query = """
SELECT 
    invoice_id,
    total_amount,
    subtotal
FROM `invoicereader-477008.vendors_ai.invoices`  
WHERE invoice_id = '0000212'
"""

print("\nVerifying update...")
results = client.query(verify_query).result()

for row in results:
    print(f"Updated invoice:")
    print(f"  Invoice ID: {row.invoice_id}")
    print(f"  Total Amount: ${row.total_amount}")
    print(f"  Subtotal: ${row.subtotal}")