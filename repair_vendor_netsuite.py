#!/usr/bin/env python3
"""
Manual repair script to fix vendor NetSuite ID in BigQuery
"""
import requests
import json

# Using the local API to repair the vendor
base_url = "http://127.0.0.1:5000"

print("🔍 Searching for Nick DeMatteo vendor...")
response = requests.get(f"{base_url}/api/vendors/list", params={"search": "Nick DeMatteo", "limit": 10})
vendors = response.json()

if vendors["vendors"]:
    for vendor in vendors["vendors"]:
        if "Nick DeMatteo" in vendor.get("global_name", ""):
            vendor_id = vendor["vendor_id"]
            print(f"Found vendor: {vendor_id} - {vendor['global_name']}")
            print(f"Current NetSuite ID: {vendor.get('netsuite_internal_id')}")
            
            if not vendor.get('netsuite_internal_id'):
                print(f"\n⚠️  This vendor needs repair!")
                print(f"Vendor ID: {vendor_id}")
                print("NetSuite ID should be: 1082")
                print("\nTo fix this, we need to manually update the BigQuery record.")
                print("\nSQL to run in BigQuery console:")
                print("-" * 50)
                print(f"""
UPDATE `invoicereader-477008.vendors_ai.global_vendors`
SET 
    netsuite_internal_id = '1082',
    netsuite_sync_status = 'synced',
    netsuite_last_sync = CURRENT_TIMESTAMP(),
    custom_attributes = TO_JSON_STRING(STRUCT(
        IFNULL(JSON_VALUE(custom_attributes, '$.source'), 'API') AS source,
        IFNULL(JSON_VALUE(custom_attributes, '$.address'), '') AS address,
        IFNULL(JSON_VALUE(custom_attributes, '$.email'), 'contact@nickdematteo.com') AS email,
        IFNULL(JSON_VALUE(custom_attributes, '$.phone'), '917.573.8530') AS phone,
        IFNULL(JSON_VALUE(custom_attributes, '$.tax_id'), '') AS tax_id,
        IFNULL(JSON_VALUE(custom_attributes, '$.external_id'), '') AS external_id,
        '1082' AS netsuite_internal_id,
        'synced' AS netsuite_sync_status,
        CAST(CURRENT_TIMESTAMP() AS STRING) AS netsuite_last_sync
    )),
    last_updated = CURRENT_TIMESTAMP()
WHERE vendor_id = '{vendor_id}';
                """)
                print("-" * 50)