import os
import json
import uuid
from datetime import datetime
from typing import Optional
from google.cloud import bigquery
from google.oauth2 import service_account
from config import config

class BigQueryService:
    """Service for BigQuery vendor database operations"""
    
    def __init__(self):
        # Use vertex-runner service account (has BigQuery access)
        credentials = None
        
        sa_json = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON')
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except json.JSONDecodeError:
                print("Warning: Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        elif os.path.exists(config.VERTEX_RUNNER_SA_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                config.VERTEX_RUNNER_SA_PATH,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        
        if not credentials:
            raise ValueError("BigQuery service account credentials not found in environment or file")
        
        self.client = bigquery.Client(
            credentials=credentials,
            project=config.GOOGLE_CLOUD_PROJECT_ID
        )
        
        self.dataset_id = "vendors_ai"
        self.table_id = "global_vendors"
        self.full_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.{self.table_id}"
        
        # NetSuite sync log table
        self.sync_log_table_id = "netsuite_sync_log"
        self.full_sync_log_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.{self.sync_log_table_id}"
    
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
            bigquery.SchemaField("netsuite_internal_id", "STRING", mode="NULLABLE"),  # NetSuite tracking
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
        ADD COLUMN IF NOT EXISTS netsuite_internal_id STRING,
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
            
            # Prepare vendors for BigQuery (JSON type expects dict, not string)
            prepared_vendors = []
            for vendor in mapped_vendors:
                vendor_copy = vendor.copy()
                # BigQuery JSON type expects dict/object, not JSON string
                if 'custom_attributes' not in vendor_copy or not vendor_copy['custom_attributes']:
                    vendor_copy['custom_attributes'] = {}
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
    
    def search_vendor_by_id(self, vendor_id):
        """Search for a vendor by ID"""
        
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
            netsuite_internal_id,
            last_updated
        FROM `{self.full_table_id}`
        WHERE vendor_id = @vendor_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            vendors = []
            
            for row in results:
                # Handle custom_attributes
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
                    "netsuite_internal_id": row.netsuite_internal_id,
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None
                })
            
            return vendors
            
        except Exception as e:
            print(f"❌ Error searching vendor by ID: {e}")
            return []
    
    def search_vendor_by_name(self, vendor_name, limit=5):
        """Search for vendors by name using fuzzy matching with punctuation normalization"""
        
        # CRITICAL FIX: Normalize punctuation to fix the "comma bug"
        # "Software Oasis, LLC" should match "Software Oasis LLC" in database
        clean_name = vendor_name
        for remove_str in [',', '.', ' Inc', ' LLC', ' Ltd', ' Corp', ' Corporation']:
            clean_name = clean_name.replace(remove_str, '')
        clean_name = ' '.join(clean_name.split())  # Normalize whitespace
        
        print(f"🔍 BigQuery search: '{vendor_name}' → normalized: '{clean_name}'")
        
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
           OR LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(global_name, ',', ''), '.', ''), ' Inc', ''), ' LLC', ''), ' Ltd', '')) LIKE LOWER(@clean_name)
        ORDER BY last_updated DESC
        LIMIT @limit
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("vendor_name", "STRING", f"%{vendor_name}%"),
                bigquery.ScalarQueryParameter("clean_name", "STRING", f"%{clean_name}%"),
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
    
    def get_all_vendors(self, limit=20, offset=0, search_term=None):
        """
        Get all vendors with pagination and optional search
        
        Args:
            limit: Number of vendors per page (default 20)
            offset: Starting offset for pagination (default 0)
            search_term: Optional search string to filter vendors (default None)
        
        Returns:
            dict with 'vendors' list and 'total_count' integer
        """
        
        # Build WHERE clause for search
        where_clause = ""
        query_params = [
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("offset", "INT64", offset),
        ]
        
        if search_term:
            # Search across global_name, normalized_name, and vendor_id
            search_pattern = f"%{search_term.lower()}%"
            where_clause = """
            WHERE LOWER(global_name) LIKE @search
               OR LOWER(normalized_name) LIKE @search
               OR LOWER(vendor_id) LIKE @search
            """
            query_params.append(bigquery.ScalarQueryParameter("search", "STRING", search_pattern))
        
        # Get total count
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.full_table_id}`
        {where_clause}
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
        {where_clause}
        ORDER BY last_updated DESC
        LIMIT @limit
        OFFSET @offset
        """
        
        try:
            # Create separate job configs for count and data queries
            # COUNT query only needs @search parameter (if search_term exists)
            if search_term:
                count_job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("search", "STRING", f"%{search_term.lower()}%")
                    ]
                )
            else:
                count_job_config = None
            
            # Data query needs @limit, @offset, and @search (if search_term exists)
            data_job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            
            # Get total count
            count_result = self.client.query(count_query, job_config=count_job_config).result()
            total_count = list(count_result)[0].total
            
            # Get vendors
            results = self.client.query(vendors_query, job_config=data_job_config).result()
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
    
    def ensure_netsuite_sync_log_table(self):
        """Create NetSuite sync log table if it doesn't exist"""
        schema = [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("entity_type", "STRING", mode="NULLABLE"),  # vendor or invoice
            bigquery.SchemaField("entity_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("action", "STRING", mode="NULLABLE"),  # create, update, sync
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),  # success, failed, pending
            bigquery.SchemaField("netsuite_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("request_data", "JSON", mode="NULLABLE"),  # JSON of request
            bigquery.SchemaField("response_data", "JSON", mode="NULLABLE"),  # JSON of response
            bigquery.SchemaField("duration_ms", "INT64", mode="NULLABLE"),
        ]
        
        try:
            # Try to get the table
            table = self.client.get_table(self.full_sync_log_table_id)
            print(f"✓ NetSuite sync log table {self.full_sync_log_table_id} already exists")
            return True
        except Exception as e:
            if "Not found" in str(e):
                print(f"⚠️ NetSuite sync log table not found. Creating...")
                table = bigquery.Table(self.full_sync_log_table_id, schema=schema)
                table = self.client.create_table(table)
                print(f"✓ Created NetSuite sync log table {self.full_sync_log_table_id}")
                return True
            else:
                print(f"❌ Error checking/creating sync log table: {e}")
                return False
    
    def log_netsuite_sync(self, sync_data):
        """
        Log NetSuite API call to sync log table
        
        Args:
            sync_data: Dict with sync log data
                - id: Unique ID for this log entry
                - timestamp: When the sync happened
                - entity_type: 'vendor' or 'invoice'
                - entity_id: ID of the entity being synced
                - action: 'create', 'update', 'sync', 'test'
                - status: 'success', 'failed', 'pending'
                - netsuite_id: NetSuite internal ID if successful
                - error_message: Error message if failed
                - request_data: Dict of request data (will be stored as JSON)
                - response_data: Dict of response data (will be stored as JSON)
                - duration_ms: Time taken in milliseconds
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure table exists
            self.ensure_netsuite_sync_log_table()
            
            # Prepare the row
            row = {
                "id": sync_data.get("id", str(uuid.uuid4())),
                "timestamp": sync_data.get("timestamp", datetime.utcnow().isoformat()),
                "entity_type": sync_data.get("entity_type"),
                "entity_id": sync_data.get("entity_id"),
                "action": sync_data.get("action"),
                "status": sync_data.get("status"),
                "netsuite_id": sync_data.get("netsuite_id"),
                "error_message": sync_data.get("error_message"),
                "request_data": sync_data.get("request_data", {}),  # Store as dict for BigQuery JSON
                "response_data": sync_data.get("response_data", {}),  # Store as dict for BigQuery JSON
                "duration_ms": sync_data.get("duration_ms", 0)
            }
            
            # Insert the row
            errors = self.client.insert_rows_json(self.full_sync_log_table_id, [row])
            
            if errors:
                print(f"❌ Error logging NetSuite sync: {errors}")
                return False
            
            return True
        except Exception as e:
            print(f"❌ Error logging NetSuite sync: {e}")
            return False
    
    def get_netsuite_sync_activities(self, limit=20, entity_type=None):
        """
        Get recent NetSuite sync activities
        
        Args:
            limit: Number of activities to return
            entity_type: Filter by entity type ('vendor', 'invoice')
        
        Returns:
            List of sync activities
        """
        try:
            # Build WHERE clause
            where_clause = ""
            params = []
            if entity_type:
                where_clause = "WHERE entity_type = @entity_type"
                params.append(bigquery.ScalarQueryParameter("entity_type", "STRING", entity_type))
            
            query = f"""
            SELECT 
                id,
                timestamp,
                entity_type,
                entity_id,
                action,
                status,
                netsuite_id,
                error_message,
                request_data,
                response_data,
                duration_ms
            FROM `{self.full_sync_log_table_id}`
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT @limit
            """
            
            params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            
            results = self.client.query(query, job_config=job_config).result()
            
            activities = []
            for row in results:
                activities.append({
                    "id": row.id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "action": row.action,
                    "status": row.status,
                    "netsuite_id": row.netsuite_id,
                    "error_message": row.error_message,
                    "request_data": row.request_data,
                    "response_data": row.response_data,
                    "duration_ms": row.duration_ms
                })
            
            return activities
        except Exception as e:
            print(f"❌ Error fetching NetSuite sync activities: {e}")
            return []
    
    def get_netsuite_sync_statistics(self):
        """
        Get NetSuite sync statistics
        
        Returns:
            Dict with sync statistics
        """
        try:
            query = f"""
            SELECT 
                entity_type,
                status,
                COUNT(*) as count,
                AVG(duration_ms) as avg_duration_ms,
                MAX(timestamp) as last_sync
            FROM `{self.full_sync_log_table_id}`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            GROUP BY entity_type, status
            """
            
            results = self.client.query(query).result()
            
            stats = {
                "vendors": {"success": 0, "failed": 0, "pending": 0, "avg_duration_ms": 0},
                "invoices": {"success": 0, "failed": 0, "pending": 0, "avg_duration_ms": 0},
                "total": {"success": 0, "failed": 0, "pending": 0},
                "last_sync": None
            }
            
            for row in results:
                entity_type = row.entity_type or "unknown"
                status = row.status or "unknown"
                
                if entity_type == "vendor":
                    stats["vendors"][status] = row.count
                    if status == "success":
                        stats["vendors"]["avg_duration_ms"] = row.avg_duration_ms or 0
                elif entity_type == "invoice":
                    stats["invoices"][status] = row.count
                    if status == "success":
                        stats["invoices"]["avg_duration_ms"] = row.avg_duration_ms or 0
                
                # Update totals
                if status in ["success", "failed", "pending"]:
                    stats["total"][status] += row.count
                
                # Update last sync
                if row.last_sync:
                    if not stats["last_sync"] or row.last_sync > datetime.fromisoformat(stats["last_sync"]):
                        stats["last_sync"] = row.last_sync.isoformat()
            
            # Calculate success rate
            total = sum(stats["total"].values())
            stats["success_rate"] = (stats["total"]["success"] / total * 100) if total > 0 else 0
            
            return stats
        except Exception as e:
            print(f"❌ Error fetching NetSuite sync statistics: {e}")
            return {
                "vendors": {"success": 0, "failed": 0, "pending": 0, "avg_duration_ms": 0},
                "invoices": {"success": 0, "failed": 0, "pending": 0, "avg_duration_ms": 0},
                "total": {"success": 0, "failed": 0, "pending": 0},
                "success_rate": 0,
                "last_sync": None
            }
    
    def query(self, sql_query, params=None):
        """
        Execute a parameterized BigQuery query and return results as list of dicts
        
        Args:
            sql_query: SQL query string with @param_name placeholders
            params: Dict of parameter names to values
        
        Returns:
            List of dicts with query results
        """
        if params is None:
            params = {}
        
        # Build query parameters
        query_parameters = []
        for key, value in params.items():
            # Determine BigQuery type
            if isinstance(value, bool):
                param_type = "BOOL"
            elif isinstance(value, int):
                param_type = "INT64"
            elif isinstance(value, float):
                param_type = "FLOAT64"
            else:
                param_type = "STRING"
            
            query_parameters.append(
                bigquery.ScalarQueryParameter(key, param_type, value)
            )
        
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        
        try:
            results = self.client.query(sql_query, job_config=job_config).result()
            
            # Convert to list of dicts
            rows = []
            for row in results:
                row_dict = dict(row)
                rows.append(row_dict)
            
            return rows
        except Exception as e:
            print(f"❌ Error executing query: {e}")
            return []
    
    def execute_query(self, sql_query, params=None):
        """
        Execute a parameterized BigQuery DML query (INSERT, UPDATE, DELETE)
        
        Args:
            sql_query: SQL DML query string with @param_name placeholders
            params: Dict of parameter names to values
        
        Returns:
            Number of affected rows
        """
        if params is None:
            params = {}
        
        # Build query parameters
        query_parameters = []
        for key, value in params.items():
            # Determine BigQuery type
            if isinstance(value, bool):
                param_type = "BOOL"
            elif isinstance(value, int):
                param_type = "INT64"
            elif isinstance(value, float):
                param_type = "FLOAT64"
            elif value is None:
                param_type = "STRING"
            else:
                param_type = "STRING"
            
            query_parameters.append(
                bigquery.ScalarQueryParameter(key, param_type, value)
            )
        
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        
        try:
            job = self.client.query(sql_query, job_config=job_config)
            result = job.result()
            
            return result.num_dml_affected_rows if hasattr(result, 'num_dml_affected_rows') else 0
        except Exception as e:
            print(f"❌ Error executing DML query: {e}")
            raise
    
    def insert_invoice(self, invoice_data):
        """
        Insert invoice data into vendors_ai.invoices table
        
        Args:
            invoice_data: Dict with invoice fields:
                - invoice_id: str
                - vendor_id: str (optional)
                - vendor_name: str
                - client_id: str
                - amount: float
                - currency: str
                - invoice_date: str (YYYY-MM-DD format)
                - status: str (matched/unmatched/ambiguous)
                - gcs_uri: str (Google Cloud Storage URI)
                - file_type: str (pdf, png, jpeg)
                - file_size: int (bytes)
                - metadata: dict (will be converted to JSON)
        
        Returns:
            True if successful, False otherwise
        """
        invoices_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.invoices"
        
        try:
            # First, ensure the new columns exist
            try:
                alter_sql = """
                ALTER TABLE vendors_ai.invoices
                ADD COLUMN IF NOT EXISTS gcs_uri STRING,
                ADD COLUMN IF NOT EXISTS file_type STRING,
                ADD COLUMN IF NOT EXISTS file_size INT64
                """
                self.client.query(alter_sql).result()
            except:
                pass  # Columns may already exist
            
            # Prepare the row data
            # Convert metadata dict to JSON string for BigQuery STRING column
            metadata_value = invoice_data.get("metadata", {})
            if isinstance(metadata_value, dict):
                metadata_json = json.dumps(metadata_value)
            else:
                metadata_json = json.dumps({})
            
            row = {
                "invoice_id": invoice_data.get("invoice_id"),
                "vendor_id": invoice_data.get("vendor_id"),
                "vendor_name": invoice_data.get("vendor_name"),
                "client_id": invoice_data.get("client_id", "default_client"),
                "amount": invoice_data.get("amount"),
                "currency": invoice_data.get("currency"),
                "invoice_date": invoice_data.get("invoice_date"),
                "status": invoice_data.get("status"),
                "gcs_uri": invoice_data.get("gcs_uri"),
                "file_type": invoice_data.get("file_type"),
                "file_size": invoice_data.get("file_size"),
                "metadata": metadata_json  # JSON string for BigQuery
            }
            
            # Insert the row
            errors = self.client.insert_rows_json(invoices_table_id, [row])
            
            if errors:
                print(f"❌ Error inserting invoice: {errors}")
                return False
            
            print(f"✓ Inserted invoice {invoice_data.get('invoice_id')} into BigQuery")
            return True
            
        except Exception as e:
            print(f"❌ Error inserting invoice: {e}")
            return False
    
    def get_invoices(self, page=1, limit=20, status=None):
        """
        Get invoices with pagination and optional status filter
        
        Args:
            page: Page number (default 1)
            limit: Number of invoices per page (default 20)
            status: Optional status filter (matched/unmatched/ambiguous)
        
        Returns:
            dict with 'invoices' list and 'total_count' integer
        """
        invoices_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.invoices"
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Build WHERE clause for status filter
        where_clause = ""
        query_params = [
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("offset", "INT64", offset),
        ]
        
        if status:
            where_clause = "WHERE status = @status"
            query_params.append(bigquery.ScalarQueryParameter("status", "STRING", status))
        
        # Get total count
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{invoices_table_id}`
        {where_clause}
        """
        
        # Get paginated invoices
        invoices_query = f"""
        SELECT 
            invoice_id,
            vendor_id,
            vendor_name,
            client_id,
            amount,
            currency,
            invoice_date,
            status,
            created_at,
            metadata
        FROM `{invoices_table_id}`
        {where_clause}
        ORDER BY created_at DESC
        LIMIT @limit
        OFFSET @offset
        """
        
        try:
            # Create job configs
            if status:
                count_job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("status", "STRING", status)
                    ]
                )
            else:
                count_job_config = None
            
            data_job_config = bigquery.QueryJobConfig(query_parameters=query_params)
            
            # Get total count
            count_result = self.client.query(count_query, job_config=count_job_config).result()
            total_count = list(count_result)[0].total
            
            # Get invoices
            results = self.client.query(invoices_query, job_config=data_job_config).result()
            invoices = []
            
            for row in results:
                # Parse metadata JSON
                metadata = {}
                if row.metadata:
                    if isinstance(row.metadata, str):
                        try:
                            metadata = json.loads(row.metadata)
                        except:
                            metadata = {}
                    elif isinstance(row.metadata, dict):
                        metadata = row.metadata
                
                invoice = {
                    "invoice_id": row.invoice_id,
                    "vendor_id": row.vendor_id,
                    "vendor_name": row.vendor_name,
                    "client_id": row.client_id,
                    "amount": float(row.amount) if row.amount else 0,
                    "currency": row.currency,
                    "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "match_verdict": metadata.get("verdict"),
                    "match_confidence": metadata.get("confidence"),
                    "match_reasoning": metadata.get("reasoning"),
                    "match_method": metadata.get("method")
                }
                
                invoices.append(invoice)
            
            return {
                "invoices": invoices,
                "total_count": total_count
            }
            
        except Exception as e:
            print(f"❌ Error fetching invoices: {e}")
            return {
                "invoices": [],
                "total_count": 0
            }
    
    def ensure_invoices_table_with_netsuite(self):
        """Ensure the invoices table has NetSuite tracking fields"""
        
        invoices_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.invoices"
        
        # Check if we need to add NetSuite columns to existing invoices table
        try:
            table = self.client.get_table(invoices_table_id)
            existing_fields = {field.name for field in table.schema}
            
            # Check if NetSuite fields exist
            netsuite_fields = {'netsuite_bill_id', 'netsuite_sync_status', 'netsuite_sync_date'}
            missing_fields = netsuite_fields - existing_fields
            
            if missing_fields:
                print(f"⚠️ Adding NetSuite tracking fields to invoices table...")
                query = f"""
                ALTER TABLE `{invoices_table_id}`
                ADD COLUMN IF NOT EXISTS netsuite_bill_id STRING,
                ADD COLUMN IF NOT EXISTS netsuite_sync_status STRING,
                ADD COLUMN IF NOT EXISTS netsuite_sync_date TIMESTAMP;
                """
                
                try:
                    self.client.query(query).result()
                    print("✓ Added NetSuite tracking fields to invoices table")
                except Exception as e:
                    print(f"⚠️ Could not add NetSuite fields (they may already exist): {e}")
            else:
                print("✓ NetSuite tracking fields already exist in invoices table")
            
            return True
            
        except Exception as e:
            if "Not found" in str(e):
                print(f"⚠️ Invoices table not found. Creating with NetSuite fields...")
                
                # Create invoices table with NetSuite fields
                schema = [
                    bigquery.SchemaField("invoice_id", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("vendor_id", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("vendor_name", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("client_id", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("amount", "FLOAT64", mode="NULLABLE"),
                    bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("invoice_date", "DATE", mode="NULLABLE"),
                    bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("netsuite_bill_id", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("netsuite_sync_status", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("netsuite_sync_date", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
                    bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("last_updated", "TIMESTAMP", mode="NULLABLE"),
                ]
                
                table = bigquery.Table(invoices_table_id, schema=schema)
                table = self.client.create_table(table)
                print(f"✓ Created invoices table with NetSuite tracking fields")
                return True
            else:
                print(f"❌ Error checking/creating invoices table: {e}")
                raise
    
    def update_vendor_netsuite_id(self, vendor_id: str, netsuite_id: str) -> bool:
        """
        Update vendor's NetSuite internal ID in BigQuery
        
        Args:
            vendor_id: Our vendor ID
            netsuite_id: NetSuite internal ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            query = f"""
            UPDATE `{self.full_table_id}`
            SET netsuite_internal_id = @netsuite_id,
                last_updated = CURRENT_TIMESTAMP()
            WHERE vendor_id = @vendor_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                    bigquery.ScalarQueryParameter("netsuite_id", "STRING", netsuite_id),
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
            print(f"✓ Updated NetSuite ID for vendor {vendor_id}: {netsuite_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error updating vendor NetSuite ID: {e}")
            return False
    
    def update_invoice_netsuite_sync(self, invoice_id: str, netsuite_bill_id: str, 
                                    sync_status: str = "synced") -> bool:
        """
        Update invoice's NetSuite sync information in BigQuery
        NOTE: Currently NetSuite columns don't exist, so this stores to sync log instead
        
        Args:
            invoice_id: Our invoice ID
            netsuite_bill_id: NetSuite vendor bill ID
            sync_status: Sync status (synced, pending, failed)
            
        Returns:
            True if successful, False otherwise
        """
        # For now, since NetSuite columns don't exist in invoices table,
        # we'll store the sync information in the sync log table instead
        try:
            # Store sync event in sync log table
            sync_log_row = {
                "sync_id": str(uuid.uuid4()),
                "entity_type": "invoice",
                "entity_id": invoice_id,
                "netsuite_id": netsuite_bill_id,
                "action": "sync",
                "status": sync_status,
                "timestamp": datetime.now().isoformat(),
                "error_message": None,
                "metadata": json.dumps({
                    "sync_type": "vendor_bill",
                    "bill_id": netsuite_bill_id
                })
            }
            
            errors = self.client.insert_rows_json(self.full_sync_log_table_id, [sync_log_row])
            
            if errors:
                print(f"❌ Error logging invoice NetSuite sync: {errors}")
                return False
                
            print(f"✓ Logged NetSuite sync for invoice {invoice_id}: {netsuite_bill_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error updating invoice NetSuite sync: {e}")
            # If sync log table doesn't exist, just return True to not break the sync
            if "Not found" in str(e):
                print(f"⚠️ Sync log table not found, but continuing with sync")
                return True
            return False
    
    def get_vendor_netsuite_id(self, vendor_id: str) -> Optional[str]:
        """
        Get vendor's NetSuite internal ID from BigQuery
        
        Args:
            vendor_id: Our vendor ID
            
        Returns:
            NetSuite internal ID or None
        """
        try:
            query = f"""
            SELECT netsuite_internal_id
            FROM `{self.full_table_id}`
            WHERE vendor_id = @vendor_id
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                ]
            )
            
            results = self.client.query(query, job_config=job_config).result()
            
            for row in results:
                return row.netsuite_internal_id
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting vendor NetSuite ID: {e}")
            return None
    
    def get_vendor_by_id(self, vendor_id: str) -> Optional[dict]:
        """
        Get a single vendor by ID - returns dict or None
        
        Args:
            vendor_id: The vendor ID to look up
            
        Returns:
            dict with vendor data or None if not found
        """
        vendors = self.search_vendor_by_id(vendor_id)
        if vendors and len(vendors) > 0:
            return vendors[0]
        return None
    
    def get_invoice_details(self, invoice_id: str) -> Optional[dict]:
        """
        Get invoice details from BigQuery
        
        Args:
            invoice_id: The invoice ID to look up
            
        Returns:
            dict with invoice data or None if not found
        """
        query = f"""
        SELECT 
            invoice_id,
            number,
            vendor_name,
            vendor_id,
            invoice_date,
            due_date,
            currency_code as currency,
            amount as total_amount,
            amount as subtotal,
            0 as tax_amount,
            line_items,
            extracted_data,
            gcs_uri,
            file_type,
            file_size,
            netsuite_bill_id,
            sync_status,
            created_at,
            updated_at
        FROM `{config.GOOGLE_CLOUD_PROJECT_ID}.{self.dataset_id}.invoices`
        WHERE invoice_id = @invoice_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            for row in results:
                # Convert Row to dict with all fields
                invoice_dict = {
                    "invoice_id": row.invoice_id,
                    "invoice_number": row.invoice_number,
                    "vendor_name": row.vendor_name,
                    "vendor_id": row.vendor_id,
                    "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "currency": row.currency,
                    "total_amount": float(row.total_amount) if row.total_amount else 0,
                    "subtotal": float(row.subtotal) if row.subtotal else 0,
                    "tax_amount": float(row.tax_amount) if row.tax_amount else 0,
                    "netsuite_bill_id": row.netsuite_bill_id,
                    "sync_status": row.sync_status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None
                }
                
                # Handle line_items - could be JSON or string
                if hasattr(row, 'line_items') and row.line_items:
                    try:
                        if isinstance(row.line_items, str):
                            invoice_dict["line_items"] = json.loads(row.line_items)
                        else:
                            invoice_dict["line_items"] = row.line_items
                    except:
                        invoice_dict["line_items"] = []
                else:
                    invoice_dict["line_items"] = []
                
                # Handle extracted_data - could be JSON or string  
                if hasattr(row, 'extracted_data') and row.extracted_data:
                    try:
                        if isinstance(row.extracted_data, str):
                            invoice_dict["extracted_data"] = json.loads(row.extracted_data)
                        else:
                            invoice_dict["extracted_data"] = row.extracted_data
                    except:
                        invoice_dict["extracted_data"] = {}
                else:
                    invoice_dict["extracted_data"] = {}
                
                return invoice_dict
            
            return None
        except Exception as e:
            print(f"❌ Error getting invoice details: {e}")
            return None
    
    def update_invoice_netsuite_id(self, invoice_id: str, netsuite_bill_id: str) -> bool:
        """
        Alias for update_invoice_netsuite_sync for compatibility
        
        Args:
            invoice_id: Our invoice ID
            netsuite_bill_id: NetSuite vendor bill ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.update_invoice_netsuite_sync(invoice_id, netsuite_bill_id, "synced")
