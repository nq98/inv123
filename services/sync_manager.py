"""
NetSuite Synchronization Manager
Handles bidirectional sync between our platform and NetSuite
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from google.cloud import bigquery
from services.bigquery_service import BigQueryService
from services.netsuite_service import NetSuiteService
from services.retry_utils import exponential_backoff_retry, retry_with_backoff, RetryableError
from config import config

class SyncManager:
    """Manages complete synchronization between platform and NetSuite"""
    
    def __init__(self):
        self.bigquery = BigQueryService()
        self.netsuite = NetSuiteService()
        self.client = self.bigquery.client
        self.project_id = config.GOOGLE_CLOUD_PROJECT_ID
        self.sync_log_table_id = f"{self.project_id}.vendors_ai.sync_log"
        self.ensure_sync_log_table()
    
    def ensure_sync_log_table(self):
        """Create sync_log table if it doesn't exist"""
        try:
            # Check if table exists
            table = self.client.get_table(self.sync_log_table_id)
            print(f"✓ Sync log table {self.sync_log_table_id} already exists")
        except Exception:
            # Create the table if it doesn't exist
            schema = [
                bigquery.SchemaField("log_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("operation_type", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("entity_type", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("entity_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("details", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("duration_seconds", "FLOAT64", mode="NULLABLE"),
            ]
            
            table = bigquery.Table(self.sync_log_table_id, schema=schema)
            table = self.client.create_table(table)
            print(f"✓ Created sync log table {self.sync_log_table_id}")
    
    @exponential_backoff_retry(max_retries=3, initial_delay=1.0, exceptions=(Exception,))
    def log_sync_activity(self, operation_type: str, entity_type: str = None, 
                          entity_id: str = None, status: str = "success", 
                          details: dict = None, error_message: str = None,
                          duration_seconds: float = None) -> bool:
        """Log a sync activity to BigQuery with retry logic"""
        try:
            log_entry = {
                "log_id": str(uuid.uuid4()),
                "operation_type": operation_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details or {},
                "error_message": error_message,
                "duration_seconds": duration_seconds
            }
            
            table = self.client.get_table(self.sync_log_table_id)
            errors = self.client.insert_rows_json(table, [log_entry])
            
            if errors:
                error_msg = f"BigQuery insert failed: {errors}"
                print(f"❌ Error logging sync activity: {error_msg}")
                raise RetryableError(error_msg)
            
            return True
        except RetryableError:
            raise
        except Exception as e:
            print(f"❌ Failed to log sync activity: {e}")
            # Don't fail the entire operation if logging fails
            return False
    
    def get_recent_sync_activities(self, limit: int = 10) -> List[Dict]:
        """Get recent sync activities from the log"""
        try:
            query = f"""
            SELECT 
                log_id,
                operation_type,
                entity_type,
                entity_id,
                status,
                timestamp,
                details,
                error_message,
                duration_seconds
            FROM `{self.sync_log_table_id}`
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
            
            results = list(self.client.query(query).result())
            activities = []
            
            for row in results:
                activities.append({
                    'log_id': row.log_id,
                    'operation_type': row.operation_type,
                    'entity_type': row.entity_type,
                    'entity_id': row.entity_id,
                    'status': row.status,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'details': row.details,
                    'error_message': row.error_message,
                    'duration_seconds': row.duration_seconds
                })
            
            return activities
        except Exception as e:
            print(f"Error fetching recent sync activities: {e}")
            return []
    
    def get_sync_dashboard_stats(self) -> Dict:
        """Get comprehensive sync statistics for dashboard"""
        try:
            stats = {
                'vendors': {},
                'invoices': {},
                'payments': {},
                'recent_activities': []
            }
            
            # Get vendor sync statistics
            # Extract sync fields from custom_attributes JSON for Universal Schema
            vendor_query = f"""
            SELECT 
                COUNT(*) as total_vendors,
                COUNTIF(JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_internal_id') IS NOT NULL) as synced_vendors,
                COUNTIF(JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_internal_id') IS NULL) as not_synced_vendors,
                COUNTIF(JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_sync_status') = 'failed') as failed_syncs
            FROM `{self.project_id}.vendors_ai.global_vendors`
            """
            
            vendor_results = list(self.client.query(vendor_query).result())
            if vendor_results:
                row = vendor_results[0]
                stats['vendors'] = {
                    'total': row.total_vendors,
                    'synced': row.synced_vendors,
                    'not_synced': row.not_synced_vendors,
                    'failed': row.failed_syncs,
                    'sync_percentage': round((row.synced_vendors / row.total_vendors * 100) if row.total_vendors > 0 else 0, 1)
                }
            
            # Get invoice sync statistics
            # Checking if invoices table has netsuite_bill_id column, payment_status might not exist
            invoice_query = f"""
            SELECT 
                COUNT(*) as total_invoices,
                COUNTIF(netsuite_bill_id IS NOT NULL) as with_bills,
                COUNTIF(netsuite_bill_id IS NULL) as without_bills,
                0 as paid,
                0 as pending,
                0 as overdue,
                0 as partial
            FROM `{self.project_id}.vendors_ai.invoices`
            """
            
            invoice_results = list(self.client.query(invoice_query).result())
            if invoice_results:
                row = invoice_results[0]
                stats['invoices'] = {
                    'total': row.total_invoices,
                    'with_bills': row.with_bills,
                    'without_bills': row.without_bills,
                    'bill_percentage': round((row.with_bills / row.total_invoices * 100) if row.total_invoices > 0 else 0, 1)
                }
                stats['payments'] = {
                    'paid': row.paid,
                    'pending': row.pending,
                    'overdue': row.overdue,
                    'partial': row.partial,
                    'total': row.total_invoices
                }
            
            # Get recent sync activities
            stats['recent_activities'] = self.get_recent_sync_activities(10)
            
            # Get sync operation statistics for the last 24 hours
            activity_stats_query = f"""
            SELECT 
                operation_type,
                COUNT(*) as count,
                COUNTIF(status = 'success') as success_count,
                COUNTIF(status = 'failed') as failed_count,
                AVG(duration_seconds) as avg_duration
            FROM `{self.sync_log_table_id}`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY operation_type
            ORDER BY count DESC
            """
            
            activity_results = list(self.client.query(activity_stats_query).result())
            stats['operation_stats'] = []
            for row in activity_results:
                stats['operation_stats'].append({
                    'operation': row.operation_type,
                    'total': row.count,
                    'success': row.success_count,
                    'failed': row.failed_count,
                    'avg_duration': round(row.avg_duration, 2) if row.avg_duration else 0
                })
            
            return stats
            
        except Exception as e:
            print(f"Error getting sync dashboard stats: {e}")
            return {
                'vendors': {'total': 0, 'synced': 0, 'not_synced': 0, 'failed': 0, 'sync_percentage': 0},
                'invoices': {'total': 0, 'with_bills': 0, 'without_bills': 0, 'bill_percentage': 0},
                'payments': {'paid': 0, 'pending': 0, 'overdue': 0, 'partial': 0, 'total': 0},
                'recent_activities': [],
                'operation_stats': []
            }
        
    def update_vendor_schema(self):
        """Ensure vendor table has required fields - sync data goes in custom_attributes"""
        try:
            # Check table exists and has custom_attributes column
            table_id = f"{self.project_id}.vendors_ai.global_vendors"
            table = self.client.get_table(table_id)
            
            existing_fields = {field.name for field in table.schema}
            
            # Ensure custom_attributes column exists for storing sync data
            if 'custom_attributes' not in existing_fields:
                print(f"Warning: custom_attributes column missing in vendor table")
                # For Universal Schema, sync fields go in custom_attributes JSON
                # Not adding direct columns as they belong in the JSON field
                return False
            
            print("✓ Vendor table has custom_attributes column for sync fields")
            # Sync fields (netsuite_internal_id, netsuite_sync_status, etc.) 
            # are stored in custom_attributes JSON as per Universal Schema
            return True
        except Exception as e:
            print(f"Error checking vendor schema: {e}")
            return False
            
    def update_invoice_schema(self):
        """Add payment tracking fields to invoice table"""
        try:
            table_id = f"{self.project_id}.vendors_ai.invoices"
            table = self.client.get_table(table_id)
            
            existing_fields = {field.name for field in table.schema}
            new_fields = []
            
            # Add payment tracking fields if missing
            if 'payment_status' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_status", "STRING", mode="NULLABLE"))
            if 'payment_date' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_date", "DATE", mode="NULLABLE"))
            if 'payment_amount' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_amount", "FLOAT64", mode="NULLABLE"))
            if 'payment_method' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_method", "STRING", mode="NULLABLE"))
                
            if new_fields:
                new_schema = table.schema + new_fields
                table.schema = new_schema
                table = self.client.update_table(table, ["schema"])
                print(f"✓ Updated invoice table with {len(new_fields)} new payment fields")
            else:
                print("✓ Invoice table already has all payment fields")
                
            return True
        except Exception as e:
            print(f"Error updating invoice schema: {e}")
            return False
    
    def sync_vendor_to_netsuite(self, vendor_id: str, force: bool = False) -> Dict:
        """
        Sync single vendor to NetSuite with tracking
        """
        try:
            # Get vendor from BigQuery
            vendor = self.bigquery.get_vendor_by_id(vendor_id)
            if not vendor:
                return {'success': False, 'error': 'Vendor not found'}
            
            # Check if already synced (unless forced)
            if not force and vendor.get('netsuite_internal_id'):
                last_sync = vendor.get('netsuite_last_sync')
                if last_sync and (datetime.now() - last_sync).seconds < 3600:  # Less than 1 hour
                    return {
                        'success': True,
                        'message': 'Recently synced',
                        'netsuite_id': vendor.get('netsuite_internal_id')
                    }
            
            # Sync to NetSuite
            sync_data = {
                'vendor_id': vendor_id,
                'name': vendor.get('global_name', ''),
                'email': vendor.get('emails')[0] if vendor.get('emails') else None,
                'phone': vendor.get('phone_numbers')[0] if vendor.get('phone_numbers') else None,
                'tax_id': vendor.get('tax_id'),
                'address': vendor.get('address'),
                'external_id': f"VENDOR_{vendor_id}"
            }
            
            # Log sync start
            start_time = datetime.now()
            
            # Retry NetSuite API call with exponential backoff
            try:
                result = retry_with_backoff(
                    self.netsuite.sync_vendor_to_netsuite,
                    args=(sync_data,),
                    max_retries=3,
                    initial_delay=2.0,
                    backoff_factor=2.0
                )
            except Exception as e:
                print(f"❌ Failed to sync vendor to NetSuite after retries: {e}")
                result = {'success': False, 'error': str(e)}
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Log sync activity
            self.log_sync_activity(
                operation_type='vendor_sync',
                entity_type='vendor',
                entity_id=vendor_id,
                status='success' if result.get('success') else 'failed',
                details={
                    'vendor_name': vendor.get('global_name', ''),
                    'netsuite_id': result.get('netsuite_id'),
                    'action': 'create' if not vendor.get('netsuite_internal_id') else 'update'
                },
                error_message=result.get('error') if not result.get('success') else None,
                duration_seconds=duration
            )
            
            # Update sync status in BigQuery
            update_query = f"""
            UPDATE `{self.project_id}.vendors_ai.global_vendors`
            SET 
                custom_attributes = JSON_SET(
                    IFNULL(custom_attributes, JSON '{{}}'),
                    '$.netsuite_internal_id', @netsuite_id,
                    '$.netsuite_sync_status', @sync_status,
                    '$.netsuite_last_sync', CAST(CURRENT_TIMESTAMP() AS STRING),
                    '$.netsuite_sync_error', @sync_error
                ),
                last_updated = CURRENT_TIMESTAMP()
            WHERE vendor_id = @vendor_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                    bigquery.ScalarQueryParameter("netsuite_id", "STRING", result.get('netsuite_id') if result.get('success') else None),
                    bigquery.ScalarQueryParameter("sync_status", "STRING", 'synced' if result.get('success') else 'failed'),
                    bigquery.ScalarQueryParameter("sync_error", "STRING", result.get('error') if not result.get('success') else None)
                ]
            )
            
            # Execute query with retry logic
            try:
                retry_with_backoff(
                    lambda: self.client.query(update_query, job_config=job_config).result(),
                    max_retries=3,
                    initial_delay=1.0
                )
            except Exception as e:
                error_msg = f"Failed to update vendor sync status in BigQuery: {e}"
                print(f"❌ {error_msg}")
                # Propagate the error instead of swallowing it
                raise RetryableError(error_msg)
            
            # Log sync activity
            self.bigquery.log_netsuite_sync({
                'entity_type': 'vendor',
                'entity_id': vendor_id,
                'action': 'sync',
                'status': 'success' if result.get('success') else 'failed',
                'netsuite_id': result.get('netsuite_id'),
                'error_message': result.get('error')
            })
            
            return result
            
        except Exception as e:
            print(f"Error syncing vendor {vendor_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def sync_csv_vendors_to_netsuite(self, vendor_ids: List[str]) -> Dict:
        """
        Sync multiple vendors from CSV import to NetSuite
        """
        results = {
            'total': len(vendor_ids),
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for vendor_id in vendor_ids:
            result = self.sync_vendor_to_netsuite(vendor_id)
            if result.get('success'):
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'vendor_id': vendor_id,
                    'error': result.get('error')
                })
        
        return results
    
    def sync_vendors_from_netsuite(self, progress_callback=None) -> Dict:
        """
        Pull all vendors from NetSuite and sync to BigQuery with real-time progress reporting
        
        Args:
            progress_callback: Optional callback function to report progress
                             Should accept (step, total_steps, message, data)
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            'total_fetched': 0,
            'new_vendors': 0,
            'updated_vendors': 0,
            'failed': 0,
            'errors': [],
            'start_time': datetime.now()
        }
        
        try:
            # Step 1: Fetch vendors from NetSuite with pagination
            if progress_callback:
                progress_callback(1, 5, "Connecting to NetSuite...", {})
            
            all_vendors = []
            offset = 0
            limit = 100  # Fetch 100 vendors at a time
            
            while True:
                try:
                    # Use REST API to get all vendors
                    params = {'limit': limit, 'offset': offset}
                    response = self.netsuite._make_request('GET', '/record/v1/vendor', params=params)
                    
                    if not response or 'items' not in response:
                        break
                    
                    batch_items = response.get('items', [])
                    all_vendors.extend(batch_items)
                    
                    if progress_callback:
                        progress_callback(
                            1, 5, 
                            f"Fetching vendors from NetSuite... ({len(all_vendors)} found)", 
                            {'fetched': len(all_vendors)}
                        )
                    
                    # Check if there are more vendors
                    if len(batch_items) < limit:
                        break
                    
                    offset += limit
                    
                except Exception as e:
                    print(f"Error fetching vendors batch at offset {offset}: {e}")
                    stats['errors'].append(f"Fetch error at offset {offset}: {str(e)}")
                    break
            
            stats['total_fetched'] = len(all_vendors)
            
            if progress_callback:
                progress_callback(
                    2, 5, 
                    f"Found {len(all_vendors)} vendors in NetSuite", 
                    {'total': len(all_vendors)}
                )
            
            # Step 2: Process each vendor
            for idx, ns_vendor in enumerate(all_vendors):
                try:
                    if progress_callback and idx % 10 == 0:
                        progress_callback(
                            3, 5,
                            f"Processing vendor {idx + 1} of {len(all_vendors)}",
                            {
                                'current': idx + 1,
                                'total': len(all_vendors),
                                'vendor_name': ns_vendor.get('companyName', 'Unknown')
                            }
                        )
                    
                    # Extract vendor data from NetSuite format
                    ns_id = str(ns_vendor.get('id', ''))
                    company_name = ns_vendor.get('companyName', '')
                    email = ns_vendor.get('email', '')
                    phone = ns_vendor.get('phone', '')
                    tax_id = ns_vendor.get('defaultTaxReg', '')
                    address = self._format_netsuite_address(ns_vendor.get('defaultAddress', {}))
                    external_id = ns_vendor.get('externalId', '')
                    
                    # Check if vendor exists in BigQuery
                    existing_vendor = None
                    
                    # Try to find by tax ID first
                    if tax_id:
                        existing_vendor = self._find_vendor_by_tax_id(tax_id)
                    
                    # If not found by tax ID, try by name
                    if not existing_vendor and company_name:
                        existing_vendor = self._find_vendor_by_name(company_name)
                    
                    if existing_vendor:
                        # Update existing vendor with NetSuite info
                        self._update_vendor_netsuite_fields(
                            existing_vendor['vendor_id'],
                            ns_id,
                            external_id
                        )
                        stats['updated_vendors'] += 1
                    else:
                        # Create new vendor following Universal Schema
                        # 1. Prepare Custom Attributes (Flexible Bucket)
                        custom_attrs = {
                            "address": address,
                            "phone": phone,
                            "tax_id": tax_id,
                            "email": email,
                            "external_id": external_id,
                            "netsuite_internal_id": ns_id,
                            "netsuite_sync_status": "synced",
                            "netsuite_last_sync": datetime.now().isoformat(),
                            "source": "NetSuite Import"
                        }
                        
                        # 2. Prepare the Row (Matching BigQuery Universal Schema)
                        vendor_data = {
                            "vendor_id": f"NETSUITE_{ns_id}",  # Generate a unique ID
                            "global_name": company_name,        # Map 'name' to 'global_name'  
                            "normalized_name": company_name.lower() if company_name else "",
                            "emails": [email] if email else [],
                            "domains": [],  # Can extract from email if needed
                            "countries": [],  # Can extract from address if available
                            # NOTE: addresses field removed - it's stored in custom_attributes instead
                            "custom_attributes": json.dumps(custom_attrs),  # Pack everything else here!
                            "source_system": "NETSUITE",
                            "created_at": datetime.now(),
                            "last_updated": datetime.now()
                        }
                        
                        # Insert into BigQuery
                        self._insert_vendor_to_bigquery(vendor_data)
                        stats['new_vendors'] += 1
                        
                except Exception as e:
                    print(f"Error processing vendor {ns_vendor.get('companyName', 'Unknown')}: {e}")
                    stats['failed'] += 1
                    stats['errors'].append(f"Vendor {ns_vendor.get('companyName', 'Unknown')}: {str(e)}")
            
            # Step 4: Final statistics
            if progress_callback:
                progress_callback(
                    4, 5,
                    "Finalizing sync results...",
                    stats
                )
            
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            # Log sync activity
            if self.bigquery:
                self.bigquery.log_netsuite_sync({
                    'entity_type': 'vendor_bulk',
                    'entity_id': 'BULK_PULL',
                    'action': 'pull_all',
                    'status': 'success',
                    'details': {
                        'total_fetched': stats['total_fetched'],
                        'new_vendors': stats['new_vendors'],
                        'updated_vendors': stats['updated_vendors'],
                        'failed': stats['failed']
                    }
                })
            
            if progress_callback:
                progress_callback(
                    5, 5,
                    "Vendor sync completed successfully!",
                    stats
                )
            
            return stats
            
        except Exception as e:
            print(f"Critical error in vendor sync: {e}")
            stats['errors'].append(f"Critical error: {str(e)}")
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            if progress_callback:
                progress_callback(
                    5, 5,
                    f"Sync failed: {str(e)}",
                    stats
                )
            
            return stats
    
    def _format_netsuite_address(self, address_obj: Dict) -> str:
        """Format NetSuite address object into a string"""
        if not address_obj:
            return ""
        
        parts = []
        if address_obj.get('addr1'):
            parts.append(address_obj['addr1'])
        if address_obj.get('addr2'):
            parts.append(address_obj['addr2'])
        if address_obj.get('city'):
            parts.append(address_obj['city'])
        if address_obj.get('state'):
            parts.append(address_obj['state'])
        if address_obj.get('zip'):
            parts.append(address_obj['zip'])
        if address_obj.get('country'):
            parts.append(address_obj['country'])
        
        return ", ".join(parts)
    
    def _find_vendor_by_tax_id(self, tax_id: str) -> Optional[Dict]:
        """Find vendor in BigQuery by tax ID"""
        try:
            query = f"""
            SELECT * FROM `{self.project_id}.vendors_ai.global_vendors`
            WHERE LOWER(tax_id) = LOWER(@tax_id)
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("tax_id", "STRING", tax_id)
                ]
            )
            
            results = list(self.client.query(query, job_config=job_config).result())
            return dict(results[0]) if results else None
        except Exception as e:
            print(f"Error finding vendor by tax ID: {e}")
            return None
    
    def _find_vendor_by_name(self, name: str) -> Optional[Dict]:
        """Find vendor in BigQuery by name"""
        try:
            query = f"""
            SELECT * FROM `{self.project_id}.vendors_ai.global_vendors`
            WHERE LOWER(global_name) = LOWER(@name)
            OR LOWER(name) = LOWER(@name)
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("name", "STRING", name)
                ]
            )
            
            results = list(self.client.query(query, job_config=job_config).result())
            return dict(results[0]) if results else None
        except Exception as e:
            print(f"Error finding vendor by name: {e}")
            return None
    
    def _update_vendor_netsuite_fields(self, vendor_id: str, netsuite_id: str, external_id: str):
        """Update vendor's NetSuite sync fields"""
        try:
            query = f"""
            UPDATE `{self.project_id}.vendors_ai.global_vendors`
            SET 
                custom_attributes = JSON_SET(
                    IFNULL(custom_attributes, JSON '{{}}'),
                    '$.netsuite_internal_id', @netsuite_id,
                    '$.external_id', @external_id,
                    '$.netsuite_sync_status', 'synced',
                    '$.netsuite_last_sync', CAST(CURRENT_TIMESTAMP() AS STRING)
                ),
                last_updated = CURRENT_TIMESTAMP()
            WHERE vendor_id = @vendor_id
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                    bigquery.ScalarQueryParameter("netsuite_id", "STRING", netsuite_id),
                    bigquery.ScalarQueryParameter("external_id", "STRING", external_id or "")
                ]
            )
            
            self.client.query(query, job_config=job_config).result()
            
        except Exception as e:
            print(f"Error updating vendor NetSuite fields: {e}")
            raise
    
    def _insert_vendor_to_bigquery(self, vendor_data: Dict):
        """Insert new vendor into BigQuery"""
        try:
            table_id = f"{self.project_id}.vendors_ai.global_vendors"
            table = self.client.get_table(table_id)
            
            # Convert datetime objects to ISO format strings
            if isinstance(vendor_data.get('created_at'), datetime):
                vendor_data['created_at'] = vendor_data['created_at'].isoformat()
            if isinstance(vendor_data.get('last_updated'), datetime):
                vendor_data['last_updated'] = vendor_data['last_updated'].isoformat()
            if isinstance(vendor_data.get('netsuite_last_sync'), datetime):
                vendor_data['netsuite_last_sync'] = vendor_data['netsuite_last_sync'].isoformat()
            
            errors = self.client.insert_rows_json(table, [vendor_data])
            
            if errors:
                raise Exception(f"Failed to insert vendor: {errors}")
                
        except Exception as e:
            print(f"Error inserting vendor to BigQuery: {e}")
            raise
    
    def pull_vendors_from_netsuite(self, last_modified_after: Optional[datetime] = None) -> Dict:
        """
        Pull all vendors from NetSuite and sync to BigQuery
        """
        try:
            # Search for vendors in NetSuite
            search_results = self.netsuite.search_vendors(
                last_modified_after=last_modified_after.isoformat() if last_modified_after else None
            )
            
            if not search_results:
                return {'success': True, 'message': 'No vendors to sync', 'count': 0}
            
            synced_count = 0
            failed_count = 0
            
            for netsuite_vendor in search_results:
                try:
                    # Check if vendor exists in our system
                    vendor_id = None
                    existing_query = f"""
                    SELECT vendor_id 
                    FROM `{self.project_id}.vendors_ai.global_vendors`
                    WHERE JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_internal_id') = @netsuite_id
                    LIMIT 1
                    """
                    
                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("netsuite_id", "STRING", str(netsuite_vendor.get('id')))
                        ]
                    )
                    
                    results = self.client.query(existing_query, job_config=job_config).result()
                    for row in results:
                        vendor_id = row.vendor_id
                    
                    if vendor_id:
                        # Update existing vendor
                        update_query = f"""
                        UPDATE `{self.project_id}.vendors_ai.global_vendors`
                        SET 
                            global_name = @name,
                            custom_attributes = JSON_SET(
                                IFNULL(custom_attributes, JSON '{{}}'),
                                '$.netsuite_sync_status', 'synced',
                                '$.netsuite_last_sync', CAST(CURRENT_TIMESTAMP() AS STRING)
                            ),
                            last_updated = CURRENT_TIMESTAMP()
                        WHERE vendor_id = @vendor_id
                        """
                        
                        job_config = bigquery.QueryJobConfig(
                            query_parameters=[
                                bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                                bigquery.ScalarQueryParameter("name", "STRING", netsuite_vendor.get('entityid', ''))
                            ]
                        )
                        
                        self.client.query(update_query, job_config=job_config).result()
                    else:
                        # Create new vendor
                        import uuid
                        vendor_id = f"NS_VENDOR_{str(uuid.uuid4())[:8].upper()}"
                        
                        vendor_data = {
                            'vendor_id': vendor_id,
                            'global_name': netsuite_vendor.get('entityid', ''),
                            'emails': [netsuite_vendor.get('email')] if netsuite_vendor.get('email') else [],
                            'phone_numbers': [netsuite_vendor.get('phone')] if netsuite_vendor.get('phone') else [],
                            'address': netsuite_vendor.get('address', ''),
                            'vendor_type': 'Company',
                            'netsuite_internal_id': str(netsuite_vendor.get('id')),
                            'netsuite_sync_status': 'synced',
                            'netsuite_last_sync': datetime.utcnow().isoformat(),
                            'created_at': datetime.utcnow().isoformat(),
                            'last_updated': datetime.utcnow().isoformat()
                        }
                        
                        table = self.client.get_table(f"{self.project_id}.vendors_ai.global_vendors")
                        errors = self.client.insert_rows_json(table, [vendor_data])
                        
                        if errors:
                            raise Exception(f"Failed to insert vendor: {errors}")
                    
                    synced_count += 1
                    
                except Exception as e:
                    print(f"Error syncing vendor from NetSuite: {e}")
                    failed_count += 1
            
            return {
                'success': True,
                'total': len(search_results),
                'synced': synced_count,
                'failed': failed_count
            }
            
        except Exception as e:
            print(f"Error pulling vendors from NetSuite: {e}")
            return {'success': False, 'error': str(e)}
    
    def sync_payment_status(self, invoice_id: str) -> Dict:
        """
        Sync payment status from NetSuite back to our platform
        """
        try:
            # Get invoice from BigQuery
            invoice = self.bigquery.get_invoice_details(invoice_id)
            if not invoice or not invoice.get('netsuite_bill_id'):
                return {'success': False, 'error': 'Invoice not synced to NetSuite'}
            
            # Get payment status from NetSuite
            payment_info = self.netsuite.get_bill_payment_status(invoice.get('netsuite_bill_id'))
            
            if payment_info and payment_info.get('success'):
                # Update payment status in BigQuery
                update_query = f"""
                UPDATE `{self.project_id}.vendors_ai.invoices`
                SET 
                    custom_attributes = JSON_SET(
                        IFNULL(custom_attributes, JSON '{{}}'),
                        '$.payment_status', @payment_status,
                        '$.payment_date', CAST(@payment_date AS STRING),
                        '$.payment_amount', @payment_amount,
                        '$.netsuite_sync_date', CAST(CURRENT_TIMESTAMP() AS STRING)
                    ),
                    updated_at = CURRENT_TIMESTAMP()
                WHERE invoice_id = @invoice_id
                """
                
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id),
                        bigquery.ScalarQueryParameter("payment_status", "STRING", payment_info.get('status', 'unpaid')),
                        bigquery.ScalarQueryParameter("payment_date", "DATE", payment_info.get('payment_date')),
                        bigquery.ScalarQueryParameter("payment_amount", "FLOAT64", payment_info.get('amount_paid', 0))
                    ]
                )
                
                self.client.query(update_query, job_config=job_config).result()
                
                return {
                    'success': True,
                    'payment_status': payment_info.get('status'),
                    'payment_date': payment_info.get('payment_date'),
                    'amount_paid': payment_info.get('amount_paid')
                }
            
            return {'success': False, 'error': 'Could not retrieve payment status'}
            
        except Exception as e:
            print(f"Error syncing payment status: {e}")
            return {'success': False, 'error': str(e)}
    
    def sync_all_payment_status(self, progress_callback=None) -> Dict:
        """
        Sync payment status for all invoices that have NetSuite bills
        
        Args:
            progress_callback: Optional callback function(step, total, message, data)
        
        Returns:
            Dict with sync statistics
        """
        stats = {
            'start_time': datetime.now(),
            'total_invoices': 0,
            'synced': 0,
            'paid': 0,
            'partial': 0,
            'pending': 0,
            'overdue': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            # Step 1: Get all invoices with NetSuite bills
            if progress_callback:
                progress_callback(1, 5, "Fetching invoices with NetSuite bills...", stats)
            
            query = f"""
            SELECT 
                invoice_id,
                JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_bill_id') as netsuite_bill_id,
                vendor_id,
                invoice_number,
                total_amount,
                JSON_EXTRACT_SCALAR(custom_attributes, '$.payment_status') as payment_status,
                JSON_EXTRACT_SCALAR(custom_attributes, '$.payment_date') as payment_date
            FROM `{self.project_id}.vendors_ai.invoices`
            WHERE JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_bill_id') IS NOT NULL
            """
            
            invoices = list(self.client.query(query).result())
            stats['total_invoices'] = len(invoices)
            
            if progress_callback:
                progress_callback(2, 5, f"Found {len(invoices)} invoices to sync", stats)
            
            # Step 2: Process each invoice
            for idx, invoice in enumerate(invoices):
                try:
                    if progress_callback and idx % 10 == 0:
                        progress_callback(
                            3, 5, 
                            f"Processing invoice {idx + 1}/{len(invoices)}...", 
                            stats
                        )
                    
                    # Get payment status from NetSuite
                    payment_info = self.netsuite.get_bill_payment_status(invoice['netsuite_bill_id'])
                    
                    if payment_info.get('success'):
                        # Update invoice with payment information
                        status = payment_info.get('status', 'pending')
                        payment_date = payment_info.get('payment_date')
                        payment_amount = payment_info.get('payment_amount', 0)
                        
                        # Update BigQuery
                        update_query = f"""
                        UPDATE `{self.project_id}.vendors_ai.invoices`
                        SET 
                            custom_attributes = JSON_SET(
                                IFNULL(custom_attributes, JSON '{{}}'),
                                '$.payment_status', @payment_status,
                                '$.payment_date', CAST(@payment_date AS STRING),
                                '$.payment_amount', @payment_amount,
                                '$.payment_sync_date', CAST(CURRENT_TIMESTAMP() AS STRING)
                            ),
                            updated_at = CURRENT_TIMESTAMP()
                        WHERE invoice_id = @invoice_id
                        """
                        
                        job_config = bigquery.QueryJobConfig(
                            query_parameters=[
                                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice['invoice_id']),
                                bigquery.ScalarQueryParameter("payment_status", "STRING", status),
                                bigquery.ScalarQueryParameter("payment_date", "DATE", payment_date),
                                bigquery.ScalarQueryParameter("payment_amount", "FLOAT64", payment_amount)
                            ]
                        )
                        
                        self.client.query(update_query, job_config=job_config).result()
                        
                        # Update statistics
                        stats['synced'] += 1
                        if status == 'paid':
                            stats['paid'] += 1
                        elif status == 'partial':
                            stats['partial'] += 1
                        elif status == 'pending':
                            stats['pending'] += 1
                        elif status == 'overdue':
                            stats['overdue'] += 1
                    else:
                        stats['failed'] += 1
                        stats['errors'].append(f"Invoice {invoice['invoice_number']}: {payment_info.get('error')}")
                        
                except Exception as e:
                    stats['failed'] += 1
                    stats['errors'].append(f"Invoice {invoice.get('invoice_number', 'Unknown')}: {str(e)}")
            
            # Step 3: Final statistics
            if progress_callback:
                progress_callback(4, 5, "Calculating final statistics...", stats)
            
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            stats['sync_rate'] = (stats['synced'] / stats['total_invoices'] * 100) if stats['total_invoices'] > 0 else 0
            
            # Log sync activity
            if self.bigquery:
                self.bigquery.log_netsuite_sync({
                    'entity_type': 'payment_status_bulk',
                    'entity_id': 'BULK_PAYMENT_SYNC',
                    'action': 'sync_all',
                    'status': 'success',
                    'details': {
                        'total_invoices': stats['total_invoices'],
                        'synced': stats['synced'],
                        'paid': stats['paid'],
                        'partial': stats['partial'],
                        'pending': stats['pending'],
                        'overdue': stats['overdue'],
                        'failed': stats['failed']
                    }
                })
            
            if progress_callback:
                progress_callback(5, 5, "Payment sync completed!", stats)
            
            return stats
            
        except Exception as e:
            print(f"Critical error in payment sync: {e}")
            stats['errors'].append(f"Critical error: {str(e)}")
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            if progress_callback:
                progress_callback(5, 5, f"Sync failed: {str(e)}", stats)
            
            return stats
    
    def sweep_unpaid_bills(self, progress_callback=None) -> Dict:
        """
        Sweep NetSuite for all unpaid bills and update their payment status
        
        Args:
            progress_callback: Optional callback function(step, total, message, data)
            
        Returns:
            Dict with sweep statistics
        """
        stats = {
            'start_time': datetime.now(),
            'total_bills': 0,
            'matched_invoices': 0,
            'updated': 0,
            'new_unpaid': 0,
            'errors': []
        }
        
        try:
            # Step 1: Fetch unpaid bills from NetSuite
            if progress_callback:
                progress_callback(1, 4, "Fetching unpaid bills from NetSuite...", stats)
            
            unpaid_bills = self.netsuite.search_unpaid_bills(limit=1000)
            
            if not unpaid_bills.get('success'):
                stats['errors'].append(f"Failed to fetch unpaid bills: {unpaid_bills.get('error')}")
                return stats
            
            bills = unpaid_bills.get('items', [])
            stats['total_bills'] = len(bills)
            
            if progress_callback:
                progress_callback(2, 4, f"Found {len(bills)} unpaid bills", stats)
            
            # Step 2: Match bills to invoices and update payment status
            for idx, bill in enumerate(bills):
                try:
                    if progress_callback and idx % 10 == 0:
                        progress_callback(
                            3, 4,
                            f"Processing bill {idx + 1}/{len(bills)}...",
                            stats
                        )
                    
                    # Find invoice by NetSuite bill ID
                    query = f"""
                    SELECT 
                        invoice_id, 
                        JSON_EXTRACT_SCALAR(custom_attributes, '$.payment_status') as payment_status
                    FROM `{self.project_id}.vendors_ai.invoices`
                    WHERE JSON_EXTRACT_SCALAR(custom_attributes, '$.netsuite_bill_id') = @bill_id
                    LIMIT 1
                    """
                    
                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[
                            bigquery.ScalarQueryParameter("bill_id", "STRING", str(bill.get('id')))
                        ]
                    )
                    
                    results = list(self.client.query(query, job_config=job_config).result())
                    
                    if results:
                        invoice = dict(results[0])
                        stats['matched_invoices'] += 1
                        
                        # Update payment status
                        payment_status = bill.get('payment_status', 'pending')
                        
                        update_query = f"""
                        UPDATE `{self.project_id}.vendors_ai.invoices`
                        SET 
                            custom_attributes = JSON_SET(
                                IFNULL(custom_attributes, JSON '{{}}'),
                                '$.payment_status', @payment_status,
                                '$.payment_sync_date', CAST(CURRENT_TIMESTAMP() AS STRING)
                            ),
                            updated_at = CURRENT_TIMESTAMP()
                        WHERE invoice_id = @invoice_id
                        """
                        
                        job_config = bigquery.QueryJobConfig(
                            query_parameters=[
                                bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice['invoice_id']),
                                bigquery.ScalarQueryParameter("payment_status", "STRING", payment_status)
                            ]
                        )
                        
                        self.client.query(update_query, job_config=job_config).result()
                        stats['updated'] += 1
                        
                        if invoice.get('payment_status') != payment_status:
                            stats['new_unpaid'] += 1
                            
                except Exception as e:
                    stats['errors'].append(f"Bill {bill.get('tranid', 'Unknown')}: {str(e)}")
            
            # Step 3: Final report
            if progress_callback:
                progress_callback(4, 4, "Payment sweep completed!", stats)
            
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            return stats
            
        except Exception as e:
            print(f"Critical error in payment sweep: {e}")
            stats['errors'].append(f"Critical error: {str(e)}")
            stats['end_time'] = datetime.now()
            stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
            
            if progress_callback:
                progress_callback(4, 4, f"Sweep failed: {str(e)}", stats)
            
            return stats
    
    def get_sync_status(self, entity_type: str = None) -> Dict:
        """
        Get overall sync status and statistics
        """
        try:
            stats = {}
            
            # Vendor sync stats
            if not entity_type or entity_type == 'vendor':
                vendor_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(netsuite_internal_id) as synced,
                    COUNT(CASE WHEN netsuite_sync_status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN netsuite_internal_id IS NULL THEN 1 END) as not_synced,
                    MAX(netsuite_last_sync) as last_sync
                FROM `{self.project_id}.vendors_ai.global_vendors`
                """
                
                results = self.client.query(vendor_query).result()
                for row in results:
                    stats['vendors'] = {
                        'total': row.total,
                        'synced': row.synced,
                        'failed': row.failed,
                        'not_synced': row.not_synced,
                        'sync_percentage': (row.synced / row.total * 100) if row.total > 0 else 0,
                        'last_sync': row.last_sync.isoformat() if row.last_sync else None
                    }
            
            # Invoice sync stats with payment status breakdown
            if not entity_type or entity_type == 'invoice':
                invoice_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(netsuite_bill_id) as synced,
                    COUNT(CASE WHEN netsuite_sync_status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN payment_status = 'paid' THEN 1 END) as paid,
                    COUNT(CASE WHEN payment_status = 'partial' THEN 1 END) as partial,
                    COUNT(CASE WHEN payment_status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN payment_status = 'overdue' THEN 1 END) as overdue,
                    MAX(netsuite_sync_date) as last_sync,
                    MAX(payment_sync_date) as last_payment_sync
                FROM `{self.project_id}.vendors_ai.invoices`
                """
                
                results = self.client.query(invoice_query).result()
                for row in results:
                    stats['invoices'] = {
                        'total': row.total,
                        'synced': row.synced,
                        'failed': row.failed,
                        'paid': row.paid,
                        'partial': row.partial,
                        'pending': row.pending,
                        'overdue': row.overdue,
                        'sync_percentage': (row.synced / row.total * 100) if row.total > 0 else 0,
                        'last_sync': row.last_sync.isoformat() if row.last_sync else None,
                        'last_payment_sync': row.last_payment_sync.isoformat() if row.last_payment_sync else None
                    }
            
            return {'success': True, 'stats': stats}
            
        except Exception as e:
            print(f"Error getting sync status: {e}")
            return {'success': False, 'error': str(e)}