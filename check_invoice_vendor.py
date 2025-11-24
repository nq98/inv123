#!/usr/bin/env python3
"""Check and fix invoice 0000212 vendor linkage"""

from google.cloud import bigquery
import os
import json

# Load credentials
credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if credentials_json:
    credentials_dict = json.loads(credentials_json)
    with open('/tmp/service_account.json', 'w') as f:
        json.dump(credentials_dict, f)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/service_account.json'

client = bigquery.Client(project="invoicereader-477008")

# Check invoice current vendor_id
print("Checking invoice 0000212 current vendor_id...")
query1 = """
SELECT invoice_id, vendor_id, vendor_name 
FROM `invoicereader-477008.vendors_ai.invoices` 
WHERE invoice_id = '0000212'
"""
results1 = client.query(query1).result()
for row in results1:
    print(f"Invoice: {row.invoice_id}")
    print(f"Current vendor_id: {row.vendor_id}")
    print(f"Vendor name: {row.vendor_name}")

# Check vendor with NetSuite ID
print("\nChecking vendor with NetSuite ID 982...")
query2 = """
SELECT vendor_id, global_name, netsuite_internal_id 
FROM `invoicereader-477008.vendors_ai.global_vendors` 
WHERE netsuite_internal_id = '982' OR vendor_id = 'AUTO_ARTEM_ANDREEVITCH_RE_27'
"""
results2 = client.query(query2).result()
for row in results2:
    print(f"Vendor ID: {row.vendor_id}")
    print(f"Name: {row.global_name}")
    print(f"NetSuite ID: {row.netsuite_internal_id}")

# Update invoice to link to correct vendor
print("\nUpdating invoice 0000212 to link to vendor AUTO_ARTEM_ANDREEVITCH_RE_27...")
update_query = """
UPDATE `invoicereader-477008.vendors_ai.invoices`
SET vendor_id = 'AUTO_ARTEM_ANDREEVITCH_RE_27',
    updated_at = CURRENT_TIMESTAMP()
WHERE invoice_id = '0000212'
"""
try:
    result = client.query(update_query).result()
    print("✅ Invoice updated successfully!")
except Exception as e:
    print(f"❌ Update failed: {e}")

# Verify the update
print("\nVerifying the update...")
verify_query = """
SELECT i.invoice_id, i.vendor_id, i.vendor_name, 
       v.global_name, v.netsuite_internal_id
FROM `invoicereader-477008.vendors_ai.invoices` i
LEFT JOIN `invoicereader-477008.vendors_ai.global_vendors` v
  ON i.vendor_id = v.vendor_id
WHERE i.invoice_id = '0000212'
"""
results3 = client.query(verify_query).result()
for row in results3:
    print(f"Invoice: {row.invoice_id}")
    print(f"Vendor ID: {row.vendor_id}")
    print(f"Vendor Name (from invoice): {row.vendor_name}")
    print(f"Vendor Name (from vendor table): {row.global_name}")
    print(f"NetSuite ID: {row.netsuite_internal_id}")
    
print("\n✅ Done! Invoice 0000212 is now properly linked to vendor with NetSuite ID 982")