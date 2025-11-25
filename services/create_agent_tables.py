from services.bigquery_service import BigQueryService

def create_agent_tables():
    """
    Create all required BigQuery tables for the Agent API
    """
    bq = BigQueryService()
    
    tables = [
        {
            'name': 'agent_issues',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.agent_issues (
              issue_id STRING NOT NULL,
              issue_type STRING NOT NULL,
              severity STRING NOT NULL,
              vendor_id STRING,
              vendor_name STRING,
              vendor_email STRING,
              client_id STRING NOT NULL,
              client_email STRING,
              invoice_ids ARRAY<STRING>,
              description STRING,
              metadata JSON,
              status STRING NOT NULL DEFAULT 'open',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              resolved_at TIMESTAMP,
              resolved_by STRING
            )
            PARTITION BY DATE(created_at)
            """
        },
        {
            'name': 'agent_actions',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.agent_actions (
              action_id STRING NOT NULL,
              action_type STRING NOT NULL,
              status STRING NOT NULL DEFAULT 'pending_approval',
              priority STRING NOT NULL DEFAULT 'medium',
              vendor_id STRING,
              vendor_name STRING,
              vendor_email STRING,
              client_id STRING NOT NULL,
              client_email STRING,
              issue_id STRING,
              email_subject STRING,
              email_body STRING,
              reason STRING,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              approved_at TIMESTAMP,
              approved_by STRING,
              sent_at TIMESTAMP,
              metadata JSON
            )
            PARTITION BY DATE(created_at)
            """
        },
        {
            'name': 'client_settings',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.client_settings (
              client_id STRING NOT NULL,
              auto_send_vendor_emails BOOLEAN DEFAULT false,
              auto_send_threshold STRING DEFAULT 'high_priority_only',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              updated_at TIMESTAMP
            )
            """
        },
        {
            'name': 'api_keys',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.api_keys (
              api_key_hash STRING NOT NULL,
              client_id STRING NOT NULL,
              description STRING,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              last_used_at TIMESTAMP,
              active BOOLEAN DEFAULT true
            )
            """
        },
        {
            'name': 'invoices',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.invoices (
              invoice_id STRING NOT NULL,
              vendor_id STRING,
              vendor_name STRING,
              client_id STRING NOT NULL,
              amount NUMERIC,
              currency STRING,
              invoice_date DATE,
              status STRING,
              gcs_uri STRING,
              file_type STRING,
              file_size INT64,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              metadata JSON
            )
            PARTITION BY DATE(invoice_date)
            """
        },
        {
            'name': 'invoices_add_gcs_columns',
            'sql': """
            ALTER TABLE vendors_ai.invoices
            ADD COLUMN IF NOT EXISTS gcs_uri STRING,
            ADD COLUMN IF NOT EXISTS file_type STRING,
            ADD COLUMN IF NOT EXISTS file_size INT64
            """
        },
        {
            'name': 'invoices_add_feedback_columns',
            'sql': """
            ALTER TABLE vendors_ai.invoices
            ADD COLUMN IF NOT EXISTS approval_status STRING,
            ADD COLUMN IF NOT EXISTS rejection_reason STRING,
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS reviewed_by STRING
            """
        },
        {
            'name': 'gmail_scan_checkpoints',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.gmail_scan_checkpoints (
              scan_id STRING NOT NULL,
              client_email STRING NOT NULL,
              scan_type STRING NOT NULL,
              status STRING NOT NULL,
              days_range INT64,
              total_emails INT64,
              processed_count INT64,
              extracted_count INT64,
              duplicate_count INT64,
              failed_count INT64,
              last_message_id STRING,
              last_page_token STRING,
              processed_message_ids ARRAY<STRING>,
              started_at TIMESTAMP,
              updated_at TIMESTAMP,
              completed_at TIMESTAMP,
              error_message STRING,
              metadata JSON
            )
            PARTITION BY DATE(started_at)
            """
        },
        {
            'name': 'ai_feedback_log',
            'sql': """
            CREATE TABLE IF NOT EXISTS vendors_ai.ai_feedback_log (
              feedback_id STRING NOT NULL,
              invoice_id STRING NOT NULL,
              feedback_type STRING NOT NULL,
              original_extraction JSON,
              corrected_data JSON,
              rejection_reason STRING,
              vendor_name_original STRING,
              vendor_name_corrected STRING,
              amount_original NUMERIC,
              amount_corrected NUMERIC,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
              created_by STRING,
              applied_to_learning BOOLEAN DEFAULT false
            )
            PARTITION BY DATE(created_at)
            """
        }
    ]
    
    print(f"\n{'='*60}")
    print("Creating Agent API Tables in BigQuery")
    print(f"{'='*60}\n")
    
    for table in tables:
        try:
            print(f"Creating table: {table['name']}...")
            bq.client.query(table['sql']).result()
            print(f"✓ Table {table['name']} created successfully")
        except Exception as e:
            if "Already Exists" in str(e):
                print(f"✓ Table {table['name']} already exists")
            else:
                print(f"❌ Error creating table {table['name']}: {e}")
    
    print(f"\n{'='*60}")
    print("Migration Complete")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    create_agent_tables()
