"""
Cancellation Assistant Service - AI-powered subscription cancellation helper

This service uses Gemini AI to help users cancel subscriptions by:
1. Analyzing vendor cancellation difficulty (dark patterns)
2. Finding cancellation portals/methods
3. Generating personalized cancellation emails
4. Providing step-by-step cancellation guides
5. Tracking cancellation attempts
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.cloud import bigquery


class CancellationAssistantService:
    """AI-powered service to help users cancel subscriptions"""
    
    def __init__(self):
        self.openrouter_client = None
        self.bq_client = None
        self._init_ai_client()
        self._init_bigquery()
        self._ensure_tables_exist()
        
    def _init_ai_client(self):
        """Initialize OpenRouter client for Gemini"""
        try:
            from openai import OpenAI
            api_key = os.getenv('OPENROUTER_API_KEY')
            if not api_key:
                api_key = os.getenv('LANGCHAIN_API_KEY')
            
            if api_key:
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                    timeout=60.0
                )
                print("✅ [Cancellation Assistant] AI client initialized")
        except Exception as e:
            print(f"⚠️ [Cancellation Assistant] AI init error: {e}")
            
    def _init_bigquery(self):
        """Initialize BigQuery client"""
        try:
            sa_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            if sa_json:
                import json as json_module
                from google.oauth2 import service_account
                sa_info = json_module.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
                self.bq_client = bigquery.Client(credentials=credentials, project=sa_info.get('project_id'))
            else:
                self.bq_client = bigquery.Client()
        except Exception as e:
            print(f"⚠️ [Cancellation Assistant] BigQuery init error: {e}")
            
    def _ensure_tables_exist(self):
        """Create tables if they don't exist"""
        if not self.bq_client:
            return
            
        dataset_id = "invoicereader-477008.vendors_ai"
        
        knowledge_schema = [
            bigquery.SchemaField("vendor_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_domain", "STRING"),
            bigquery.SchemaField("cancellation_method", "STRING"),
            bigquery.SchemaField("cancellation_url", "STRING"),
            bigquery.SchemaField("cancellation_email", "STRING"),
            bigquery.SchemaField("cancellation_phone", "STRING"),
            bigquery.SchemaField("dark_pattern_score", "INTEGER"),
            bigquery.SchemaField("cancellation_steps", "STRING"),
            bigquery.SchemaField("notes", "STRING"),
            bigquery.SchemaField("last_verified", "TIMESTAMP"),
            bigquery.SchemaField("verified_by", "STRING"),
        ]
        
        requests_schema = [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("user_email", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("subscription_amount", "FLOAT"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("cancellation_method", "STRING"),
            bigquery.SchemaField("ai_strategy", "STRING"),
            bigquery.SchemaField("email_draft", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
            bigquery.SchemaField("cancelled_at", "TIMESTAMP"),
            bigquery.SchemaField("notes", "STRING"),
        ]
        
        tables = [
            ("cancellation_knowledge", knowledge_schema),
            ("cancellation_requests", requests_schema),
        ]
        
        for table_name, schema in tables:
            table_ref = f"{dataset_id}.{table_name}"
            try:
                self.bq_client.get_table(table_ref)
            except:
                table = bigquery.Table(table_ref, schema=schema)
                self.bq_client.create_table(table)
                print(f"✅ Created table {table_ref}")
                
    def get_cancellation_help(self, vendor_name: str, amount: float = None, 
                              billing_email: str = None, user_email: str = None) -> Dict:
        """
        Get AI-powered cancellation help for a subscription
        
        Returns:
        - Cancellation difficulty score (1-5)
        - Cancellation method (portal, email, phone, chat)
        - Step-by-step guide
        - Draft cancellation email
        - Direct cancellation link if available
        """
        
        if not self.openrouter_client:
            return {"error": "AI service not available"}
            
        existing_knowledge = self._get_vendor_knowledge(vendor_name)
        
        prompt = f"""You are a subscription cancellation expert. Help the user cancel their subscription to {vendor_name}.

SUBSCRIPTION DETAILS:
- Vendor: {vendor_name}
- Monthly Amount: ${amount:.2f if amount else 'Unknown'}
- Billing Email: {billing_email or 'Not provided'}

{f"KNOWN CANCELLATION INFO: {json.dumps(existing_knowledge)}" if existing_knowledge else ""}

PROVIDE A COMPREHENSIVE CANCELLATION GUIDE:

1. DARK_PATTERN_SCORE (1-5):
   1 = Very Easy (one-click cancel in settings)
   2 = Easy (cancel in account settings)
   3 = Medium (requires multiple steps or chat)
   4 = Hard (requires calling or special procedure)
   5 = Very Hard (intentionally difficult, retention calls required)

2. CANCELLATION_METHOD: One of [portal, email, phone, chat, mixed]

3. CANCELLATION_URL: Direct link to cancellation page if known (or best guess based on common patterns like /account/billing, /settings/subscription)

4. STEP_BY_STEP_GUIDE: Numbered list of exact steps to cancel

5. DRAFT_EMAIL: If email is needed, write a professional cancellation request email ready to send. Include:
   - Subject line
   - Request to cancel immediately
   - Request for confirmation
   - Request for no retention offers

6. TIPS: Any insider tips for faster cancellation

7. WARNINGS: Any dark patterns or tricks to watch out for

8. EXPECTED_TIMELINE: How long the cancellation typically takes

Return as JSON:
{{
  "vendor_name": "{vendor_name}",
  "dark_pattern_score": <1-5>,
  "difficulty_label": "<Very Easy|Easy|Medium|Hard|Very Hard>",
  "cancellation_method": "<portal|email|phone|chat|mixed>",
  "cancellation_url": "<url or null>",
  "cancellation_email": "<email or null>",
  "cancellation_phone": "<phone or null>",
  "steps": ["step1", "step2", ...],
  "draft_email": {{
    "subject": "...",
    "body": "..."
  }},
  "tips": ["tip1", "tip2"],
  "warnings": ["warning1", "warning2"],
  "expected_timeline": "...",
  "confidence": <0.0-1.0>
}}
"""

        try:
            response = self.openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                
                if user_email:
                    self._save_cancellation_request(user_email, vendor_name, amount, result)
                
                if result.get('confidence', 0) > 0.7:
                    self._update_vendor_knowledge(vendor_name, result)
                    
                return result
            else:
                return {"error": "Failed to parse AI response", "raw": content}
                
        except Exception as e:
            print(f"AI error: {e}")
            return {"error": str(e)}
            
    def _get_vendor_knowledge(self, vendor_name: str) -> Optional[Dict]:
        """Get existing knowledge about a vendor's cancellation process"""
        if not self.bq_client:
            return None
            
        query = """
            SELECT * FROM `invoicereader-477008.vendors_ai.cancellation_knowledge`
            WHERE LOWER(vendor_name) = LOWER(@vendor_name)
            LIMIT 1
        """
        
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_name", "STRING", vendor_name)
                ]
            )
            results = self.bq_client.query(query, job_config=job_config).result()
            for row in results:
                return dict(row)
        except:
            pass
        return None
        
    def _update_vendor_knowledge(self, vendor_name: str, data: Dict):
        """Update or insert vendor cancellation knowledge"""
        if not self.bq_client:
            return
            
        table_ref = "invoicereader-477008.vendors_ai.cancellation_knowledge"
        
        row = {
            "vendor_name": vendor_name,
            "vendor_domain": self._extract_domain(vendor_name),
            "cancellation_method": data.get("cancellation_method"),
            "cancellation_url": data.get("cancellation_url"),
            "cancellation_email": data.get("cancellation_email"),
            "cancellation_phone": data.get("cancellation_phone"),
            "dark_pattern_score": data.get("dark_pattern_score"),
            "cancellation_steps": json.dumps(data.get("steps", [])),
            "notes": json.dumps({"tips": data.get("tips"), "warnings": data.get("warnings")}),
            "last_verified": datetime.utcnow().isoformat(),
            "verified_by": "ai_generated",
        }
        
        try:
            delete_query = f"""
                DELETE FROM `{table_ref}` WHERE LOWER(vendor_name) = LOWER(@vendor_name)
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_name", "STRING", vendor_name)
                ]
            )
            self.bq_client.query(delete_query, job_config=job_config).result()
            
            errors = self.bq_client.insert_rows_json(table_ref, [row])
            if errors:
                print(f"Knowledge insert errors: {errors}")
        except Exception as e:
            print(f"Knowledge update error: {e}")
            
    def _save_cancellation_request(self, user_email: str, vendor_name: str, 
                                    amount: float, ai_result: Dict):
        """Save a cancellation request for tracking"""
        if not self.bq_client:
            return
            
        import uuid
        table_ref = "invoicereader-477008.vendors_ai.cancellation_requests"
        
        row = {
            "id": str(uuid.uuid4()),
            "user_email": user_email,
            "vendor_name": vendor_name,
            "subscription_amount": amount,
            "status": "pending",
            "cancellation_method": ai_result.get("cancellation_method"),
            "ai_strategy": json.dumps(ai_result),
            "email_draft": json.dumps(ai_result.get("draft_email", {})),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        try:
            errors = self.bq_client.insert_rows_json(table_ref, [row])
            if errors:
                print(f"Request save errors: {errors}")
        except Exception as e:
            print(f"Request save error: {e}")
            
    def _extract_domain(self, vendor_name: str) -> str:
        """Extract likely domain from vendor name"""
        clean = vendor_name.lower().replace(" ", "").replace(".", "")
        return f"{clean}.com"
        
    def get_user_cancellation_requests(self, user_email: str) -> List[Dict]:
        """Get all cancellation requests for a user"""
        if not self.bq_client:
            return []
            
        query = """
            SELECT * FROM `invoicereader-477008.vendors_ai.cancellation_requests`
            WHERE user_email = @user_email
            ORDER BY created_at DESC
        """
        
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("user_email", "STRING", user_email)
                ]
            )
            results = self.bq_client.query(query, job_config=job_config).result()
            return [dict(row) for row in results]
        except Exception as e:
            print(f"Error fetching requests: {e}")
            return []
            
    def update_cancellation_status(self, request_id: str, status: str, notes: str = None):
        """Update the status of a cancellation request"""
        if not self.bq_client:
            return False
            
        update_query = """
            UPDATE `invoicereader-477008.vendors_ai.cancellation_requests`
            SET status = @status, 
                updated_at = @updated_at,
                cancelled_at = @cancelled_at,
                notes = @notes
            WHERE id = @request_id
        """
        
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("status", "STRING", status),
                    bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", datetime.utcnow().isoformat()),
                    bigquery.ScalarQueryParameter("cancelled_at", "TIMESTAMP", 
                        datetime.utcnow().isoformat() if status == "cancelled" else None),
                    bigquery.ScalarQueryParameter("notes", "STRING", notes),
                    bigquery.ScalarQueryParameter("request_id", "STRING", request_id),
                ]
            )
            self.bq_client.query(update_query, job_config=job_config).result()
            return True
        except Exception as e:
            print(f"Error updating status: {e}")
            return False
            
    def generate_batch_cancellation_plan(self, subscriptions: List[Dict], user_email: str) -> Dict:
        """
        Generate a smart cancellation plan for multiple subscriptions
        Prioritizes by savings and ease of cancellation
        """
        if not self.openrouter_client:
            return {"error": "AI service not available"}
            
        prompt = f"""You are a subscription optimization expert. The user wants to cancel some subscriptions to save money.

CURRENT SUBSCRIPTIONS:
{json.dumps(subscriptions, indent=2)}

Create a SMART CANCELLATION PLAN that:
1. Prioritizes subscriptions by potential savings (highest $ first)
2. Groups by cancellation difficulty (easy wins first)
3. Identifies duplicate/overlapping tools
4. Suggests which to cancel vs keep
5. Estimates total monthly savings

Return as JSON:
{{
  "total_current_spend": <float>,
  "recommended_cancellations": [
    {{
      "vendor": "...",
      "amount": <float>,
      "reason": "...",
      "difficulty": "<easy|medium|hard>",
      "priority": <1-10>
    }}
  ],
  "keep_recommendations": [
    {{
      "vendor": "...",
      "amount": <float>,
      "reason": "..."
    }}
  ],
  "duplicate_tools": [
    {{
      "category": "...",
      "tools": ["tool1", "tool2"],
      "recommendation": "..."
    }}
  ],
  "estimated_monthly_savings": <float>,
  "execution_order": ["vendor1", "vendor2", ...],
  "time_estimate": "..."
}}
"""

        try:
            response = self.openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            return {"error": "Failed to parse response"}
            
        except Exception as e:
            return {"error": str(e)}


_cancellation_service = None

def get_cancellation_service():
    """Get singleton instance of CancellationAssistantService"""
    global _cancellation_service
    if _cancellation_service is None:
        _cancellation_service = CancellationAssistantService()
    return _cancellation_service
