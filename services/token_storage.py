import os
import json
import secrets
from cryptography.fernet import Fernet
from datetime import datetime

class SecureTokenStorage:
    """Secure server-side storage for OAuth tokens with encryption"""
    
    def __init__(self):
        self.storage_dir = 'secure_tokens'
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Get or create encryption key
        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)
    
    def _get_or_create_key(self):
        """Get existing encryption key or create a new one"""
        key_path = os.path.join(self.storage_dir, '.key')
        
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(key)
            os.chmod(key_path, 0o600)  # Read/write for owner only
            return key
    
    def store_credentials(self, credentials):
        """
        Store OAuth credentials securely and return a session token
        
        Args:
            credentials: Dictionary with OAuth token data
            
        Returns:
            session_token: Opaque token to use as session identifier
        """
        session_token = secrets.token_urlsafe(32)
        
        credentials_data = {
            'credentials': credentials,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Encrypt the credentials
        encrypted_data = self.cipher.encrypt(
            json.dumps(credentials_data).encode('utf-8')
        )
        
        # Store encrypted data with session token as filename
        token_path = os.path.join(self.storage_dir, f"{session_token}.enc")
        with open(token_path, 'wb') as f:
            f.write(encrypted_data)
        
        os.chmod(token_path, 0o600)  # Read/write for owner only
        
        return session_token
    
    def get_credentials(self, session_token):
        """
        Retrieve credentials using session token
        
        Args:
            session_token: Session identifier
            
        Returns:
            credentials dictionary or None if not found
        """
        if not session_token:
            return None
        
        token_path = os.path.join(self.storage_dir, f"{session_token}.enc")
        
        if not os.path.exists(token_path):
            return None
        
        try:
            with open(token_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            credentials_data = json.loads(decrypted_data.decode('utf-8'))
            
            return credentials_data['credentials']
        
        except Exception as e:
            print(f"Error retrieving credentials: {e}")
            return None
    
    def delete_credentials(self, session_token):
        """Delete stored credentials"""
        if not session_token:
            return
        
        token_path = os.path.join(self.storage_dir, f"{session_token}.enc")
        
        if os.path.exists(token_path):
            os.remove(token_path)
    
    def cleanup_old_tokens(self, max_age_hours=24):
        """Remove tokens older than max_age_hours"""
        from datetime import timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.enc'):
                token_path = os.path.join(self.storage_dir, filename)
                
                try:
                    with open(token_path, 'rb') as f:
                        encrypted_data = f.read()
                    
                    decrypted_data = self.cipher.decrypt(encrypted_data)
                    credentials_data = json.loads(decrypted_data.decode('utf-8'))
                    
                    created_at = datetime.fromisoformat(credentials_data['created_at'])
                    
                    if created_at < cutoff_time:
                        os.remove(token_path)
                        print(f"Removed old token: {filename}")
                
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    # Remove corrupted files
                    os.remove(token_path)
