"""
Authentication Service for Multi-Tenant SaaS Platform

Provides user authentication with Flask-Login and BigQuery-backed user storage.
Each user has isolated data accessed via owner_email filtering.
"""

import os
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask_login import LoginManager, UserMixin
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "invoicereader-477008"
DATASET_ID = "vendors_ai"
USERS_TABLE = f"{PROJECT_ID}.{DATASET_ID}.users"


class User(UserMixin):
    """Flask-Login compatible User class backed by BigQuery"""
    
    def __init__(self, email: str, password_hash: str, created_at: datetime, 
                 display_name: str = None, is_active: bool = True):
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at
        self.display_name = display_name or email.split('@')[0]
        self._is_active = is_active
    
    def get_id(self) -> str:
        return self.email
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @property
    def owner_email(self) -> str:
        return self.email
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'email': self.email,
            'display_name': self.display_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self._is_active
        }


class AuthService:
    """
    Handles user authentication and management with BigQuery storage.
    
    Features:
    - User registration and login
    - Secure password hashing (SHA-256 + salt)
    - Flask-Login integration
    - BigQuery-backed user storage
    """
    
    def __init__(self):
        self.client = self._get_bigquery_client()
        self._ensure_users_table()
    
    def _get_bigquery_client(self) -> bigquery.Client:
        """Get authenticated BigQuery client"""
        creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if creds_json:
            import json
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
            return bigquery.Client(project=PROJECT_ID, credentials=credentials)
        return bigquery.Client(project=PROJECT_ID)
    
    def _ensure_users_table(self):
        """Create users table if it doesn't exist"""
        schema = [
            bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("password_hash", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("password_salt", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("display_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("is_active", "BOOLEAN", mode="REQUIRED"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("last_login", "TIMESTAMP", mode="NULLABLE"),
        ]
        
        table_ref = bigquery.Table(USERS_TABLE, schema=schema)
        
        try:
            self.client.get_table(USERS_TABLE)
            print(f"✓ Users table {USERS_TABLE} already exists")
        except Exception:
            try:
                self.client.create_table(table_ref)
                print(f"✓ Created users table {USERS_TABLE}")
            except Exception as e:
                print(f"⚠️ Could not create users table: {e}")
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """Hash password with salt using SHA-256"""
        if salt is None:
            salt = secrets.token_hex(32)
        
        salted = f"{salt}{password}"
        password_hash = hashlib.sha256(salted.encode()).hexdigest()
        
        return password_hash, salt
    
    def _verify_password(self, password: str, stored_hash: str, salt: str) -> bool:
        """Verify password against stored hash"""
        computed_hash, _ = self._hash_password(password, salt)
        return computed_hash == stored_hash
    
    def register_user(self, email: str, password: str, display_name: str = None) -> Optional[User]:
        """
        Register a new user.
        
        Args:
            email: User's email address (used as unique identifier)
            password: Plain text password (will be hashed)
            display_name: Optional display name
            
        Returns:
            User object if registration successful, None if email already exists
        """
        email = email.lower().strip()
        
        if self.get_user_by_email(email):
            print(f"⚠️ User {email} already exists")
            return None
        
        password_hash, salt = self._hash_password(password)
        now = datetime.now(timezone.utc)
        
        row = {
            'email': email,
            'password_hash': password_hash,
            'password_salt': salt,
            'display_name': display_name or email.split('@')[0],
            'is_active': True,
            'created_at': now.isoformat(),
            'last_login': None
        }
        
        try:
            errors = self.client.insert_rows_json(USERS_TABLE, [row])
            if errors:
                print(f"❌ Failed to create user: {errors}")
                return None
            
            print(f"✓ Created user: {email}")
            return User(
                email=email,
                password_hash=password_hash,
                created_at=now,
                display_name=row['display_name'],
                is_active=True
            )
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            return None
    
    def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.
        
        Args:
            email: User's email address
            password: Plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        email = email.lower().strip()
        
        query = f"""
        SELECT email, password_hash, password_salt, display_name, is_active, created_at, last_login
        FROM `{USERS_TABLE}`
        WHERE email = @email
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            row = None
            for r in results:
                row = r
                break
            
            if not row:
                print(f"⚠️ User not found: {email}")
                return None
            
            if not row.is_active:
                print(f"⚠️ User account disabled: {email}")
                return None
            
            if not self._verify_password(password, row.password_hash, row.password_salt):
                print(f"⚠️ Invalid password for: {email}")
                return None
            
            self._update_last_login(email)
            
            return User(
                email=row.email,
                password_hash=row.password_hash,
                created_at=row.created_at,
                display_name=row.display_name,
                is_active=row.is_active
            )
            
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Load user by email (for Flask-Login user_loader)"""
        email = email.lower().strip()
        
        query = f"""
        SELECT email, password_hash, display_name, is_active, created_at
        FROM `{USERS_TABLE}`
        WHERE email = @email
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config).result()
            for row in results:
                return User(
                    email=row.email,
                    password_hash=row.password_hash,
                    created_at=row.created_at,
                    display_name=row.display_name,
                    is_active=row.is_active
                )
            return None
        except Exception as e:
            print(f"❌ Error loading user: {e}")
            return None
    
    def _update_last_login(self, email: str):
        """Update user's last login timestamp"""
        query = f"""
        UPDATE `{USERS_TABLE}`
        SET last_login = CURRENT_TIMESTAMP()
        WHERE email = @email
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        try:
            self.client.query(query, job_config=job_config).result()
        except Exception as e:
            print(f"⚠️ Could not update last login: {e}")
    
    def seed_initial_user(self, email: str = "barak@payouts.com", password: str = "123456789"):
        """
        Create the initial admin user if they don't exist.
        Called during app initialization to ensure there's always a valid user.
        """
        existing = self.get_user_by_email(email)
        if existing:
            print(f"✓ Initial user {email} already exists")
            return existing
        
        print(f"🌱 Seeding initial user: {email}")
        return self.register_user(email, password, display_name="Barak")
    
    def list_users(self, limit: int = 100) -> list:
        """List all users (admin function)"""
        query = f"""
        SELECT email, display_name, is_active, created_at, last_login
        FROM `{USERS_TABLE}`
        ORDER BY created_at DESC
        LIMIT {limit}
        """
        
        try:
            results = self.client.query(query).result()
            users = []
            for row in results:
                users.append({
                    'email': row.email,
                    'display_name': row.display_name,
                    'is_active': row.is_active,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'last_login': row.last_login.isoformat() if row.last_login else None
                })
            return users
        except Exception as e:
            print(f"❌ Error listing users: {e}")
            return []


_auth_service = None

def get_auth_service() -> AuthService:
    """Get singleton AuthService instance"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def init_login_manager(app):
    """
    Initialize Flask-Login with the app.
    Call this in app.py during initialization.
    
    Usage:
        from services.auth_service import init_login_manager
        init_login_manager(app)
    """
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        auth_service = get_auth_service()
        return auth_service.get_user_by_email(user_id)
    
    return login_manager
