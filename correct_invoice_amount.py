#!/usr/bin/env python3
"""Correct invoice 0000212 amount to the actual $300 from the PDF"""

import os
from google.cloud import bigquery
from google.oauth2 import service_account
import json
from datetime import datetime, date

# Setup BigQuery client
credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if credentials_json:
    credentials_dict = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
    client = bigquery.Client(credentials=credentials, project='invoicereader-477008')
else:
    client = bigquery.Client(project='invoicereader-477008')

print("🔧 CORRECTING INVOICE AMOUNT TO ACTUAL VALUE FROM PDF")
print("=" * 60)

# Update the invoice with CORRECT amount from the actual invoice PDF
update_query = """
UPDATE `invoicereader-477008.vendors_ai.invoices`
SET 
    amount = 300.00,
    invoice_date = DATE('2025-08-25')
WHERE invoice_id = '0000212'
"""

print("📄 Invoice 0000212 - Actual values from PDF:")
print("  - Invoice Total: $300.00 (not $67.25)")
print("  - Issue Date: August 25, 2025")
print("  - Vendor: Artem Andreevitch Revva")
print("\nUpdating to correct amount...")

try:
    client.query(update_query).result()
    print("✅ Invoice amount corrected successfully!")
except Exception as e:
    print(f"❌ Error updating invoice: {e}")
    raise

# Verify the update
verify_query = """
SELECT 
    invoice_id,
    vendor_id,
    vendor_name,
    amount,
    currency,
    invoice_date
FROM `invoicereader-477008.vendors_ai.invoices`  
WHERE invoice_id = '0000212'
"""

print("\nVerifying correction...")
results = client.query(verify_query).result()

for row in results:
    print(f"\n✅ CORRECTED INVOICE DATA:")
    print(f"  Invoice ID: {row.invoice_id}")
    print(f"  Vendor: {row.vendor_name} (ID: {row.vendor_id})")
    print(f"  Amount: ${row.amount:.2f} {row.currency}")
    print(f"  Invoice Date: {row.invoice_date}")
    
print("\n🎯 Invoice ready for NetSuite sync with CORRECT amount of $300!")
print("=" * 60)