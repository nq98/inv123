"""
Subscription Pulse - AI-FIRST Semantic SaaS Spend Analytics Service

This service provides TRUE AI-FIRST subscription discovery where Gemini AI 
is the SOLE decision maker - NO keyword pre-filtering.

Key Features:
- AI-First: Every email goes directly to Gemini for semantic classification
- Real Monthly Spend: Currency normalization + annual-to-monthly prorating
- Clear AI Reasoning: Shows WHY each item is classified as active/stopped
- Accurate Churn Detection: Based on actual billing cadence, not guesses
"""

import os
import json
import re
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from collections import defaultdict
from google.oauth2 import service_account
from google.cloud import bigquery

STAGE1_BATCH_SIZE = 50
STAGE2_BATCH_SIZE = 15
MAX_PARALLEL_WORKERS = 20
STAGE2_PARALLEL_WORKERS = 10

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

import config

# Currency exchange rates to USD (approximate - for monthly spend calculation)
CURRENCY_TO_USD = {
    'USD': 1.0,
    'EUR': 1.10,
    'GBP': 1.27,
    'ILS': 0.27,
    'CAD': 0.74,
    'AUD': 0.65,
    'JPY': 0.0067,
    'CHF': 1.13,
    'INR': 0.012,
    'BRL': 0.20,
    'MXN': 0.058,
}


class SubscriptionPulseService:
    """AI-FIRST Semantic SaaS Spend Analytics - Gemini is the SOLE classifier"""
    
    # Known SaaS categories for duplicate detection
    SAAS_CATEGORIES = {
        'project_management': ['asana', 'monday', 'trello', 'jira', 'clickup', 'notion', 'basecamp', 'wrike', 'linear'],
        'communication': ['slack', 'teams', 'zoom', 'google meet', 'discord', 'webex', 'loom'],
        'crm': ['salesforce', 'hubspot', 'pipedrive', 'zoho crm', 'freshsales', 'close'],
        'design': ['figma', 'sketch', 'adobe', 'canva', 'invision', 'framer'],
        'development': ['github', 'gitlab', 'bitbucket', 'jfrog', 'circleci', 'vercel', 'netlify', 'replit'],
        'cloud': ['aws', 'azure', 'google cloud', 'digitalocean', 'heroku', 'railway', 'render'],
        'hr': ['gusto', 'bamboohr', 'workday', 'deel', 'remote', 'rippling'],
        'marketing': ['mailchimp', 'sendgrid', 'hubspot', 'marketo', 'intercom', 'customer.io'],
        'analytics': ['mixpanel', 'amplitude', 'heap', 'fullstory', 'hotjar', 'posthog'],
        'storage': ['dropbox', 'box', 'google drive', 'onedrive'],
        'security': ['okta', 'auth0', '1password', 'lastpass', 'duo', 'cloudflare'],
        'ai_tools': ['openai', 'anthropic', 'midjourney', 'cursor', 'copilot', 'jasper'],
        'video': ['netflix', 'spotify', 'youtube', 'disney', 'hulu', 'hbo', 'apple music'],
    }
    
    def __init__(self):
        self.config = config.config
        
        print("🚀 Initializing Subscription Pulse AI Service...")
        
        # Initialize OpenRouter client (PRIMARY - no rate limits, best model)
        self.openrouter_client = None
        openrouter_api_key = os.getenv('OPENROUTERA')
        if openrouter_api_key and OPENAI_AVAILABLE:
            try:
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                    default_headers={
                        "HTTP-Referer": "https://replit.com",
                        "X-Title": "Subscription Pulse AI Scanner"
                    }
                )
                print("✅ [Subscription Pulse] OpenRouter client initialized (PRIMARY)")
            except Exception as e:
                print(f"❌ [Subscription Pulse] OpenRouter initialization failed: {e}")
        else:
            print(f"⚠️ [Subscription Pulse] OpenRouter not available (key: {bool(openrouter_api_key)}, openai: {OPENAI_AVAILABLE})")
        
        # Initialize Gemini client as fallback
        self.gemini_client = None
        api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
        if api_key and GENAI_AVAILABLE:
            try:
                self.gemini_client = genai.Client(api_key=api_key)
                print("✅ [Subscription Pulse] Gemini native client initialized (FALLBACK)")
            except Exception as e:
                print(f"❌ [Subscription Pulse] Gemini initialization failed: {e}")
        else:
            print(f"⚠️ [Subscription Pulse] Gemini not available (key: {bool(api_key)}, genai: {GENAI_AVAILABLE})")
        
        # Verify at least one AI client is available
        if not self.openrouter_client and not self.gemini_client:
            print("❌ CRITICAL: No AI client available for Subscription Pulse! Scans will fail.")
            
        # Initialize BigQuery
        self._init_bigquery()
        
    def _init_bigquery(self):
        """Initialize BigQuery client"""
        credentials = None
        sa_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        
        if sa_json:
            try:
                sa_info = json.loads(sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
            except json.JSONDecodeError:
                print("Warning: Failed to parse service account JSON")
        
        if credentials:
            self.bq_client = bigquery.Client(credentials=credentials, project=self.config.GOOGLE_CLOUD_PROJECT_ID)
        else:
            self.bq_client = bigquery.Client(project=self.config.GOOGLE_CLOUD_PROJECT_ID)
            
        # Ensure subscription tables exist
        self._ensure_tables_exist()
        
    def _ensure_tables_exist(self):
        """Create subscription tracking tables if they don't exist"""
        dataset_id = f"{self.config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai"
        
        # Subscription vendors table - with AI reasoning field
        subscription_vendors_schema = [
            bigquery.SchemaField("vendor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("normalized_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("domain", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("category", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("is_subscription", "BOOL", mode="REQUIRED"),
            bigquery.SchemaField("first_seen", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("last_seen", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("payment_frequency", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("average_amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("last_amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("lifetime_spend", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("lifetime_spend_usd", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("monthly_spend_usd", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("payment_count", "INT64", mode="NULLABLE"),
            bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("ai_reasoning", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("confidence", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("claimed_by", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("claimed_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("owner_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        
        # Subscription events table
        subscription_events_schema = [
            bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("amount_usd", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("billing_cadence", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("email_subject", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("email_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("paid_by_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("ai_reasoning", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("confidence", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("owner_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        
        tables = [
            (f"{dataset_id}.subscription_vendors", subscription_vendors_schema),
            (f"{dataset_id}.subscription_events", subscription_events_schema),
        ]
        
        for table_id, schema in tables:
            try:
                self.bq_client.get_table(table_id)
            except Exception:
                table = bigquery.Table(table_id, schema=schema)
                self.bq_client.create_table(table)
                print(f"Created table: {table_id}")

    def analyze_email_semantic(self, email_data):
        """
        AI-FIRST SEMANTIC ANALYSIS - Gemini is the SOLE decision maker.
        
        NO keyword pre-filtering. Every email goes directly to AI for classification.
        This ensures we don't miss subscriptions with unusual wording.
        
        Args:
            email_data: Dict with 'subject', 'body', 'sender', 'date', 'id'
            
        Returns:
            Dict with extracted subscription info or None if not a subscription
        """
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        sender = email_data.get('sender', '')
        email_date = email_data.get('date')
        
        # DIRECT TO AI - No pre-filtering!
        ai_result = self._semantic_classify_with_gemini(subject, body, sender)
        
        if not ai_result:
            return None
        
        # AI confirmed this is a TRUE subscription
        if not ai_result.get('is_subscription', False):
            return None
            
        vendor_name = ai_result.get('vendor_name', '')
        if not vendor_name:
            return None
            
        # Extract domain from sender if AI didn't provide it
        vendor_domain = ai_result.get('domain', '')
        if not vendor_domain:
            sender_info = self._extract_vendor_from_sender(sender)
            if sender_info:
                vendor_domain = sender_info.get('domain', '')
        
        # Detect who paid (for Shadow IT)
        paid_by = self._extract_paid_by_email(body)
        
        # Calculate USD equivalent
        amount = ai_result.get('amount', 0)
        currency = ai_result.get('currency', 'USD')
        amount_usd = self._convert_to_usd(amount, currency)
        
        # Calculate monthly equivalent based on billing cadence
        billing_cadence = ai_result.get('billing_cadence', 'monthly')
        monthly_amount_usd = self._calculate_monthly_amount(amount_usd, billing_cadence)
        
        return {
            'vendor_name': vendor_name,
            'domain': vendor_domain,
            'amount': amount,
            'amount_usd': amount_usd,
            'monthly_amount_usd': monthly_amount_usd,
            'currency': currency,
            'billing_cadence': billing_cadence,
            'is_subscription': True,
            'payment_type': ai_result.get('payment_type', 'subscription'),
            'email_subject': subject,
            'email_date': email_date,
            'email_id': email_data.get('id'),
            'sender': sender,
            'paid_by_email': paid_by,
            'confidence': ai_result.get('confidence', 0.8),
            'ai_reasoning': ai_result.get('reasoning', ''),
            'next_expected_date': ai_result.get('next_expected_date'),
        }
    
    # Alias for backward compatibility
    def analyze_email_fast(self, email_data):
        """Backward compatibility - now uses full semantic analysis"""
        return self.analyze_email_semantic(email_data)
    
    def analyze_email_batch(self, email_batch):
        """
        BULK ANALYSIS - Analyze multiple emails in a single Gemini API call.
        
        This is 6x faster than individual calls and provides better context
        for Gemini to compare patterns across emails.
        
        Args:
            email_batch: List of email_data dicts (max 6-8 recommended)
            
        Returns:
            List of results (same order as input, None for non-subscriptions)
        """
        if not email_batch:
            return []
        
        # Build batch prompt with all emails
        emails_json = []
        for i, email in enumerate(email_batch):
            emails_json.append({
                "index": i,
                "subject": email.get('subject', '')[:200],
                "sender": email.get('sender', ''),
                "body_preview": email.get('body', '')[:1000]
            })
        
        prompt = f"""🧠 BULK SUBSCRIPTION ANALYZER - Analyze {len(email_batch)} emails at once

You are an expert at identifying TRUE RECURRING SUBSCRIPTIONS from emails.
Analyze ALL emails below and return a JSON array with results for each.

## EMAILS TO ANALYZE:
{json.dumps(emails_json, indent=2)}

## CLASSIFICATION RULES:

### ✅ TRUE SUBSCRIPTIONS (is_subscription: true):
- SaaS Products: Notion, Slack, Zoom, Figma, GitHub, Linear, Vercel, Netlify
- Cloud Services: AWS, Google Cloud, Azure, DigitalOcean, Heroku
- AI Tools: OpenAI, Anthropic, Cursor, Midjourney
- Streaming: Netflix, Spotify, Disney+, YouTube Premium
- Business Tools: Salesforce, HubSpot, Intercom, Mailchimp
- Development: JetBrains, CircleCI, Datadog, Sentry

### ❌ NOT SUBSCRIPTIONS (is_subscription: false):
- Marketplace payouts (Fiverr, Upwork - money YOU RECEIVE)
- Payment processor notifications ("Stripe payout", "PayPal deposit")
- One-time purchases (Amazon orders, hardware)
- Welcome emails, newsletters, marketing
- Invoices YOU SENT to customers

## OUTPUT FORMAT (JSON array, no markdown):
[
  {{
    "index": 0,
    "is_subscription": true/false,
    "vendor_name": "The REAL company name",
    "amount": 0.00,
    "currency": "USD",
    "billing_cadence": "monthly|annual|quarterly",
    "payment_type": "subscription|one_time|marketplace|payout|skip",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
  }},
  ...
]

Return results for ALL {len(email_batch)} emails in order by index.
"""

        result_text = None
        
        # PRIMARY: OpenRouter Gemini (faster and more reliable)
        if self.openrouter_client:
            try:
                response = self.openrouter_client.chat.completions.create(
                    model="google/gemini-2.5-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                result_text = response.choices[0].message.content
                print(f"✅ Stage 2 Batch: {len(email_batch)} emails analyzed with OpenRouter")
            except Exception as e:
                print(f"⚠️ OpenRouter Stage 2 error: {e}")
        
        # FALLBACK: Gemini native client
        if not result_text and self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={
                        "temperature": 0.1,
                        "response_mime_type": "application/json"
                    }
                )
                result_text = response.text
                print(f"✅ Stage 2 Batch: {len(email_batch)} emails analyzed with Gemini native fallback")
            except Exception as e:
                print(f"⚠️ Gemini native Stage 2 error: {e}")
                raise
        
        if not result_text:
            raise ValueError("No AI response received for batch analysis")
        
        # Parse batch results with strict validation
        try:
            # Clean markdown if present
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            batch_results = json.loads(result_text.strip())
        except json.JSONDecodeError as e:
            print(f"Batch JSON parse error: {e}, response: {result_text[:500]}")
            raise  # Let caller handle with sequential fallback
        
        # Handle both array and object with "results" key
        if isinstance(batch_results, dict):
            batch_results = batch_results.get('results', batch_results.get('emails', []))
        
        # Debug: Count how many are subscriptions
        sub_count = sum(1 for r in batch_results if r.get('is_subscription'))
        print(f"📊 Stage 2 Batch Result: {sub_count}/{len(batch_results)} emails are subscriptions")
        
        # Map results back to email order
        results = []
        result_map = {r.get('index', i): r for i, r in enumerate(batch_results)}
        
        # Track diagnostics
        skipped_explicit_false = 0
        skipped_payout = 0
        accepted = 0
        
        for i, email in enumerate(email_batch):
            ai_result = result_map.get(i)
            
            # FIX: Only skip if AI EXPLICITLY says it's NOT a subscription
            # Stage 1 already pre-filtered, so we trust those emails more
            if ai_result and ai_result.get('is_subscription') == False:
                skipped_explicit_false += 1
                results.append(None)
                continue
            
            # Also skip if AI identifies it as a payout (not a charge)
            payment_type = ai_result.get('payment_type', '') if ai_result else ''
            if payment_type in ['payout', 'marketplace', 'skip']:
                skipped_payout += 1
                results.append(None)
                continue
            
            # FIX: If no AI result, still process since Stage 1 passed it
            if not ai_result:
                ai_result = {}
            
            accepted += 1
            
            # Process subscription result - use fallbacks if AI didn't provide data
            vendor_name = ai_result.get('vendor_name') or ai_result.get('vendor_hint') or ''
            
            # FIX: Fallback to extract vendor from sender if AI didn't provide it
            if not vendor_name:
                vendor_info = self._extract_vendor_from_sender(email.get('sender', ''))
                if vendor_info:
                    vendor_name = vendor_info.get('name', 'Unknown')
            
            if not vendor_name:
                vendor_name = email.get('vendor_hint', 'Unknown')
            
            vendor_domain = ai_result.get('domain', self._extract_domain(email.get('sender', '')))
            amount = ai_result.get('amount', 0)
            currency = ai_result.get('currency', 'USD')
            amount_usd = self._convert_to_usd(amount, currency)
            billing_cadence = ai_result.get('billing_cadence', 'monthly')
            monthly_amount_usd = self._calculate_monthly_amount(amount_usd, billing_cadence)
            
            email_date = email.get('date')
            if email_date and hasattr(email_date, 'isoformat'):
                email_date = email_date.isoformat()
            
            results.append({
                'vendor_name': vendor_name,
                'domain': vendor_domain,
                'amount': amount,
                'amount_usd': amount_usd,
                'monthly_amount_usd': monthly_amount_usd,
                'currency': currency,
                'billing_cadence': billing_cadence,
                'is_subscription': True,
                'payment_type': ai_result.get('payment_type', 'subscription'),
                'email_subject': email.get('subject', ''),
                'email_date': email_date,
                'email_id': email.get('id'),
                'sender': email.get('sender', ''),
                'confidence': ai_result.get('confidence', 0.8),
                'ai_reasoning': ai_result.get('reasoning', ''),
            })
        
        # Diagnostic logging
        print(f"📊 Stage 2 Batch Stats: {accepted} accepted, {skipped_explicit_false} rejected (is_subscription=false), {skipped_payout} skipped (payout/marketplace)")
        
        return results
    
    def semantic_fast_filter(self, email_batch):
        """
        STAGE 1: AI Semantic Triage using Gemini 2.5 Flash
        
        Fast classification of up to 50 emails in one API call.
        Returns list of dicts with 'is_subscription' boolean and 'reason'.
        
        Args:
            email_batch: List of up to 50 email dicts with subject, sender, body
            
        Returns:
            List of {'index': int, 'is_subscription': bool, 'reason': str, 'vendor_hint': str}
        """
        if not email_batch:
            return []
        
        emails_json = []
        for i, email in enumerate(email_batch):
            emails_json.append({
                "index": i,
                "subject": email.get('subject', '')[:150],
                "sender": email.get('sender', ''),
                "snippet": email.get('body', '')[:400]
            })
        
        prompt = f"""🔍 TURBO SUBSCRIPTION FILTER - Classify {len(email_batch)} emails FAST

Analyze each email and determine if it's a TRUE RECURRING SUBSCRIPTION CHARGE.
Be concise - just return index, boolean, short reason, vendor name.

## EMAILS:
{json.dumps(emails_json)}

## RULES:
✅ TRUE SUBSCRIPTION: SaaS charges (Notion, Slack, Zoom, GitHub, Netflix, Spotify, AWS, OpenAI, etc.) - YOU were CHARGED
❌ NOT SUBSCRIPTION: Payouts/income, one-time purchases, marketing, newsletters

## OUTPUT (JSON array only, no markdown):
[{{"index":0,"is_subscription":true,"reason":"Monthly SaaS","vendor_hint":"Notion"}}]

Return ALL {len(email_batch)} emails."""

        result_text = None
        
        # PRIMARY: OpenRouter Gemini (fast, no rate limits)
        if self.openrouter_client:
            try:
                response = self.openrouter_client.chat.completions.create(
                    model="google/gemini-2.5-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                result_text = response.choices[0].message.content
                print(f"✅ Stage 1: Batch of {len(email_batch)} emails filtered with OpenRouter")
            except Exception as e:
                print(f"⚠️ Stage 1 OpenRouter error: {e}")
        
        # FALLBACK: Gemini native client
        if not result_text and self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={
                        "temperature": 0.1,
                        "response_mime_type": "application/json"
                    }
                )
                result_text = response.text
                print(f"✅ Stage 1: Batch of {len(email_batch)} emails filtered with Gemini native")
            except Exception as e:
                print(f"⚠️ Stage 1 Gemini native error: {e}")
                raise
        
        if not result_text:
            raise Exception("No AI response for fast filter")
        
        # DIAGNOSTIC: Log first part of AI response
        print(f"🔍 Stage 1 AI raw response (first 200 chars): {result_text[:200]}")
        
        try:
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            results = json.loads(result_text.strip())
            
            if isinstance(results, dict):
                results = results.get('results', results.get('emails', []))
            
            return results
            
        except json.JSONDecodeError as e:
            print(f"❌ Fast filter JSON error: {e}")
            print(f"❌ Raw response that failed: {result_text[:500]}")
            raise
    
    def parallel_semantic_filter(self, all_emails, progress_callback=None):
        """
        TURBO Stage 1: Parallel AI Semantic Triage
        
        Processes 10,000 emails in ~30 seconds using:
        - 50 emails per batch
        - 20 parallel workers
        
        Returns: List of emails that passed AI filter
        """
        if not all_emails:
            return []
        
        batches = []
        for i in range(0, len(all_emails), STAGE1_BATCH_SIZE):
            batch = all_emails[i:i + STAGE1_BATCH_SIZE]
            batches.append((i // STAGE1_BATCH_SIZE, batch))
        
        passed_emails = []
        completed = [0]
        lock = threading.Lock()
        
        def process_batch(batch_data):
            batch_idx, batch = batch_data
            try:
                results = self.semantic_fast_filter(batch)
                
                # DIAGNOSTIC: Log what AI returned
                subs_count = sum(1 for r in results if r.get('is_subscription'))
                print(f"📊 Stage 1 Batch {batch_idx}: AI returned {len(results)} results, {subs_count} are subscriptions")
                
                if len(results) == 0:
                    print(f"⚠️ Stage 1 Batch {batch_idx}: AI returned EMPTY array!")
                
                filtered = []
                result_map = {r.get('index', i): r for i, r in enumerate(results)}
                for i, email in enumerate(batch):
                    result = result_map.get(i)
                    if result and result.get('is_subscription'):
                        email_copy = email.copy()
                        email_copy['ai_reason'] = result.get('reason', '')
                        email_copy['vendor_hint'] = result.get('vendor_hint')
                        filtered.append(email_copy)
                
                with lock:
                    completed[0] += 1
                    if progress_callback:
                        progress_callback(completed[0], len(batches), len(filtered))
                
                return filtered
            except Exception as e:
                print(f"❌ Stage 1 Batch {batch_idx} FAILED: {e}")
                import traceback
                traceback.print_exc()
                with lock:
                    completed[0] += 1
                # On error, return empty list to filter out this batch
                # (safer than passing all through as false positives)
                return []
        
        print(f"⚡ Starting parallel semantic filter: {len(all_emails)} emails in {len(batches)} batches with {MAX_PARALLEL_WORKERS} workers")
        
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            futures = [executor.submit(process_batch, batch) for batch in batches]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    with lock:
                        passed_emails.extend(result)
                except Exception as e:
                    print(f"Future error: {e}")
        
        print(f"✅ Parallel Stage 1 complete: {len(passed_emails)} emails passed filter")
        return passed_emails
    
    def parallel_deep_extraction(self, filtered_emails, progress_callback=None):
        """
        TURBO Stage 2: Parallel Deep AI Extraction
        
        Processes filtered emails (~300) in ~10 seconds using:
        - 15 emails per batch
        - 10 parallel workers
        """
        if not filtered_emails:
            return []
        
        batches = []
        for i in range(0, len(filtered_emails), STAGE2_BATCH_SIZE):
            batch = filtered_emails[i:i + STAGE2_BATCH_SIZE]
            batches.append((i // STAGE2_BATCH_SIZE, batch))
        
        all_subscriptions = []
        completed = [0]
        lock = threading.Lock()
        
        def process_batch(batch_data):
            batch_idx, batch = batch_data
            try:
                results = self.analyze_email_batch(batch)
                
                with lock:
                    completed[0] += 1
                    if progress_callback:
                        progress_callback(completed[0], len(batches))
                
                return [r for r in results if r] if results else []
            except Exception as e:
                print(f"⚠️ Extraction batch {batch_idx} error: {e}")
                with lock:
                    completed[0] += 1
                return []
        
        print(f"⚡ Starting parallel deep extraction: {len(filtered_emails)} emails in {len(batches)} batches with {STAGE2_PARALLEL_WORKERS} workers")
        
        with ThreadPoolExecutor(max_workers=STAGE2_PARALLEL_WORKERS) as executor:
            futures = [executor.submit(process_batch, batch) for batch in batches]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    with lock:
                        all_subscriptions.extend(result)
                except Exception as e:
                    print(f"Future error: {e}")
        
        print(f"✅ Parallel Stage 2 complete: {len(all_subscriptions)} subscriptions extracted")
        return all_subscriptions
    
    def _semantic_classify_with_gemini(self, subject, body, sender):
        """
        AI-FIRST SEMANTIC CLASSIFICATION - The Supreme Subscription Judge
        
        Uses Gemini 3 Pro to semantically understand:
        1. Is this a TRUE recurring subscription?
        2. What's the REAL vendor name (not payment processor)?
        3. What's the billing cadence (monthly/annual/quarterly)?
        4. What's the exact amount and currency?
        """
        
        prompt = f"""🧠 THE SUPREME SUBSCRIPTION JUDGE - AI-First Semantic Analysis

You are an expert at identifying TRUE RECURRING SUBSCRIPTIONS from emails.
Your job: Semantically analyze this email and determine if it's a subscription payment.

## EMAIL TO ANALYZE:
**Subject**: {subject[:300]}
**Sender**: {sender}
**Body**: {body[:1500]}

## SEMANTIC CLASSIFICATION RULES:

### ✅ TRUE SUBSCRIPTIONS (is_subscription: true):
These are services YOU PAY FOR on a recurring basis:
- **SaaS Products**: Notion, Slack, Zoom, Figma, GitHub, Linear, Vercel, Netlify
- **Cloud Services**: AWS, Google Cloud, Azure, DigitalOcean, Heroku
- **AI Tools**: OpenAI, Anthropic, Cursor, Midjourney, Jasper
- **Streaming**: Netflix, Spotify, Disney+, YouTube Premium, Apple Music
- **Business Tools**: Salesforce, HubSpot, Intercom, Zendesk, Mailchimp
- **Development**: JetBrains, CircleCI, Datadog, New Relic, Sentry
- **Security**: 1Password, Okta, Auth0, Cloudflare
- **Productivity**: Microsoft 365, Google Workspace, Dropbox, Notion

### ❌ NOT SUBSCRIPTIONS (is_subscription: false) - REJECT THESE:
1. **Marketplace/Platform Sales**: Mrkter, Fiverr, Upwork payouts (money YOU RECEIVE)
2. **Payment Processor Notifications**: "Stripe payout", "PayPal deposit" (not charges)
3. **One-Time Purchases**: Single orders, course purchases, hardware
4. **Bank Alerts**: Credit card statements, bank transfers
5. **Invoices YOU SENT**: Bills to your customers (not bills you pay)
6. **Freelancer/Contractor Payments**: Money you paid for services rendered once

### 🔑 KEY SEMANTIC INSIGHT:
- "Stripe" charging YOU for Stripe Atlas = ✅ SUBSCRIPTION
- "Stripe" sending payout notification = ❌ NOT SUBSCRIPTION
- "Netflix" charging monthly fee = ✅ SUBSCRIPTION  
- "Amazon" order confirmation = ❌ NOT SUBSCRIPTION (one-time)

## OUTPUT FORMAT (JSON only, no markdown):
{{
  "is_subscription": true/false,
  "vendor_name": "The REAL company name (not payment processor)",
  "amount": 0.00,
  "currency": "USD",
  "billing_cadence": "monthly|annual|quarterly|weekly",
  "payment_type": "subscription|one_time|marketplace|payout|skip",
  "domain": "vendor.com (if known)",
  "confidence": 0.0-1.0,
  "reasoning": "Clear explanation of WHY this is/isn't a subscription",
  "next_expected_date": "YYYY-MM-DD or null"
}}

If this is clearly NOT a payment/transaction email, return:
{{"is_subscription": false, "payment_type": "skip", "reasoning": "Not a payment email"}}
"""

        result_text = None
        
        # PRIMARY: OpenRouter Gemini 3 Pro (flagship model - best semantic reasoning)
        if self.openrouter_client:
            try:
                response = self.openrouter_client.chat.completions.create(
                    model="google/gemini-3-pro-preview",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                result_text = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenRouter Gemini 3 Pro error: {e}")
        
        # FALLBACK: Direct Gemini API
        if not result_text and self.gemini_client:
            import time
            time.sleep(0.1)  # Rate limiting
            
            try:
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                result_text = response.text.strip()
            except Exception as e:
                print(f"Gemini Flash error: {e}")
                return None
        
        if not result_text:
            return None
            
        try:
            # Clean up response
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # Log classification for debugging
            vendor = result.get('vendor_name', 'Unknown')
            is_sub = result.get('is_subscription', False)
            reason = result.get('reasoning', '')[:50]
            print(f"[AI Judge] {vendor}: {'✅ SUB' if is_sub else '❌ SKIP'} - {reason}")
            
            return result
            
        except Exception as e:
            print(f"JSON parsing error: {e}")
            return None
    
    def _convert_to_usd(self, amount, currency):
        """Convert amount to USD using exchange rates"""
        rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
        return round(amount * rate, 2)
    
    def _calculate_monthly_amount(self, amount_usd, billing_cadence):
        """Calculate monthly equivalent based on billing cadence"""
        cadence_map = {
            'monthly': 1,
            'annual': 12,
            'yearly': 12,
            'quarterly': 3,
            'weekly': 0.25,
            'biannual': 6,
            'semi-annual': 6,
        }
        divisor = cadence_map.get(billing_cadence.lower(), 1)
        return round(amount_usd / divisor, 2)
    
    def _extract_vendor_from_sender(self, sender):
        """Extract vendor name and domain from sender email"""
        if not sender:
            return None
            
        # Extract email from "Name <email>" format
        email_match = re.search(r'<([^>]+)>', sender)
        email = email_match.group(1) if email_match else sender
        
        # Extract domain
        domain_match = re.search(r'@([^>\s]+)', email)
        if not domain_match:
            return None
            
        domain = domain_match.group(1).lower()
        
        # Skip generic email providers
        generic_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com']
        if domain in generic_domains:
            return None
            
        # Clean domain to get company name
        company_name = domain.split('.')[0].title()
        
        return {
            'name': company_name,
            'domain': domain,
            'confidence': 0.85
        }
        
    def _extract_paid_by_email(self, body):
        """Extract the email of who paid (for Shadow IT detection)"""
        patterns = [
            r'receipt for[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'billed to[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'user[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'account[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def aggregate_subscription_data(self, events):
        """
        Aggregate individual email events into subscription analytics
        
        REAL MONTHLY SPEND: Uses USD normalization and proper prorating
        ACCURATE CHURN: Based on actual billing cadence from AI
        
        Args:
            events: List of analyzed email events
            
        Returns:
            Dict with aggregated subscription data including REAL monthly spend
        """
        vendors = defaultdict(lambda: {
            'payments': [],
            'first_seen': None,
            'last_seen': None,
            'domain': None,
            'is_subscription': False,
            'paid_by_emails': set(),
            'billing_cadence': 'monthly',
            'ai_reasonings': [],
            'confidences': [],
        })
        
        for event in events:
            if not event or not event.get('vendor_name'):
                continue
                
            vendor_key = event['vendor_name'].lower().strip()
            vendor_data = vendors[vendor_key]
            
            # Track payment with USD normalized amount
            if event.get('amount', 0) > 0:
                amount_usd = event.get('amount_usd') or self._convert_to_usd(
                    event['amount'], 
                    event.get('currency', 'USD')
                )
                monthly_usd = event.get('monthly_amount_usd') or self._calculate_monthly_amount(
                    amount_usd,
                    event.get('billing_cadence', 'monthly')
                )
                
                vendor_data['payments'].append({
                    'amount': event['amount'],
                    'amount_usd': amount_usd,
                    'monthly_usd': monthly_usd,
                    'currency': event.get('currency', 'USD'),
                    'date': event.get('email_date'),
                    'email_id': event.get('email_id'),
                    'billing_cadence': event.get('billing_cadence', 'monthly'),
                })
                
            # Update timestamps
            event_date = event.get('email_date')
            if event_date:
                if not vendor_data['first_seen'] or event_date < vendor_data['first_seen']:
                    vendor_data['first_seen'] = event_date
                if not vendor_data['last_seen'] or event_date > vendor_data['last_seen']:
                    vendor_data['last_seen'] = event_date
                    
            # Track metadata
            vendor_data['domain'] = event.get('domain') or vendor_data['domain']
            vendor_data['is_subscription'] = True
            vendor_data['vendor_name'] = event['vendor_name']
            vendor_data['billing_cadence'] = event.get('billing_cadence', 'monthly')
            
            if event.get('ai_reasoning'):
                vendor_data['ai_reasonings'].append(event['ai_reasoning'])
            if event.get('confidence'):
                vendor_data['confidences'].append(event['confidence'])
            
            if event.get('paid_by_email'):
                vendor_data['paid_by_emails'].add(event['paid_by_email'])
                
        # Calculate aggregates with REAL monthly spend
        results = {
            'active_subscriptions': [],
            'stopped_subscriptions': [],
            'all_vendors': [],
            'price_alerts': [],
            'duplicates': [],
            'shadow_it': [],
            'timeline': [],
            'active_count': 0,
            'stopped_count': 0,
            'monthly_spend': 0,  # REAL monthly spend in USD
            'monthly_spend_by_currency': {},  # Breakdown by currency
            'potential_savings': 0,
            'alerts': [],
            'total_lifetime_spend': 0,
        }
        
        now = datetime.utcnow()
        
        for vendor_key, data in vendors.items():
            if not data['payments']:
                continue
                
            # Calculate REAL amounts in USD
            amounts_usd = [p['amount_usd'] for p in data['payments']]
            monthly_amounts = [p['monthly_usd'] for p in data['payments']]
            
            lifetime_spend_usd = sum(amounts_usd)
            avg_monthly_usd = sum(monthly_amounts) / len(monthly_amounts) if monthly_amounts else 0
            last_monthly_usd = monthly_amounts[-1] if monthly_amounts else 0
            
            # Use the most recent billing cadence
            billing_cadence = data['payments'][-1].get('billing_cadence', 'monthly')
            
            # SMART CHURN DETECTION based on actual billing cadence
            churn_thresholds = {
                'weekly': timedelta(days=14),      # 2 weeks
                'monthly': timedelta(days=45),     # 1.5 months
                'quarterly': timedelta(days=120),  # 4 months
                'annual': timedelta(days=400),     # 13 months
                'yearly': timedelta(days=400),
            }
            churn_threshold = churn_thresholds.get(billing_cadence, timedelta(days=45))
            churn_cutoff = now - churn_threshold
            
            # Determine status
            last_seen = data['last_seen']
            status = 'active'
            days_since_payment = 0
            
            if last_seen:
                try:
                    last_seen_dt = last_seen if isinstance(last_seen, datetime) else datetime.fromisoformat(str(last_seen).replace('Z', '+00:00'))
                    if hasattr(last_seen_dt, 'tzinfo') and last_seen_dt.tzinfo:
                        last_seen_dt = last_seen_dt.replace(tzinfo=None)
                    
                    days_since_payment = (now - last_seen_dt).days
                    
                    if last_seen_dt < churn_cutoff:
                        status = 'stopped'
                        results['alerts'].append({
                            'type': 'stopped',
                            'title': f'{data["vendor_name"]} subscription ended',
                            'description': f'No payment in {days_since_payment} days. Last payment: {last_seen_dt.strftime("%b %d, %Y")}'
                        })
                except Exception as e:
                    print(f"Error parsing date for {data['vendor_name']}: {e}")
            
            # Get category
            category = self._get_vendor_category(data['vendor_name'])
            
            # Get best AI reasoning
            ai_reasoning = data['ai_reasonings'][-1] if data['ai_reasonings'] else f"Detected as {billing_cadence} subscription"
            avg_confidence = sum(data['confidences']) / len(data['confidences']) if data['confidences'] else 0.8
            
            vendor_record = {
                'vendor_id': hashlib.md5(vendor_key.encode()).hexdigest()[:12],
                'vendor_name': data['vendor_name'],
                'domain': data['domain'],
                'category': category,
                'status': status,
                'first_seen': data['first_seen'].isoformat() if data['first_seen'] else None,
                'last_seen': data['last_seen'].isoformat() if data['last_seen'] else None,
                'days_since_payment': days_since_payment,
                'frequency': billing_cadence,
                'billing_cadence': billing_cadence,
                'monthly_amount': last_monthly_usd,  # REAL monthly in USD
                'monthly_amount_usd': last_monthly_usd,
                'last_amount': amounts_usd[-1] if amounts_usd else 0,
                'lifetime_spend': lifetime_spend_usd,
                'lifetime_spend_usd': lifetime_spend_usd,
                'payment_count': len(data['payments']),
                'is_subscription': True,
                'payment_history': amounts_usd[-12:],
                'paid_by_emails': list(data['paid_by_emails']),
                'ai_reasoning': ai_reasoning,
                'confidence': avg_confidence,
                'currency': data['payments'][-1].get('currency', 'USD'),
            }
            
            results['all_vendors'].append(vendor_record)
            results['total_lifetime_spend'] += lifetime_spend_usd
            
            if status == 'active':
                results['active_subscriptions'].append(vendor_record)
                results['monthly_spend'] += last_monthly_usd
                
                # Track by currency
                currency = vendor_record['currency']
                if currency not in results['monthly_spend_by_currency']:
                    results['monthly_spend_by_currency'][currency] = 0
                results['monthly_spend_by_currency'][currency] += data['payments'][-1]['amount']
            else:
                results['stopped_subscriptions'].append(vendor_record)
                
            # Detect price changes
            if len(amounts_usd) >= 3:
                recent_avg = sum(amounts_usd[-3:]) / 3
                historical_avg = sum(amounts_usd[:-3]) / len(amounts_usd[:-3]) if len(amounts_usd) > 3 else recent_avg
                if historical_avg > 0:
                    change_percent = ((recent_avg - historical_avg) / historical_avg) * 100
                    if abs(change_percent) >= 10:
                        results['price_alerts'].append({
                            'vendor_name': data['vendor_name'],
                            'old_amount': historical_avg,
                            'new_amount': recent_avg,
                            'change_percent': change_percent,
                            'direction': 'up' if change_percent > 0 else 'down',
                        })
                        results['alerts'].append({
                            'type': 'price',
                            'title': f'{data["vendor_name"]} price {"increased" if change_percent > 0 else "decreased"}',
                            'description': f'Changed by {abs(change_percent):.1f}% from ${historical_avg:.2f} to ${recent_avg:.2f}'
                        })
                        
            # Shadow IT detection
            if data['paid_by_emails']:
                for email in data['paid_by_emails']:
                    if not self._is_corporate_email(email):
                        results['shadow_it'].append({
                            'id': vendor_record['vendor_id'],
                            'vendor_name': data['vendor_name'],
                            'paid_by_email': email,
                            'amount': last_monthly_usd,
                            'monthly_cost': last_monthly_usd,
                        })
                        results['alerts'].append({
                            'type': 'shadow',
                            'title': f'Shadow IT: {data["vendor_name"]}',
                            'description': f'Paid by personal account: {email}'
                        })
                        break
                        
            # Build timeline
            for payment in data['payments']:
                results['timeline'].append({
                    'vendor_name': data['vendor_name'],
                    'event_type': 'Payment',
                    'amount': payment['amount'],
                    'amount_usd': payment['amount_usd'],
                    'currency': payment['currency'],
                    'timestamp': payment['date'].isoformat() if payment['date'] else None,
                    'type': 'payment'
                })
                
        # Detect duplicates
        results['duplicates'] = self._detect_duplicate_tools(results['active_subscriptions'])
        for dup in results['duplicates']:
            results['potential_savings'] += dup.get('potential_savings', 0)
            results['alerts'].append({
                'type': 'duplicate',
                'title': f'Duplicate {dup["category"]} tools',
                'description': f'{len(dup["vendors"])} similar tools. Save ${dup["potential_savings"]:.0f}/year by consolidating.'
            })
            
        # Sort by spend
        results['active_subscriptions'].sort(key=lambda x: x['monthly_amount'], reverse=True)
        results['stopped_subscriptions'].sort(key=lambda x: x['lifetime_spend'], reverse=True)
        results['timeline'].sort(key=lambda x: x['timestamp'] or '', reverse=True)
        
        results['active_count'] = len(results['active_subscriptions'])
        results['stopped_count'] = len(results['stopped_subscriptions'])
        
        # Round monthly spend
        results['monthly_spend'] = round(results['monthly_spend'], 2)
        results['total_lifetime_spend'] = round(results['total_lifetime_spend'], 2)
        
        return results
        
    def _get_vendor_category(self, vendor_name):
        """Get the category of a vendor"""
        vendor_lower = vendor_name.lower()
        for category, vendors in self.SAAS_CATEGORIES.items():
            if any(v in vendor_lower for v in vendors):
                return category
        return 'other'
        
    def _detect_duplicate_tools(self, subscriptions):
        """Detect duplicate tools in the same category"""
        category_vendors = defaultdict(list)
        
        for sub in subscriptions:
            category = sub.get('category', 'other')
            if category != 'other':
                category_vendors[category].append(sub)
                
        duplicates = []
        for category, vendors in category_vendors.items():
            if len(vendors) > 1:
                total_cost = sum(v['monthly_amount'] for v in vendors)
                min_cost = min(v['monthly_amount'] for v in vendors)
                savings = (total_cost - min_cost) * 12  # Annual savings
                
                duplicates.append({
                    'category': category.replace('_', ' ').title(),
                    'vendors': [{'name': v['vendor_name'], 'monthly_cost': v['monthly_amount']} for v in vendors],
                    'potential_savings': savings
                })
                
        return duplicates
        
    def _is_corporate_email(self, email):
        """Check if email appears to be a corporate email"""
        if not email:
            return True
            
        personal_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
                          'icloud.com', 'aol.com', 'protonmail.com', 'mail.com']
        domain = email.split('@')[-1].lower()
        return domain not in personal_domains
        
    def store_subscription_results(self, client_email, results):
        """Store subscription analytics results in BigQuery with AI reasoning"""
        dataset_id = f"{self.config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai"
        
        for vendor in results.get('all_vendors', []):
            vendor_id = vendor['vendor_id']
            
            query = f"""
            MERGE `{dataset_id}.subscription_vendors` T
            USING (SELECT @vendor_id as vendor_id) S
            ON T.vendor_id = S.vendor_id
            WHEN MATCHED THEN
                UPDATE SET
                    vendor_name = @vendor_name,
                    domain = @domain,
                    category = @category,
                    is_subscription = @is_subscription,
                    first_seen = @first_seen,
                    last_seen = @last_seen,
                    status = @status,
                    payment_frequency = @frequency,
                    average_amount = @avg_amount,
                    last_amount = @last_amount,
                    lifetime_spend = @lifetime_spend,
                    lifetime_spend_usd = @lifetime_spend_usd,
                    monthly_spend_usd = @monthly_spend_usd,
                    payment_count = @payment_count,
                    currency = @currency,
                    ai_reasoning = @ai_reasoning,
                    confidence = @confidence,
                    owner_email = @owner_email,
                    updated_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
                INSERT (vendor_id, vendor_name, domain, category, is_subscription,
                        first_seen, last_seen, status, payment_frequency,
                        average_amount, last_amount, lifetime_spend, lifetime_spend_usd,
                        monthly_spend_usd, payment_count, currency, ai_reasoning,
                        confidence, owner_email, created_at, updated_at)
                VALUES (@vendor_id, @vendor_name, @domain, @category, @is_subscription,
                        @first_seen, @last_seen, @status, @frequency,
                        @avg_amount, @last_amount, @lifetime_spend, @lifetime_spend_usd,
                        @monthly_spend_usd, @payment_count, @currency, @ai_reasoning,
                        @confidence, @owner_email, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                    bigquery.ScalarQueryParameter("vendor_name", "STRING", vendor['vendor_name']),
                    bigquery.ScalarQueryParameter("domain", "STRING", vendor.get('domain')),
                    bigquery.ScalarQueryParameter("category", "STRING", vendor.get('category')),
                    bigquery.ScalarQueryParameter("is_subscription", "BOOL", True),
                    bigquery.ScalarQueryParameter("first_seen", "TIMESTAMP", vendor.get('first_seen')),
                    bigquery.ScalarQueryParameter("last_seen", "TIMESTAMP", vendor.get('last_seen')),
                    bigquery.ScalarQueryParameter("status", "STRING", vendor.get('status', 'active')),
                    bigquery.ScalarQueryParameter("frequency", "STRING", vendor.get('frequency', 'monthly')),
                    bigquery.ScalarQueryParameter("avg_amount", "FLOAT64", vendor.get('monthly_amount', 0)),
                    bigquery.ScalarQueryParameter("last_amount", "FLOAT64", vendor.get('last_amount', 0)),
                    bigquery.ScalarQueryParameter("lifetime_spend", "FLOAT64", vendor.get('lifetime_spend', 0)),
                    bigquery.ScalarQueryParameter("lifetime_spend_usd", "FLOAT64", vendor.get('lifetime_spend_usd', 0)),
                    bigquery.ScalarQueryParameter("monthly_spend_usd", "FLOAT64", vendor.get('monthly_amount_usd', 0)),
                    bigquery.ScalarQueryParameter("payment_count", "INT64", vendor.get('payment_count', 0)),
                    bigquery.ScalarQueryParameter("currency", "STRING", vendor.get('currency', 'USD')),
                    bigquery.ScalarQueryParameter("ai_reasoning", "STRING", vendor.get('ai_reasoning', '')),
                    bigquery.ScalarQueryParameter("confidence", "FLOAT64", vendor.get('confidence', 0.8)),
                    bigquery.ScalarQueryParameter("owner_email", "STRING", client_email),
                ]
            )
            
            try:
                self.bq_client.query(query, job_config=job_config).result()
            except Exception as e:
                print(f"Error storing subscription vendor: {e}")
                
        return True
        
    def get_cached_results(self, client_email):
        """Get cached subscription results from BigQuery with AI reasoning"""
        dataset_id = f"{self.config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai"
        
        query = f"""
        SELECT *
        FROM `{dataset_id}.subscription_vendors`
        WHERE updated_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
          AND (owner_email = @client_email OR owner_email IS NULL)
        ORDER BY lifetime_spend DESC
        """
        
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("client_email", "STRING", client_email),
                ]
            )
            results = list(self.bq_client.query(query, job_config=job_config).result())
            if not results:
                return None
                
            active = []
            stopped = []
            monthly_spend = 0
            total_lifetime = 0
            
            for row in results:
                vendor = {
                    'vendor_id': row['vendor_id'],
                    'vendor_name': row['vendor_name'],
                    'domain': row.get('domain'),
                    'category': row.get('category'),
                    'status': row.get('status', 'active'),
                    'first_seen': row['first_seen'].isoformat() if row.get('first_seen') else None,
                    'last_seen': row['last_seen'].isoformat() if row.get('last_seen') else None,
                    'frequency': row.get('payment_frequency', 'monthly'),
                    'billing_cadence': row.get('payment_frequency', 'monthly'),
                    'monthly_amount': row.get('monthly_spend_usd') or row.get('average_amount', 0),
                    'monthly_amount_usd': row.get('monthly_spend_usd') or row.get('average_amount', 0),
                    'last_amount': row.get('last_amount', 0),
                    'lifetime_spend': row.get('lifetime_spend_usd') or row.get('lifetime_spend', 0),
                    'lifetime_spend_usd': row.get('lifetime_spend_usd') or row.get('lifetime_spend', 0),
                    'payment_count': row.get('payment_count', 0),
                    'is_subscription': row.get('is_subscription', False),
                    'ai_reasoning': row.get('ai_reasoning', ''),
                    'confidence': row.get('confidence', 0.8),
                    'currency': row.get('currency', 'USD'),
                }
                
                total_lifetime += vendor['lifetime_spend']
                
                if vendor['status'] == 'active' and vendor['is_subscription']:
                    active.append(vendor)
                    monthly_spend += vendor['monthly_amount']
                elif vendor['status'] == 'stopped':
                    stopped.append(vendor)
                    
            return {
                'has_data': True,
                'results': {
                    'active_subscriptions': active,
                    'stopped_subscriptions': stopped,
                    'active_count': len(active),
                    'stopped_count': len(stopped),
                    'monthly_spend': round(monthly_spend, 2),
                    'total_lifetime_spend': round(total_lifetime, 2),
                    'potential_savings': 0,
                    'alerts': [],
                    'duplicates': self._detect_duplicate_tools(active),
                    'price_alerts': [],
                    'shadow_it': [],
                    'timeline': []
                }
            }
            
        except Exception as e:
            print(f"Error getting cached results: {e}")
            return None
