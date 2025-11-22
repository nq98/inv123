import bcrypt
import secrets
import time
from functools import wraps
from flask import request, jsonify
from google.cloud import bigquery


class AgentAuthService:
    """Service for managing API key authentication for agent APIs"""
    
    def __init__(self, bigquery_service):
        self.bq = bigquery_service
        self._key_cache = {}
        self._cache_ttl = 3600
        
    def generate_api_key(self, client_id, description=""):
        """
        Generate a new API key for a client
        
        Args:
            client_id: Unique identifier for the client
            description: Optional description of the API key usage
            
        Returns:
            str: Generated API key (return once, user must save it)
        """
        api_key = f"sk_{secrets.token_urlsafe(32)}"
        api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()
        
        query = """
        INSERT INTO vendors_ai.api_keys (api_key_hash, client_id, description, created_at, active)
        VALUES (@hash, @client_id, @description, CURRENT_TIMESTAMP(), true)
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("hash", "STRING", api_key_hash),
                bigquery.ScalarQueryParameter("client_id", "STRING", client_id),
                bigquery.ScalarQueryParameter("description", "STRING", description),
            ]
        )
        
        self.bq.client.query(query, job_config=job_config).result()
        
        return api_key
        
    def validate_api_key(self, api_key):
        """
        Validate API key with caching and return client_id
        
        Args:
            api_key: API key to validate
            
        Returns:
            str|None: client_id if valid, None otherwise
        """
        if not api_key or not api_key.startswith('sk_'):
            return None
        
        current_time = time.time()
        
        if api_key in self._key_cache:
            cached_data = self._key_cache[api_key]
            if current_time - cached_data['timestamp'] < self._cache_ttl:
                return cached_data['client_id']
            else:
                del self._key_cache[api_key]
        
        query = "SELECT api_key_hash, client_id FROM `vendors_ai.api_keys` WHERE active = true"
        
        try:
            results = self.bq.client.query(query).result()
            
            for row in results:
                try:
                    if bcrypt.checkpw(api_key.encode(), row['api_key_hash'].encode()):
                        self._update_last_used(row['api_key_hash'])
                        
                        self._key_cache[api_key] = {
                            'client_id': row['client_id'],
                            'timestamp': current_time
                        }
                        
                        return row['client_id']
                except Exception as e:
                    print(f"Error validating API key: {e}")
                    continue
                    
            return None
        except Exception as e:
            print(f"Error querying API keys: {e}")
            return None
    
    def _update_last_used(self, api_key_hash):
        """Update last_used_at timestamp for an API key"""
        query = """
        UPDATE `vendors_ai.api_keys`
        SET last_used_at = CURRENT_TIMESTAMP()
        WHERE api_key_hash = @hash
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("hash", "STRING", api_key_hash),
            ]
        )
        
        try:
            self.bq.client.query(query, job_config=job_config).result()
        except Exception as e:
            print(f"Error updating last_used_at: {e}")


def require_agent_auth(f):
    """
    Decorator to require API key authentication for agent endpoints
    
    Usage:
        @app.route('/api/agent/test', methods=['GET'])
        @require_agent_auth
        def agent_test():
            return jsonify({'client_id': request.client_id})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        from app import get_bigquery_service
        
        api_key = request.headers.get('X-API-Key') or \
                 request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key required'}), 401
            
        auth_service = AgentAuthService(get_bigquery_service())
        client_id = auth_service.validate_api_key(api_key)
        
        if not client_id:
            return jsonify({'success': False, 'error': 'Invalid API key'}), 403
            
        request.client_id = client_id
        
        return f(*args, **kwargs)
    return decorated
