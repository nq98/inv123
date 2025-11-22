import uuid
from datetime import datetime

class ActionManager:
    def __init__(self, bigquery_service, gmail_service):
        self.bq = bigquery_service
        self.gmail = gmail_service
    
    def create_action(self, action_type, vendor_id, vendor_email, 
                     email_subject, email_body, client_id, issue_id=None, priority='medium'):
        """Create a pending action"""
        action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
        
        query = """
        INSERT INTO vendors_ai.agent_actions 
        (action_id, action_type, status, priority, vendor_id, vendor_email,
         client_id, issue_id, email_subject, email_body, created_at)
        VALUES (@action_id, @action_type, 'pending_approval', @priority, 
                @vendor_id, @vendor_email, @client_id, @issue_id, 
                @email_subject, @email_body, CURRENT_TIMESTAMP())
        """
        
        self.bq.execute_query(query, {
            'action_id': action_id,
            'action_type': action_type,
            'priority': priority,
            'vendor_id': vendor_id,
            'vendor_email': vendor_email,
            'client_id': client_id,
            'issue_id': issue_id,
            'email_subject': email_subject,
            'email_body': email_body
        })
        
        return action_id
    
    def get_pending_actions(self, client_id):
        """Get all pending actions for a client"""
        query = """
        SELECT * FROM vendors_ai.agent_actions
        WHERE client_id = @client_id AND status = 'pending_approval'
        ORDER BY created_at DESC
        """
        return list(self.bq.query(query, {'client_id': client_id}))
    
    def approve_action(self, action_id, client_id, approved=True, modified_email=None):
        """Approve or reject an action"""
        if not approved:
            query = """
            UPDATE vendors_ai.agent_actions
            SET status = 'rejected', approved_at = CURRENT_TIMESTAMP()
            WHERE action_id = @action_id AND client_id = @client_id
            """
            self.bq.execute_query(query, {'action_id': action_id, 'client_id': client_id})
            return {'success': True, 'status': 'rejected'}
        
        action = self.get_action(action_id, client_id)
        if not action:
            return {'success': False, 'error': 'Action not found'}
        
        subject = modified_email.get('subject', action['email_subject']) if modified_email else action['email_subject']
        body = modified_email.get('body', action['email_body']) if modified_email else action['email_body']
        
        email_sent = self.gmail.send_email(action['vendor_email'], subject, body)
        
        query = """
        UPDATE vendors_ai.agent_actions
        SET status = @status, approved_at = CURRENT_TIMESTAMP(), sent_at = CURRENT_TIMESTAMP()
        WHERE action_id = @action_id AND client_id = @client_id
        """
        self.bq.execute_query(query, {
            'action_id': action_id,
            'client_id': client_id,
            'status': 'sent' if email_sent else 'failed'
        })
        
        return {'success': True, 'status': 'sent', 'email_sent': email_sent}
    
    def get_action(self, action_id, client_id):
        """Get a specific action"""
        query = """
        SELECT * FROM vendors_ai.agent_actions
        WHERE action_id = @action_id AND client_id = @client_id
        """
        results = list(self.bq.query(query, {'action_id': action_id, 'client_id': client_id}))
        return results[0] if results else None
