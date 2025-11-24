#!/usr/bin/env python3
"""Check invoice schema and data in BigQuery"""

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

# Check table schema first
print("Checking invoices table schema...")
table_ref = client.dataset('vendors_ai').table('invoices')
table = client.get_table(table_ref)

print("\nTable schema fields:")
for field in table.schema:
    print(f"  - {field.name}: {field.field_type}")

# Now check for invoice 0000212
query = """
SELECT *
FROM `invoicereader-477008.vendors_ai.invoices`
WHERE invoice_id = '0000212'
LIMIT 1
"""

print("\n\nChecking invoice 0000212 data...")
try:
    results = client.query(query).result()
    
    for row in results:
        print(f"\nInvoice found:")
        row_dict = dict(row)
        for key, value in row_dict.items():
            if key != 'raw_extracted_data':
                print(f"  {key}: {value}")
            else:
                print(f"  raw_extracted_data: <json data>")
                
        # Check raw extracted data separately
        if 'raw_extracted_data' in row_dict and row_dict['raw_extracted_data']:
            try:
                raw_data = json.loads(row_dict['raw_extracted_data']) if isinstance(row_dict['raw_extracted_data'], str) else row_dict['raw_extracted_data']
                print(f"\n  Raw extracted data fields:")
                for field in ['total_amount', 'total', 'amount', 'grand_total', 'subtotal']:
                    if field in raw_data:
                        print(f"    {field}: {raw_data[field]}")
            except Exception as e:
                print(f"  Could not parse raw data: {e}")
                
except Exception as e:
    print(f"Error: {e}")