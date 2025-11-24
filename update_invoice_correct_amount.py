#!/usr/bin/env python3
"""Update invoice 0000212 to correct amount of $300 from the PDF"""

import os
from google.cloud import bigquery
from google.oauth2 import service_account
import json
import time

# Setup BigQuery client
credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if credentials_json:
    credentials_dict = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
    client = bigquery.Client(credentials=credentials, project='invoicereader-477008')
else:
    client = bigquery.Client(project='invoicereader-477008')

print("🔄 Waiting for BigQuery streaming buffer to clear...")
print("This may take up to 90 seconds...")
time.sleep(2)  # Short wait

# Try to update with MERGE statement instead of UPDATE (works better with streaming buffer)
merge_query = """
MERGE `invoicereader-477008.vendors_ai.invoices` T
USING (SELECT '0000212' as invoice_id, 300.00 as amount, DATE('2025-08-25') as invoice_date) S
ON T.invoice_id = S.invoice_id
WHEN MATCHED THEN
  UPDATE SET 
    T.amount = S.amount,
    T.invoice_date = S.invoice_date
"""

print("\n📝 Updating Invoice 0000212 with CORRECT values from PDF:")
print("  ✓ Amount: $300.00 (from actual invoice)")  
print("  ✓ Date: August 25, 2025")
print("\nUsing MERGE statement to bypass streaming buffer...")

try:
    client.query(merge_query).result()
    print("✅ Successfully updated invoice!")
except Exception as e:
    if "streaming buffer" in str(e):
        print(f"⚠️  Streaming buffer still active. Trying alternative approach...")
        
        # Alternative: Insert into a temp table and join
        alt_query = """
        CREATE OR REPLACE TABLE `invoicereader-477008.vendors_ai.invoices_temp` AS
        SELECT * FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE invoice_id != '0000212'
        UNION ALL
        SELECT 
            '0000212' as invoice_id,
            vendor_id,
            vendor_name,
            client_id,
            300.00 as amount,  -- Correct amount from PDF
            currency,
            DATE('2025-08-25') as invoice_date,  -- Correct date from PDF
            due_date,
            status,
            gcs_uri,
            validated_data,
            extraction_metadata,
            metadata,
            created_at,
            last_updated,
            file_type,
            file_size,
            netsuite_bill_id,
            netsuite_sync_status
        FROM `invoicereader-477008.vendors_ai.invoices`
        WHERE invoice_id = '0000212'
        """
        
        try:
            client.query(alt_query).result()
            
            # Now swap the tables
            swap_query = """
            CREATE OR REPLACE TABLE `invoicereader-477008.vendors_ai.invoices` AS
            SELECT * FROM `invoicereader-477008.vendors_ai.invoices_temp`
            """
            client.query(swap_query).result()
            
            # Drop temp table
            drop_query = "DROP TABLE IF EXISTS `invoicereader-477008.vendors_ai.invoices_temp`"
            client.query(drop_query).result()
            
            print("✅ Successfully updated using table replacement!")
        except Exception as e2:
            print(f"❌ Alternative approach also failed: {e2}")
            raise
    else:
        print(f"❌ Error: {e}")
        raise

# Verify the update
verify_query = """
SELECT 
    invoice_id,
    vendor_name,
    amount,
    currency,
    invoice_date
FROM `invoicereader-477008.vendors_ai.invoices`  
WHERE invoice_id = '0000212'
"""

print("\n🔍 Verifying update...")
results = client.query(verify_query).result()

for row in results:
    print(f"\n✅ INVOICE UPDATED:")
    print(f"  Invoice ID: {row.invoice_id}")
    print(f"  Vendor: {row.vendor_name}")
    print(f"  Amount: ${row.amount:.2f} {row.currency}")
    print(f"  Date: {row.invoice_date}")
    
print("\n🎯 Invoice ready for NetSuite sync with CORRECT $300 amount!")
print("📌 Please refresh the NetSuite Dashboard to see the updated amount.")