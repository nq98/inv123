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
                    vendor_data = {
                        'name': ns_vendor.get('companyName', ''),
                        'email': ns_vendor.get('email', ''),
                        'phone': ns_vendor.get('phone', ''),
                        'tax_id': ns_vendor.get('defaultTaxReg', ''),
                        'address': self._format_netsuite_address(ns_vendor.get('defaultAddress', {})),
                        'netsuite_internal_id': str(ns_vendor.get('id', '')),
                        'external_id': ns_vendor.get('externalId', ''),
                        'source_system': 'NETSUITE'
                    }
                    
                    # Check if vendor exists in BigQuery
                    existing_vendor = None
                    
                    # Try to find by tax ID first
                    if vendor_data['tax_id']:
                        existing_vendor = self._find_vendor_by_tax_id(vendor_data['tax_id'])
                    
                    # If not found by tax ID, try by name
                    if not existing_vendor and vendor_data['name']:
                        existing_vendor = self._find_vendor_by_name(vendor_data['name'])
                    
                    if existing_vendor:
                        # Update existing vendor with NetSuite info
                        self._update_vendor_netsuite_fields(
                            existing_vendor['vendor_id'],
                            vendor_data['netsuite_internal_id'],
                            vendor_data['external_id']
                        )
                        stats['updated_vendors'] += 1
                    else:
                        # Create new vendor
                        new_vendor_id = str(uuid.uuid4())
                        vendor_data['vendor_id'] = new_vendor_id
                        vendor_data['global_name'] = vendor_data['name']
                        vendor_data['created_at'] = datetime.now()
                        vendor_data['last_updated'] = datetime.now()
                        vendor_data['netsuite_sync_status'] = 'synced'
                        vendor_data['netsuite_last_sync'] = datetime.now()
                        
                        # Format for BigQuery
                        vendor_data['emails'] = [vendor_data['email']] if vendor_data['email'] else []
                        vendor_data['phone_numbers'] = [vendor_data['phone']] if vendor_data['phone'] else []
                        del vendor_data['email']
                        del vendor_data['phone']
                        
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
                netsuite_internal_id = @netsuite_id,
                external_id = @external_id,
                netsuite_sync_status = 'synced',
                netsuite_last_sync = CURRENT_TIMESTAMP(),
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
                netsuite_bill_id,
                vendor_id,
                invoice_number,
                total_amount,
                payment_status,
                payment_date
            FROM `{self.project_id}.vendors_ai.invoices`
            WHERE netsuite_bill_id IS NOT NULL
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
                            payment_status = @payment_status,
                            payment_date = @payment_date,
                            payment_amount = @payment_amount,
                            payment_sync_date = CURRENT_TIMESTAMP()
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
                    SELECT invoice_id, payment_status
                    FROM `{self.project_id}.vendors_ai.invoices`
                    WHERE netsuite_bill_id = @bill_id
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
                            payment_status = @payment_status,
                            payment_sync_date = CURRENT_TIMESTAMP()
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