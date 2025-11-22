import uuid
from datetime import datetime

class IssueDetector:
    def __init__(self, bigquery_service):
        self.bq = bigquery_service
    
    def detect_all_issues(self, client_id=None):
        """Detect all compliance issues"""
        issues = []
        
        # Detect missing W-9s
        issues.extend(self.detect_missing_w9(client_id))
        
        # Detect duplicate invoices
        issues.extend(self.detect_duplicate_invoices(client_id))
        
        return issues
    
    def detect_missing_w9(self, client_id=None):
        """Find vendors with invoices but missing W-9"""
        query = """
        SELECT 
            vendor_id,
            vendor_name,
            vendor_email,
            COUNT(*) as invoice_count,
            SUM(amount) as total_spend
        FROM vendors_ai.invoices
        WHERE has_w9 = false
        {}
        GROUP BY vendor_id, vendor_name, vendor_email
        HAVING invoice_count > 0
        """.format('AND client_id = @client_id' if client_id else '')
        
        params = {'client_id': client_id} if client_id else {}
        results = self.bq.query(query, params)
        
        issues = []
        for row in results:
            issue_id = f"ISS-{uuid.uuid4().hex[:8].upper()}"
            issues.append({
                'issue_id': issue_id,
                'type': 'missing_w9',
                'severity': 'high' if row['total_spend'] > 10000 else 'medium',
                'vendor_id': row['vendor_id'],
                'vendor_name': row['vendor_name'],
                'vendor_email': row['vendor_email'],
                'description': f"Vendor {row['vendor_name']} has {row['invoice_count']} invoices totaling ${row['total_spend']:.2f} but no W-9 on file",
                'client_id': client_id or 'all'
            })
        
        return issues
    
    def detect_duplicate_invoices(self, client_id=None):
        """Find potential duplicate invoices"""
        query = """
        SELECT 
            vendor_name,
            amount,
            invoice_date,
            ARRAY_AGG(invoice_id) as invoice_ids
        FROM vendors_ai.invoices
        WHERE 1=1
        {}
        GROUP BY vendor_name, amount, invoice_date
        HAVING COUNT(*) > 1
        """.format('AND client_id = @client_id' if client_id else '')
        
        params = {'client_id': client_id} if client_id else {}
        results = self.bq.query(query, params)
        
        issues = []
        for row in results:
            issue_id = f"ISS-{uuid.uuid4().hex[:8].upper()}"
            issues.append({
                'issue_id': issue_id,
                'type': 'duplicate_invoice',
                'severity': 'medium',
                'vendor_name': row['vendor_name'],
                'invoice_ids': row['invoice_ids'],
                'description': f"Multiple invoices ({len(row['invoice_ids'])}) from {row['vendor_name']} with same amount ${row['amount']} on {row['invoice_date']}",
                'client_id': client_id or 'all'
            })
        
        return issues
