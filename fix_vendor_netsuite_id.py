#!/usr/bin/env python3
"""
Emergency fix: Update vendor record with NetSuite ID that was created but not saved to BigQuery
"""

from google.cloud import bigquery
import json
import os

# Initialize BigQuery client
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/gcp_service_account.json'
client = bigquery.Client(project='invoicereader-477008')

# First, check current state
query = """
SELECT 
    vendor_id,
    global_name,
    netsuite_internal_id,
    netsuite_sync_status,
    JSON_VALUE(custom_attributes, '$.netsuite_internal_id') as custom_attr_ns_id,
    custom_attributes
FROM `invoicereader-477008.vendors_ai.global_vendors`
WHERE global_name LIKE '%Nick DeMatteo%'
LIMIT 5;
"""

print("Checking current vendor state...")
results = client.query(query).result()
for row in results:
    print(f"Vendor ID: {row.vendor_id}")
    print(f"Name: {row.global_name}")
    print(f"NetSuite ID (field): {row.netsuite_internal_id}")
    print(f"NetSuite ID (custom attr): {row.custom_attr_ns_id}")
    print(f"Sync Status: {row.netsuite_sync_status}")
    print("---")
    
    # If we found Nick DeMatteo without NetSuite ID, update it
    if row.global_name == "Nick DeMatteo" and not row.netsuite_internal_id:
        vendor_id_to_update = row.vendor_id
        print(f"\nFIXING: Updating vendor {vendor_id_to_update} with NetSuite ID 1082...")
        
        # Update the vendor record
        update_query = f"""
        UPDATE `invoicereader-477008.vendors_ai.global_vendors`
        SET 
            netsuite_internal_id = '1082',
            netsuite_sync_status = 'synced',
            netsuite_last_sync = CURRENT_TIMESTAMP(),
            custom_attributes = TO_JSON_STRING(STRUCT(
                IFNULL(JSON_VALUE(custom_attributes, '$.source'), 'API') AS source,
                IFNULL(JSON_VALUE(custom_attributes, '$.address'), '') AS address,
                IFNULL(JSON_VALUE(custom_attributes, '$.email'), '') AS email,
                IFNULL(JSON_VALUE(custom_attributes, '$.phone'), '') AS phone,
                IFNULL(JSON_VALUE(custom_attributes, '$.tax_id'), '') AS tax_id,
                IFNULL(JSON_VALUE(custom_attributes, '$.external_id'), '') AS external_id,
                '1082' AS netsuite_internal_id,
                'synced' AS netsuite_sync_status,
                CAST(CURRENT_TIMESTAMP() AS STRING) AS netsuite_last_sync
            )),
            last_updated = CURRENT_TIMESTAMP()
        WHERE vendor_id = '{vendor_id_to_update}'
        """
        
        job = client.query(update_query)
        job.result()  # Wait for query to complete
        print("✅ Successfully updated vendor with NetSuite ID 1082")
        
        # Verify the update
        verify_query = f"""
        SELECT vendor_id, global_name, netsuite_internal_id, netsuite_sync_status
        FROM `invoicereader-477008.vendors_ai.global_vendors`
        WHERE vendor_id = '{vendor_id_to_update}'
        """
        
        verify_results = client.query(verify_query).result()
        for verify_row in verify_results:
            print(f"\nVerification:")
            print(f"  Vendor ID: {verify_row.vendor_id}")
            print(f"  Name: {verify_row.global_name}")
            print(f"  NetSuite ID: {verify_row.netsuite_internal_id}")
            print(f"  Sync Status: {verify_row.netsuite_sync_status}")