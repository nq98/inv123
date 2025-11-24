#!/usr/bin/env python3
"""Fix invoice 0000212 amount and date in BigQuery"""

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

# Update the invoice with correct amount and date
update_query = """
UPDATE `invoicereader-477008.vendors_ai.invoices`
SET 
    amount = 67.25,
    invoice_date = DATE('2025-07-01')
WHERE invoice_id = '0000212'
"""

print("Updating invoice 0000212...")
print("  - Setting amount to $67.25")
print("  - Setting invoice date to 2025-07-01")

try:
    client.query(update_query).result()
    print("✅ Invoice updated successfully!")
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

print("\nVerifying update...")
results = client.query(verify_query).result()

for row in results:
    print(f"\n✅ Updated invoice:")
    print(f"  Invoice ID: {row.invoice_id}")
    print(f"  Vendor: {row.vendor_name} (ID: {row.vendor_id})")
    print(f"  Amount: ${row.amount} {row.currency}")
    print(f"  Invoice Date: {row.invoice_date}")
    
print("\n🎯 Invoice ready for NetSuite sync!")