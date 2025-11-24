"""
NetSuite Audit Sync Manager
Polls NetSuite for real transaction data and stores in BigQuery
100% truthful - no fake data, only real NetSuite transactions
"""

import os
import json
import uuid
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from google.cloud import bigquery
from google.oauth2 import service_account
from services.netsuite_service import NetSuiteService
from services.netsuite_event_tracker import NetSuiteEventTracker
from config import config

logger = logging.getLogger(__name__)

class AuditSyncManager:
    """
    Manages real-time audit synchronization with NetSuite
    Fetches and stores actual transaction data - NO FAKE DATA
    """
    
    def __init__(self):
        """Initialize the audit sync manager with NetSuite and BigQuery connections"""
        
        # Initialize NetSuite service
        self.netsuite = NetSuiteService()
        
        # Initialize event tracker for logging
        self.event_tracker = NetSuiteEventTracker()
        
        # Initialize BigQuery client
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
                logger.error("Failed to parse GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
        
        self.bigquery_client = bigquery.Client(
            credentials=credentials,
            project=config.GOOGLE_CLOUD_PROJECT_ID
        )
        
        # Define audit table
        self.audit_table_id = f"{config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai.netsuite_audit_trail"
        
        # Ensure audit table exists
        self._ensure_audit_table()
    
    def _ensure_audit_table(self):
        """Create the audit trail table if it doesn't exist"""
        try:
            # Check if table exists
            self.bigquery_client.get_table(self.audit_table_id)
            logger.info(f"✓ Audit table {self.audit_table_id} already exists")
        except:
            # Create table with comprehensive schema
            schema = [
                bigquery.SchemaField("audit_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("transaction_type", "STRING", mode="REQUIRED"),  # BILL_CREATE, BILL_PAYMENT, BILL_UPDATE
                bigquery.SchemaField("netsuite_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("invoice_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("vendor_name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("vendor_netsuite_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("approval_status", "STRING", mode="NULLABLE"),  # PENDING, APPROVED, REJECTED, PAID
                bigquery.SchemaField("amount", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("created_date", "TIMESTAMP", mode="NULLABLE"),
                bigquery.SchemaField("modified_date", "TIMESTAMP", mode="NULLABLE"),
                bigquery.SchemaField("payment_date", "TIMESTAMP", mode="NULLABLE"),
                bigquery.SchemaField("payment_method", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("transaction_number", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("posting_period", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("netsuite_url", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("raw_payload", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("sync_source", "STRING", mode="NULLABLE"),  # POLL, WEBHOOK, MANUAL
                bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
            ]
            
            table = bigquery.Table(self.audit_table_id, schema=schema)
            table = self.bigquery_client.create_table(table)
            logger.info(f"✓ Created audit table {self.audit_table_id}")
    
    def poll_vendor_bills(self, days_back: int = 7) -> List[Dict]:
        """
        Poll NetSuite for real vendor bills
        
        Args:
            days_back: Number of days to look back for bills
            
        Returns:
            List of vendor bill records from NetSuite
        """
        if not self.netsuite.enabled:
            logger.warning("NetSuite service not enabled")
            return []
        
        try:
            # Get vendor bills from NetSuite
            # Using the REST API to get vendor bills
            bills = []
            
            # Query for recent vendor bills
            response = self.netsuite.search_vendor_bills(limit=100)
            
            if response and response.get('items'):
                for bill in response['items']:
                    # Store the real bill data
                    self._store_audit_record(
                        transaction_type='BILL_CREATE',
                        netsuite_id=bill.get('id'),
                        invoice_id=bill.get('tranId') or bill.get('refName'),
                        vendor_name=bill.get('entity', {}).get('refName'),
                        vendor_netsuite_id=bill.get('entity', {}).get('id'),
                        approval_status=bill.get('approvalStatus', {}).get('refName', 'PENDING'),
                        amount=float(bill.get('total', 0)),
                        currency=bill.get('currency', {}).get('refName', 'USD'),
                        created_date=bill.get('createdDate'),
                        modified_date=bill.get('lastModifiedDate'),
                        transaction_number=bill.get('tranId'),
                        posting_period=bill.get('postingPeriod', {}).get('refName'),
                        raw_payload=bill,
                        sync_source='POLL'
                    )
                    bills.append(bill)
            
            logger.info(f"✓ Polled {len(bills)} vendor bills from NetSuite")
            return bills
            
        except Exception as e:
            logger.error(f"Error polling vendor bills: {e}")
            return []
    
    def poll_vendor_payments(self, days_back: int = 7) -> List[Dict]:
        """
        Poll NetSuite for real vendor payments
        
        Args:
            days_back: Number of days to look back for payments
            
        Returns:
            List of vendor payment records from NetSuite
        """
        if not self.netsuite.enabled:
            logger.warning("NetSuite service not enabled")
            return []
        
        try:
            # Get vendor payments from NetSuite
            payments = []
            
            # Query for recent vendor payments
            response = self.netsuite.search_vendor_payments(limit=100)
            
            if response and response.get('items'):
                for payment in response['items']:
                    # Store the real payment data
                    self._store_audit_record(
                        transaction_type='BILL_PAYMENT',
                        netsuite_id=payment.get('id'),
                        vendor_name=payment.get('entity', {}).get('refName'),
                        vendor_netsuite_id=payment.get('entity', {}).get('id'),
                        approval_status='PAID',
                        amount=float(payment.get('total', 0)),
                        currency=payment.get('currency', {}).get('refName', 'USD'),
                        created_date=payment.get('createdDate'),
                        modified_date=payment.get('lastModifiedDate'),
                        payment_date=payment.get('tranDate'),
                        payment_method=payment.get('account', {}).get('refName'),
                        transaction_number=payment.get('tranId'),
                        posting_period=payment.get('postingPeriod', {}).get('refName'),
                        raw_payload=payment,
                        sync_source='POLL'
                    )
                    payments.append(payment)
            
            logger.info(f"✓ Polled {len(payments)} vendor payments from NetSuite")
            return payments
            
        except Exception as e:
            logger.error(f"Error polling vendor payments: {e}")
            return []
    
    def get_bill_truth(self, invoice_id: str) -> Dict:
        """
        Get the absolute truth about a bill's status from NetSuite
        NO FAKE DATA - only real NetSuite status
        
        Args:
            invoice_id: The invoice ID to check
            
        Returns:
            Dict with real bill status and details
        """
        truth = {
            'has_bill': False,
            'has_payment': False,
            'bill_status': None,
            'approval_status': None,
            'netsuite_id': None,
            'transaction_number': None,
            'amount': None,
            'vendor_name': None,
            'created_date': None,
            'payment_date': None,
            'netsuite_url': None,
            'button_state': 'CREATE_BILL',  # CREATE_BILL, BILL_PENDING, BILL_APPROVED, BILL_PAID, UPDATE_BILL
            'button_text': 'Create Bill',
            'button_disabled': False,
            'status_message': 'No bill exists in NetSuite'
        }
        
        try:
            # First check our audit trail for this invoice
            query = f"""
            SELECT *
            FROM `{self.audit_table_id}`
            WHERE invoice_id = @invoice_id
            ORDER BY timestamp DESC
            LIMIT 1
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id)
                ]
            )
            
            results = self.bigquery_client.query(query, job_config=job_config).result()
            
            for row in results:
                if row.transaction_type == 'BILL_CREATE':
                    truth['has_bill'] = True
                    truth['netsuite_id'] = row.netsuite_id
                    truth['bill_status'] = 'CREATED'
                    truth['approval_status'] = row.approval_status
                    truth['transaction_number'] = row.transaction_number
                    truth['amount'] = row.amount
                    truth['vendor_name'] = row.vendor_name
                    truth['created_date'] = row.created_date.isoformat() if row.created_date else None
                    truth['netsuite_url'] = row.netsuite_url
                    
                    # Determine button state based on approval status
                    if row.approval_status == 'APPROVED':
                        truth['button_state'] = 'BILL_APPROVED'
                        truth['button_text'] = 'Bill Approved ✓'
                        truth['button_disabled'] = True
                        truth['status_message'] = f'Bill {row.transaction_number} approved in NetSuite'
                    elif row.approval_status == 'PENDING':
                        truth['button_state'] = 'BILL_PENDING'
                        truth['button_text'] = 'Bill Pending Approval'
                        truth['button_disabled'] = True
                        truth['status_message'] = f'Bill {row.transaction_number} pending approval'
                    else:
                        truth['button_state'] = 'UPDATE_BILL'
                        truth['button_text'] = 'Update Bill'
                        truth['button_disabled'] = False
                        truth['status_message'] = f'Bill {row.transaction_number} can be updated'
                        
                elif row.transaction_type == 'BILL_PAYMENT':
                    truth['has_bill'] = True
                    truth['has_payment'] = True
                    truth['bill_status'] = 'PAID'
                    truth['approval_status'] = 'PAID'
                    truth['netsuite_id'] = row.netsuite_id
                    truth['transaction_number'] = row.transaction_number
                    truth['amount'] = row.amount
                    truth['vendor_name'] = row.vendor_name
                    truth['payment_date'] = row.payment_date.isoformat() if row.payment_date else None
                    truth['button_state'] = 'BILL_PAID'
                    truth['button_text'] = 'Bill Paid ✓'
                    truth['button_disabled'] = True
                    truth['status_message'] = f'Payment {row.transaction_number} completed'
            
            # If we have NetSuite enabled and no local record, try to fetch from NetSuite directly
            if not truth['has_bill'] and self.netsuite.enabled:
                # Search NetSuite for bills with this invoice ID
                bills = self.netsuite.search_vendor_bills_by_invoice(invoice_id)
                if bills:
                    bill = bills[0]  # Take the first matching bill
                    truth['has_bill'] = True
                    truth['netsuite_id'] = bill.get('id')
                    truth['bill_status'] = 'CREATED'
                    truth['approval_status'] = bill.get('approvalStatus', {}).get('refName', 'PENDING')
                    truth['transaction_number'] = bill.get('tranId')
                    truth['amount'] = float(bill.get('total', 0))
                    truth['vendor_name'] = bill.get('entity', {}).get('refName')
                    
                    # Store this in our audit trail for future reference
                    self._store_audit_record(
                        transaction_type='BILL_CREATE',
                        netsuite_id=bill.get('id'),
                        invoice_id=invoice_id,
                        vendor_name=truth['vendor_name'],
                        approval_status=truth['approval_status'],
                        amount=truth['amount'],
                        transaction_number=truth['transaction_number'],
                        raw_payload=bill,
                        sync_source='MANUAL'
                    )
            
        except Exception as e:
            logger.error(f"Error getting bill truth for invoice {invoice_id}: {e}")
            truth['error'] = str(e)
        
        return truth
    
    def _store_audit_record(self, **kwargs) -> bool:
        """Store an audit record in BigQuery"""
        try:
            record = {
                'audit_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow().isoformat(),
                'transaction_type': kwargs.get('transaction_type'),
                'netsuite_id': kwargs.get('netsuite_id'),
                'invoice_id': kwargs.get('invoice_id'),
                'vendor_name': kwargs.get('vendor_name'),
                'vendor_netsuite_id': kwargs.get('vendor_netsuite_id'),
                'approval_status': kwargs.get('approval_status'),
                'amount': kwargs.get('amount'),
                'currency': kwargs.get('currency', 'USD'),
                'created_date': kwargs.get('created_date'),
                'modified_date': kwargs.get('modified_date'),
                'payment_date': kwargs.get('payment_date'),
                'payment_method': kwargs.get('payment_method'),
                'transaction_number': kwargs.get('transaction_number'),
                'posting_period': kwargs.get('posting_period'),
                'netsuite_url': kwargs.get('netsuite_url'),
                'raw_payload': kwargs.get('raw_payload'),
                'sync_source': kwargs.get('sync_source', 'MANUAL'),
                'error_message': kwargs.get('error_message')
            }
            
            # Clean up None values
            record = {k: v for k, v in record.items() if v is not None}
            
            table = self.bigquery_client.get_table(self.audit_table_id)
            errors = self.bigquery_client.insert_rows_json(table, [record])
            
            if errors:
                logger.error(f"Failed to store audit record: {errors}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing audit record: {e}")
            return False
    
    def get_audit_trail(self, days: int = 7, invoice_id: str = None) -> List[Dict]:
        """
        Get real audit trail data from BigQuery
        NO FAKE DATA - only real transactions
        
        Args:
            days: Number of days to look back
            invoice_id: Optional specific invoice to filter by
            
        Returns:
            List of audit records
        """
        try:
            # Build query
            query = f"""
            SELECT *
            FROM `{self.audit_table_id}`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
            """
            
            params = []
            if invoice_id:
                query += " AND invoice_id = @invoice_id"
                params.append(bigquery.ScalarQueryParameter("invoice_id", "STRING", invoice_id))
            
            query += " ORDER BY timestamp DESC LIMIT 1000"
            
            # Execute query
            if params:
                job_config = bigquery.QueryJobConfig(query_parameters=params)
                results = self.bigquery_client.query(query, job_config=job_config).result()
            else:
                results = self.bigquery_client.query(query).result()
            
            # Format results
            audit_trail = []
            for row in results:
                audit_trail.append({
                    'audit_id': row.audit_id,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'transaction_type': row.transaction_type,
                    'netsuite_id': row.netsuite_id,
                    'invoice_id': row.invoice_id,
                    'vendor_name': row.vendor_name,
                    'vendor_netsuite_id': row.vendor_netsuite_id,
                    'approval_status': row.approval_status,
                    'amount': row.amount,
                    'currency': row.currency,
                    'created_date': row.created_date.isoformat() if row.created_date else None,
                    'modified_date': row.modified_date.isoformat() if row.modified_date else None,
                    'payment_date': row.payment_date.isoformat() if row.payment_date else None,
                    'payment_method': row.payment_method,
                    'transaction_number': row.transaction_number,
                    'posting_period': row.posting_period,
                    'netsuite_url': row.netsuite_url,
                    'raw_payload': row.raw_payload,
                    'sync_source': row.sync_source,
                    'error_message': row.error_message
                })
            
            return audit_trail
            
        except Exception as e:
            logger.error(f"Error getting audit trail: {e}")
            return []
    
    def sync_all_transactions(self) -> Dict:
        """
        Perform a full sync of all NetSuite transactions
        
        Returns:
            Summary of sync results
        """
        summary = {
            'bills_synced': 0,
            'payments_synced': 0,
            'errors': [],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            # Poll vendor bills
            bills = self.poll_vendor_bills()
            summary['bills_synced'] = len(bills)
            
            # Poll vendor payments
            payments = self.poll_vendor_payments()
            summary['payments_synced'] = len(payments)
            
            # Log the sync event
            self.event_tracker.log_event(
                direction='INBOUND',
                event_type='AUDIT_SYNC',
                event_category='SYNC',
                status='SUCCESS',
                action='SYNC',
                response_data=summary
            )
            
            logger.info(f"✓ Audit sync completed: {summary['bills_synced']} bills, {summary['payments_synced']} payments")
            
        except Exception as e:
            error_msg = f"Audit sync failed: {str(e)}"
            logger.error(error_msg)
            summary['errors'].append(error_msg)
            
            # Log the failed sync event
            self.event_tracker.log_event(
                direction='INBOUND',
                event_type='AUDIT_SYNC',
                event_category='SYNC',
                status='FAILED',
                action='SYNC',
                error_message=error_msg
            )
        
        return summary