#!/usr/bin/env python3
"""Test BigQuery schema and data to debug invoice amount issue"""

import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

# Setup credentials
sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
if sa_json:
    sa_info = json.loads(sa_json)
    credentials = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
else:
    credentials = service_account.Credentials.from_service_account_file(
        'vertex-runner.json',
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

client = bigquery.Client(
    credentials=credentials,
    project='invoicereader-477008'
)

print("=" * 60)
print("TESTING BIGQUERY INVOICE TABLE SCHEMA AND DATA")
print("=" * 60)

# Check table schema
try:
    table_ref = client.dataset('vendors_ai').table('invoices')
    table = client.get_table(table_ref)
    
    print("\nTable Schema:")
    print("-" * 40)
    for field in table.schema:
        print(f"  {field.name}: {field.field_type} ({field.mode})")
    
except Exception as e:
    print(f"Error getting table schema: {e}")

# Check sample data to see what columns have values
print("\n" + "=" * 60)
print("SAMPLE INVOICE DATA (first 3 records):")
print("-" * 40)

query = """
    SELECT *
    FROM `invoicereader-477008.vendors_ai.invoices`
    LIMIT 3
"""

try:
    results = client.query(query).result()
    
    for i, row in enumerate(results):
        print(f"\n--- Invoice {i+1} ---")
        # Print all fields dynamically
        for field in row.keys():
            value = row[field]
            if value is not None:
                print(f"  {field}: {value}")
            else:
                print(f"  {field}: NULL")
                
except Exception as e:
    print(f"Error querying data: {e}")

# Check specifically for amount-related columns
print("\n" + "=" * 60)
print("CHECKING AMOUNT COLUMNS:")
print("-" * 40)

amount_query = """
    SELECT 
        invoice_id,
        amount,
        total_amount,
        currency
    FROM `invoicereader-477008.vendors_ai.invoices`
    WHERE invoice_id IN ('SO25041816', 'A30816A8-0048')
"""

try:
    results = client.query(amount_query).result()
    
    for row in results:
        print(f"\nInvoice: {row.invoice_id}")
        print(f"  amount: {row.get('amount', 'Column not found')}")
        print(f"  total_amount: {row.get('total_amount', 'Column not found')}")
        print(f"  currency: {row.get('currency', 'Column not found')}")
        
except Exception as e:
    print(f"Error checking amount columns: {e}")
    # If the query fails, try a simpler one
    print("\nTrying alternative query...")
    simple_query = """
        SELECT invoice_id
        FROM `invoicereader-477008.vendors_ai.invoices`
        LIMIT 1
    """
    try:
        result = client.query(simple_query).result()
        row = list(result)[0]
        print("Available fields in row object:")
        print(dir(row))
        print("\nActual keys:", row.keys())
    except Exception as e2:
        print(f"Alternative query also failed: {e2}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)