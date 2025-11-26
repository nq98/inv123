"""
Multi-Tenant Migration Script
Adds owner_email column to all BigQuery tables and migrates existing data
"""

import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "invoicereader-477008"
DATASET_ID = "vendors_ai"
DEFAULT_OWNER = "barak@payouts.com"

TABLES_TO_MIGRATE = [
    "global_vendors",
    "invoices", 
    "netsuite_events",
    "netsuite_sync_log",
    "gmail_scan_checkpoints",
    "ai_feedback_log",
    "api_keys",
    "agent_actions",
    "agent_issues",
    "client_settings",
    "subscription_vendors",
    "subscription_events",
]


def get_bq_client():
    """Get authenticated BigQuery client"""
    credentials = None
    sa_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if sa_json:
        try:
            sa_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(sa_info)
        except json.JSONDecodeError:
            pass
    
    sa_path = "attached_assets/vertex-ai-search-runner.json"
    if not credentials and os.path.exists(sa_path):
        credentials = service_account.Credentials.from_service_account_file(sa_path)
    
    return bigquery.Client(project=PROJECT_ID, credentials=credentials)


def check_column_exists(client, table_name, column_name):
    """Check if a column exists in a table"""
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    try:
        table = client.get_table(table_id)
        return any(field.name == column_name for field in table.schema)
    except Exception:
        return False


def add_owner_email_column(client, table_name):
    """Add owner_email column to a table"""
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    
    if check_column_exists(client, table_name, "owner_email"):
        print(f"  ✓ {table_name}: owner_email column already exists")
        return True
    
    try:
        query = f"""
        ALTER TABLE `{table_id}`
        ADD COLUMN IF NOT EXISTS owner_email STRING
        """
        client.query(query).result()
        print(f"  ✓ {table_name}: Added owner_email column")
        return True
    except Exception as e:
        if "Not found" in str(e):
            print(f"  ⚠ {table_name}: Table does not exist (skipping)")
            return False
        print(f"  ✗ {table_name}: Error adding column - {e}")
        return False


def migrate_existing_data(client, table_name, default_owner):
    """Set owner_email for all existing records that don't have it"""
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    
    try:
        query = f"""
        UPDATE `{table_id}`
        SET owner_email = @default_owner
        WHERE owner_email IS NULL OR owner_email = ''
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("default_owner", "STRING", default_owner)
            ]
        )
        result = client.query(query, job_config=job_config).result()
        print(f"  ✓ {table_name}: Migrated existing data to owner_email = '{default_owner}'")
        return True
    except Exception as e:
        if "Not found" in str(e):
            print(f"  ⚠ {table_name}: Table does not exist (skipping migration)")
            return False
        print(f"  ✗ {table_name}: Error migrating data - {e}")
        return False


def create_user_integrations_table(client):
    """Create user_integrations table for per-user OAuth tokens"""
    table_id = f"{PROJECT_ID}.{DATASET_ID}.user_integrations"
    
    schema = [
        bigquery.SchemaField("integration_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("owner_email", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("integration_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("credentials", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("access_token", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("refresh_token", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("token_expiry", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("is_connected", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("last_used", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
    ]
    
    try:
        table = client.get_table(table_id)
        print(f"  ✓ user_integrations: Table already exists")
        return True
    except Exception:
        pass
    
    try:
        table = bigquery.Table(table_id, schema=schema)
        table = client.create_table(table)
        print(f"  ✓ user_integrations: Created table for per-user OAuth tokens")
        return True
    except Exception as e:
        print(f"  ✗ user_integrations: Error creating table - {e}")
        return False


def run_migration():
    """Run the full multi-tenant migration"""
    print("=" * 60)
    print("MULTI-TENANT MIGRATION")
    print("=" * 60)
    print(f"Project: {PROJECT_ID}")
    print(f"Dataset: {DATASET_ID}")
    print(f"Default Owner: {DEFAULT_OWNER}")
    print("=" * 60)
    
    client = get_bq_client()
    
    print("\n[Step 1] Adding owner_email column to tables...")
    for table in TABLES_TO_MIGRATE:
        add_owner_email_column(client, table)
    
    print("\n[Step 2] Migrating existing data...")
    for table in TABLES_TO_MIGRATE:
        migrate_existing_data(client, table, DEFAULT_OWNER)
    
    print("\n[Step 3] Creating user_integrations table...")
    create_user_integrations_table(client)
    
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
