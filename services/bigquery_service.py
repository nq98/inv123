import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account
from config import config

class BigQueryService:
    """Service for BigQuery vendor database operations"""
    
    def __init__(self):
        # Use vertex-runner service account (has BigQuery access)
        credentials_path = config.VERTEX_RUNNER_SA_PATH
        if not credentials_path or not os.path.exists(credentials_path):
            raise ValueError(f"BigQuery service account credentials not found at {credentials_path}")
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        self.client = bigquery.Client(
            credentials=credentials,
            project=config.GOOGLE_CLOUD_PROJECT_ID
        )
        
        self.dataset_id = "vendors_ai"
        self.table_id = "global_vendors"
        self.full_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.{self.table_id}"
    
    def ensure_table_schema(self):
        """Ensure the global_vendors table has the correct schema with custom_attributes JSON column"""
        
        schema = [
            bigquery.SchemaField("vendor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("global_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("normalized_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("emails", "STRING", mode="REPEATED"),
            bigquery.SchemaField("domains", "STRING", mode="REPEATED"),
            bigquery.SchemaField("countries", "STRING", mode="REPEATED"),
            bigquery.SchemaField("custom_attributes", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("source_system", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("last_updated", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        
        try:
            # Try to get the table
            table = self.client.get_table(self.full_table_id)
            print(f"✓ Table {self.full_table_id} already exists")
            
            # Check if custom_attributes column exists
            existing_fields = {field.name for field in table.schema}
            if "custom_attributes" not in existing_fields:
                print("⚠️ Adding custom_attributes, source_system, and timestamp columns...")
                # Note: ALTER TABLE ADD COLUMN IF NOT EXISTS is handled via SQL
                self._add_custom_columns()
            
            return True
            
        except Exception as e:
            if "Not found" in str(e):
                print(f"⚠️ Table {self.full_table_id} not found. Creating...")
                table = bigquery.Table(self.full_table_id, schema=schema)
                table = self.client.create_table(table)
                print(f"✓ Created table {self.full_table_id}")
                return True
            else:
                print(f"❌ Error checking/creating table: {e}")
                raise
    
    def _add_custom_columns(self):
        """Add custom_attributes and metadata columns if they don't exist"""
        query = f"""
        ALTER TABLE `{self.full_table_id}`
        ADD COLUMN IF NOT EXISTS custom_attributes JSON,
        ADD COLUMN IF NOT EXISTS source_system STRING,
        ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP,
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
        """
        
        try:
            self.client.query(query).result()
            print("✓ Added custom columns to table")
        except Exception as e:
            print(f"⚠️ Could not add columns (they may already exist): {e}")
    
    def merge_vendors(self, mapped_vendors, source_system="csv_upload"):
        """
        Merge vendor data into global_vendors table with smart deduplication
        
        Args:
            mapped_vendors: List of dicts with mapped vendor data
            source_system: Name of the source system (e.g., "SAP", "QuickBooks", "Excel")
        
        Returns:
            dict with inserted/updated counts
        """
        
        if not mapped_vendors:
            return {"inserted": 0, "updated": 0, "errors": []}
        
        # Create temporary staging table
        staging_table_id = f"{self.full_table_id}_staging_{int(os.urandom(4).hex(), 16)}"
        
        try:
            # Define staging table schema
            staging_schema = [
                bigquery.SchemaField("vendor_id", "STRING"),
                bigquery.SchemaField("global_name", "STRING"),
                bigquery.SchemaField("normalized_name", "STRING"),
                bigquery.SchemaField("emails", "STRING", mode="REPEATED"),
                bigquery.SchemaField("domains", "STRING", mode="REPEATED"),
                bigquery.SchemaField("countries", "STRING", mode="REPEATED"),
                bigquery.SchemaField("custom_attributes", "JSON"),
                bigquery.SchemaField("source_system", "STRING"),
            ]
            
            # Create staging table
            staging_table = bigquery.Table(staging_table_id, schema=staging_schema)
            staging_table = self.client.create_table(staging_table)
            
            # Convert custom_attributes dict to JSON string for BigQuery
            prepared_vendors = []
            for vendor in mapped_vendors:
                vendor_copy = vendor.copy()
                # Convert custom_attributes dict to JSON string
                if 'custom_attributes' in vendor_copy and vendor_copy['custom_attributes']:
                    vendor_copy['custom_attributes'] = json.dumps(vendor_copy['custom_attributes'])
                else:
                    vendor_copy['custom_attributes'] = json.dumps({})
                prepared_vendors.append(vendor_copy)
            
            # Insert data into staging table
            errors = self.client.insert_rows_json(staging_table, prepared_vendors)
            
            if errors:
                print(f"⚠️ Errors inserting into staging table: {errors}")
                return {"inserted": 0, "updated": 0, "errors": errors}
            
            # Execute MERGE query
            merge_query = f"""
            MERGE `{self.full_table_id}` T
            USING `{staging_table_id}` S
            ON T.vendor_id = S.vendor_id
            WHEN MATCHED THEN
              UPDATE SET 
                T.global_name = S.global_name,
                T.normalized_name = S.normalized_name,
                T.emails = S.emails,
                T.domains = S.domains,
                T.countries = S.countries,
                T.custom_attributes = S.custom_attributes,
                T.source_system = S.source_system,
                T.last_updated = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
              INSERT (vendor_id, global_name, normalized_name, emails, domains, countries, custom_attributes, source_system, last_updated, created_at)
              VALUES (S.vendor_id, S.global_name, S.normalized_name, S.emails, S.domains, S.countries, S.custom_attributes, S.source_system, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            
            job = self.client.query(merge_query)
            result = job.result()
            
            # Get stats from result
            stats = {
                "inserted": result.num_dml_affected_rows if hasattr(result, 'num_dml_affected_rows') else len(mapped_vendors),
                "updated": 0,
                "errors": []
            }
            
            print(f"✓ Merged {stats['inserted']} vendors into BigQuery")
            
            # Clean up staging table
            self.client.delete_table(staging_table_id, not_found_ok=True)
            
            return stats
            
        except Exception as e:
            print(f"❌ Error merging vendors: {e}")
            # Clean up staging table on error
            try:
                self.client.delete_table(staging_table_id, not_found_ok=True)
            except:
                pass
            
            return {"inserted": 0, "updated": 0, "errors": [str(e)]}
    
    def search_vendor_by_name(self, vendor_name, limit=5):
        """Search for vendors by name using fuzzy matching"""
        
        query = f"""
        SELECT 
            vendor_id,
            global_name,
            normalized_name,
            emails,
            domains,
            countries,
            custom_attributes,
            source_system,
            last_updated
        FROM `{self.full_table_id}`
        WHERE LOWER(global_name) LIKE LOWER(@vendor_name)
           OR LOWER(normalized_name) LIKE LOWER(@vendor_name)
        ORDER BY last_updated DESC
        LIMIT @limit
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("vendor_name", "STRING", f"%{vendor_name}%"),
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            vendors = []
            
            for row in results:
                # Handle custom_attributes - it may already be a dict from BigQuery JSON type
                custom_attrs = row.custom_attributes
                if custom_attrs:
                    if isinstance(custom_attrs, str):
                        custom_attrs = json.loads(custom_attrs)
                    elif isinstance(custom_attrs, dict):
                        custom_attrs = custom_attrs
                    else:
                        custom_attrs = {}
                else:
                    custom_attrs = {}
                
                vendors.append({
                    "vendor_id": row.vendor_id,
                    "global_name": row.global_name,
                    "normalized_name": row.normalized_name,
                    "emails": list(row.emails) if row.emails else [],
                    "domains": list(row.domains) if row.domains else [],
                    "countries": list(row.countries) if row.countries else [],
                    "custom_attributes": custom_attrs,
                    "source_system": row.source_system,
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None
                })
            
            return vendors
            
        except Exception as e:
            print(f"❌ Error searching vendors: {e}")
            return []
    
    def get_all_vendors(self, limit=20, offset=0):
        """
        Get all vendors with pagination
        
        Args:
            limit: Number of vendors per page (default 20)
            offset: Starting offset for pagination (default 0)
        
        Returns:
            dict with 'vendors' list and 'total_count' integer
        """
        
        # Get total count
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.full_table_id}`
        """
        
        # Get paginated vendors
        vendors_query = f"""
        SELECT 
            vendor_id,
            global_name,
            normalized_name,
            emails,
            domains,
            countries,
            custom_attributes,
            source_system,
            last_updated,
            created_at
        FROM `{self.full_table_id}`
        ORDER BY last_updated DESC
        LIMIT @limit
        OFFSET @offset
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
                bigquery.ScalarQueryParameter("offset", "INT64", offset),
            ]
        )
        
        try:
            # Get total count
            count_result = self.client.query(count_query).result()
            total_count = list(count_result)[0].total
            
            # Get vendors
            results = self.client.query(vendors_query, job_config=job_config).result()
            vendors = []
            
            for row in results:
                # Handle custom_attributes - it may already be a dict from BigQuery JSON type
                custom_attrs = row.custom_attributes
                if custom_attrs:
                    if isinstance(custom_attrs, str):
                        custom_attrs = json.loads(custom_attrs)
                    elif isinstance(custom_attrs, dict):
                        custom_attrs = custom_attrs
                    else:
                        custom_attrs = {}
                else:
                    custom_attrs = {}
                
                vendors.append({
                    "vendor_id": row.vendor_id,
                    "global_name": row.global_name,
                    "normalized_name": row.normalized_name,
                    "emails": list(row.emails) if row.emails else [],
                    "domains": list(row.domains) if row.domains else [],
                    "countries": list(row.countries) if row.countries else [],
                    "custom_attributes": custom_attrs,
                    "source_system": row.source_system,
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })
            
            return {
                "vendors": vendors,
                "total_count": total_count
            }
            
        except Exception as e:
            print(f"❌ Error fetching vendors: {e}")
            return {
                "vendors": [],
                "total_count": 0
            }
