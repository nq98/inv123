"""
NetSuite Synchronization Manager
Handles bidirectional sync between our platform and NetSuite
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from google.cloud import bigquery
from services.bigquery_service import BigQueryService
from services.netsuite_service import NetSuiteService
from config import config

class SyncManager:
    """Manages complete synchronization between platform and NetSuite"""
    
    def __init__(self):
        self.bigquery = BigQueryService()
        self.netsuite = NetSuiteService()
        self.client = self.bigquery.client
        self.project_id = config.GOOGLE_CLOUD_PROJECT_ID
        
    def update_vendor_schema(self):
        """Add sync tracking fields to vendor table"""
        try:
            # Add new columns to vendor table if they don't exist
            table_id = f"{self.project_id}.vendors_ai.global_vendors"
            table = self.client.get_table(table_id)
            
            existing_fields = {field.name for field in table.schema}
            new_fields = []
            
            # Add sync tracking fields if missing
            if 'netsuite_sync_status' not in existing_fields:
                new_fields.append(bigquery.SchemaField("netsuite_sync_status", "STRING", mode="NULLABLE"))
            if 'netsuite_last_sync' not in existing_fields:
                new_fields.append(bigquery.SchemaField("netsuite_last_sync", "TIMESTAMP", mode="NULLABLE"))
            if 'netsuite_sync_error' not in existing_fields:
                new_fields.append(bigquery.SchemaField("netsuite_sync_error", "STRING", mode="NULLABLE"))
            if 'payment_status' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_status", "STRING", mode="NULLABLE"))
            if 'payment_date' not in existing_fields:
                new_fields.append(bigquery.SchemaField("payment_date", "DATE", mode="NULLABLE"))
                
            if new_fields:
                new_schema = table.schema + new_fields
                table.schema = new_schema
                table = self.client.update_table(table, ["schema"])
                print(f"✓ Updated vendor table with {len(new_fields)} new sync fields")
            else:
                print("✓ Vendor table already has all sync fields")
                
            return True
        except Exception as e:
            print(f"Error updating vendor schema: {e}")
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
            
            result = self.netsuite.sync_vendor_to_netsuite(sync_data)
            
            # Update sync status in BigQuery
            update_query = f"""
            UPDATE `{self.project_id}.vendors_ai.global_vendors`
            SET 
                netsuite_internal_id = @netsuite_id,
                netsuite_sync_status = @sync_status,
                netsuite_last_sync = CURRENT_TIMESTAMP(),
                netsuite_sync_error = @sync_error
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
            
            self.client.query(update_query, job_config=job_config).result()
            
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
                    WHERE netsuite_internal_id = @netsuite_id
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
                            netsuite_sync_status = 'synced',
                            netsuite_last_sync = CURRENT_TIMESTAMP(),
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
                    payment_status = @payment_status,
                    payment_date = @payment_date,
                    payment_amount = @payment_amount,
                    netsuite_sync_date = CURRENT_TIMESTAMP()
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
            
            # Invoice sync stats
            if not entity_type or entity_type == 'invoice':
                invoice_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(netsuite_bill_id) as synced,
                    COUNT(CASE WHEN netsuite_sync_status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN payment_status = 'paid' THEN 1 END) as paid,
                    COUNT(CASE WHEN payment_status = 'unpaid' THEN 1 END) as unpaid,
                    MAX(netsuite_sync_date) as last_sync
                FROM `{self.project_id}.vendors_ai.invoices`
                """
                
                results = self.client.query(invoice_query).result()
                for row in results:
                    stats['invoices'] = {
                        'total': row.total,
                        'synced': row.synced,
                        'failed': row.failed,
                        'paid': row.paid,
                        'unpaid': row.unpaid,
                        'sync_percentage': (row.synced / row.total * 100) if row.total > 0 else 0,
                        'last_sync': row.last_sync.isoformat() if row.last_sync else None
                    }
            
            return {'success': True, 'stats': stats}
            
        except Exception as e:
            print(f"Error getting sync status: {e}")
            return {'success': False, 'error': str(e)}