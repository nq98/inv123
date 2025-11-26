"""
Subscription Pulse - Fast Lane SaaS Spend Analytics Service

This service provides rapid subscription discovery by analyzing email text
(subjects and bodies) instead of processing PDF attachments.

Key Features:
- Fast Lane scanning (text-only, no Document AI)
- Gemini Flash for quick classification
- Subscription vs. one-time purchase detection
- Price change detection
- Duplicate tool discovery
- Shadow IT identification
"""

import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from google.oauth2 import service_account
from google.cloud import bigquery

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

class SubscriptionPulseService:
    """Fast Lane SaaS Spend Analytics"""
    
    # Known subscription domains/patterns
    SUBSCRIPTION_KEYWORDS = [
        'subscription', 'monthly', 'annual', 'yearly', 'recurring',
        'renewal', 'auto-renew', 'billing cycle', 'plan', 'license',
        'seats', 'per user', 'per month', 'per year', '/mo', '/yr'
    ]
    
    TRANSACTION_KEYWORDS = [
        'charged', 'paid', 'payment', 'receipt', 'invoice', 'bill',
        'transaction', 'card ending', 'successful payment', 'amount due'
    ]
    
    # High-trust sender patterns (billing/finance departments)
    TRUSTED_SENDERS = [
        'billing@', 'finance@', 'payments@', 'invoices@', 'accounts@',
        'noreply@', 'no-reply@', 'receipts@', 'support@'
    ]
    
    # Known SaaS categories for duplicate detection
    SAAS_CATEGORIES = {
        'project_management': ['asana', 'monday', 'trello', 'jira', 'clickup', 'notion', 'basecamp', 'wrike'],
        'communication': ['slack', 'teams', 'zoom', 'google meet', 'discord', 'webex'],
        'crm': ['salesforce', 'hubspot', 'pipedrive', 'zoho crm', 'freshsales'],
        'design': ['figma', 'sketch', 'adobe', 'canva', 'invision'],
        'development': ['github', 'gitlab', 'bitbucket', 'jfrog', 'circleci'],
        'cloud': ['aws', 'azure', 'google cloud', 'digitalocean', 'heroku', 'vercel'],
        'hr': ['gusto', 'bamboohr', 'workday', 'deel', 'remote'],
        'marketing': ['mailchimp', 'sendgrid', 'hubspot', 'marketo', 'intercom'],
        'analytics': ['mixpanel', 'amplitude', 'heap', 'fullstory', 'hotjar'],
        'storage': ['dropbox', 'box', 'google drive', 'onedrive'],
        'security': ['okta', 'auth0', '1password', 'lastpass', 'duo']
    }
    
    def __init__(self):
        self.config = config.config
        
        # Initialize OpenRouter client (PRIMARY - no rate limits)
        self.openrouter_client = None
        openrouter_api_key = os.getenv('OPENROUTERA')
        if openrouter_api_key and OPENAI_AVAILABLE:
            try:
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_api_key,
                    default_headers={
                        "HTTP-Referer": "https://replit.com",
                        "X-Title": "Subscription Pulse Scanner"
                    }
                )
                print("✅ OpenRouter initialized for Subscription Pulse (no rate limits)")
            except Exception as e:
                print(f"⚠️ OpenRouter initialization failed: {e}")
        
        # Initialize Gemini client as fallback
        api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
        if api_key and GENAI_AVAILABLE:
            self.gemini_client = genai.Client(api_key=api_key)
        else:
            self.gemini_client = None
            
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
        
        # Subscription vendors table
        subscription_vendors_schema = [
            bigquery.SchemaField("vendor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("normalized_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("domain", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("category", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("is_subscription", "BOOL", mode="REQUIRED"),
            bigquery.SchemaField("first_seen", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("last_seen", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("status", "STRING", mode="NULLABLE"),  # active, stopped, zombie
            bigquery.SchemaField("payment_frequency", "STRING", mode="NULLABLE"),  # monthly, annual
            bigquery.SchemaField("average_amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("last_amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("lifetime_spend", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("payment_count", "INT64", mode="NULLABLE"),
            bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("claimed_by", "STRING", mode="NULLABLE"),  # corporate, team name, etc
            bigquery.SchemaField("claimed_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        
        # Subscription events table
        subscription_events_schema = [
            bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor_name", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),  # payment, renewal, cancellation, price_change
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("email_subject", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("email_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("paid_by_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("confidence", "FLOAT64", mode="NULLABLE"),
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
                
    def analyze_email_fast(self, email_data):
        """
        Fast Lane analysis with SEMANTIC AI FILTERING for subscription detection.
        
        CRITICAL: Every email goes through Gemini for true subscription classification.
        This filters out marketplace transactions (Mrkter), one-time purchases, and payouts.
        
        Args:
            email_data: Dict with 'subject', 'body', 'sender', 'date', 'id'
            
        Returns:
            Dict with extracted subscription info or None if not a TRUE subscription
        """
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        sender = email_data.get('sender', '')
        email_date = email_data.get('date')
        
        # Quick pre-filter: Check if this looks like a transaction email
        if not self._is_transaction_email(subject, body, sender):
            return None
        
        # SEMANTIC AI FILTER: Use Gemini for ALL emails to classify
        # This is the key to filtering out Mrkter, Stripe payouts, etc.
        if self.gemini_client:
            ai_result = self._classify_with_gemini_flash(subject, body, sender)
            
            # If AI says skip or not a subscription, return None
            if not ai_result:
                return None
            
            # AI confirmed this is a TRUE subscription - use AI-extracted data
            vendor_name = ai_result.get('vendor_name', '')
            vendor_domain = ai_result.get('domain', '')
            
            # If AI didn't extract domain, try to get it from sender
            if not vendor_domain:
                sender_info = self._extract_vendor_from_sender(sender)
                if sender_info:
                    vendor_domain = sender_info.get('domain', '')
            
            # Detect paid by (for Shadow IT)
            paid_by = self._extract_paid_by_email(body)
            
            return {
                'vendor_name': vendor_name,
                'domain': vendor_domain,
                'amount': ai_result.get('amount', 0),
                'currency': ai_result.get('currency', 'USD'),
                'is_subscription': True,  # AI already confirmed this
                'payment_type': ai_result.get('payment_type', 'subscription'),
                'email_subject': subject,
                'email_date': email_date,
                'email_id': email_data.get('id'),
                'sender': sender,
                'paid_by_email': paid_by,
                'confidence': ai_result.get('confidence', 0.8),
                'classification_reason': ai_result.get('reason', '')
            }
        
        # FALLBACK (no Gemini): Strict keyword-based detection
        vendor_info = self._extract_vendor_from_sender(sender)
        if not vendor_info:
            return None
            
        amount_info = self._extract_amount(subject + ' ' + body)
        is_subscription = self._is_subscription_email(subject, body)
        
        # Without AI, only accept if keywords strongly suggest subscription
        if not is_subscription:
            return None
        
        paid_by = self._extract_paid_by_email(body)
        
        return {
            'vendor_name': vendor_info.get('name'),
            'domain': vendor_info.get('domain'),
            'amount': amount_info.get('amount', 0) if amount_info else 0,
            'currency': amount_info.get('currency', 'USD') if amount_info else 'USD',
            'is_subscription': is_subscription,
            'payment_type': 'subscription',
            'email_subject': subject,
            'email_date': email_date,
            'email_id': email_data.get('id'),
            'sender': sender,
            'paid_by_email': paid_by,
            'confidence': 0.6
        }
        
    def _is_transaction_email(self, subject, body, sender):
        """Quick check if email looks like a transaction/receipt"""
        text = (subject + ' ' + body + ' ' + sender).lower()
        
        # Check for currency symbols near numbers
        has_currency = bool(re.search(r'[$€£¥₪]\s*[\d,]+\.?\d*|\d+\.?\d*\s*[$€£¥₪]', text))
        
        # Check for transaction keywords
        has_keywords = any(kw in text for kw in self.TRANSACTION_KEYWORDS)
        
        # Check for trusted sender patterns
        sender_lower = sender.lower()
        is_trusted_sender = any(pattern in sender_lower for pattern in self.TRUSTED_SENDERS)
        
        return has_currency or (has_keywords and is_trusted_sender)
        
    def _is_subscription_email(self, subject, body):
        """Check if email indicates a subscription/recurring payment"""
        text = (subject + ' ' + body).lower()
        return any(kw in text for kw in self.SUBSCRIPTION_KEYWORDS)
        
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
        
    def _extract_amount(self, text):
        """Extract monetary amount from text"""
        # Common currency patterns
        patterns = [
            r'\$\s*([\d,]+\.?\d*)',  # $123.45
            r'([\d,]+\.?\d*)\s*USD',  # 123.45 USD
            r'€\s*([\d,]+\.?\d*)',    # €123.45
            r'£\s*([\d,]+\.?\d*)',    # £123.45
            r'₪\s*([\d,]+\.?\d*)',    # ₪123.45
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    amount = float(matches[0].replace(',', ''))
                    # Determine currency
                    if '$' in text or 'USD' in text.upper():
                        currency = 'USD'
                    elif '€' in text or 'EUR' in text.upper():
                        currency = 'EUR'
                    elif '£' in text or 'GBP' in text.upper():
                        currency = 'GBP'
                    elif '₪' in text or 'ILS' in text.upper():
                        currency = 'ILS'
                    else:
                        currency = 'USD'
                    return {'amount': amount, 'currency': currency}
                except ValueError:
                    continue
        return None
        
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
        
    def _classify_with_gemini_flash(self, subject, body, sender):
        """Use OpenRouter (PRIMARY, no rate limits) or Gemini Flash for subscription classification"""
        
        prompt = f"""You are a SaaS Subscription Detector. Your job is to distinguish TRUE RECURRING SUBSCRIPTIONS from one-time purchases and marketplace transactions.

## Email to Analyze:
Subject: {subject[:200]}
Sender: {sender}
Body Preview: {body[:500]}

## CRITICAL CLASSIFICATION RULES:

### TRUE SUBSCRIPTIONS (is_subscription: true) - These are SaaS/software subscriptions:
- Software services: GitHub, Notion, Slack, Zoom, Figma, Adobe, Microsoft 365, Google Workspace
- Streaming services: Netflix, Spotify, Disney+, YouTube Premium
- Cloud services: AWS, Azure, GCP, Heroku, Vercel, DigitalOcean
- Business tools: HubSpot, Salesforce, Mailchimp, Intercom, Zendesk
- Development tools: JetBrains, CircleCI, Datadog, New Relic
- Key indicators: "monthly plan", "annual subscription", "renewal", "your subscription", "billing cycle"

### NOT SUBSCRIPTIONS (is_subscription: false) - REJECT THESE:
1. **Marketplace/Platform Transactions**: Payments THROUGH a platform (Mrkter, Fiverr, Upwork, Amazon Marketplace, eBay sales)
2. **Payment Processor Notifications**: Stripe payout, PayPal transfer, Square deposit notifications
3. **One-time Purchases**: Single orders, course purchases, one-time consulting fees
4. **Bank/Card Notifications**: Credit card alerts, bank transfers
5. **Invoices to Customers**: Bills you SENT to others (not SaaS you're paying for)
6. **Freelancer Payments**: Contractor payments, consultant fees

### KEY INSIGHT:
- "Stripe" charging YOU for their service = SUBSCRIPTION
- "Stripe" notifying about a payout/deposit = NOT SUBSCRIPTION (skip it)
- "Mrkter" sending receipt for platform transaction = NOT SUBSCRIPTION
- "Netflix" charging for monthly service = SUBSCRIPTION

## Output JSON (only valid JSON, nothing else):
{{
  "vendor_name": "Company providing the subscription service",
  "amount": 0.00,
  "currency": "USD",
  "is_subscription": true/false,
  "payment_type": "subscription|one_time|marketplace|payout|skip",
  "confidence": 0.0-1.0,
  "reason": "Brief explanation of classification"
}}

If this is clearly NOT a payment email at all, return: {{"skip": true, "reason": "not a payment email"}}"""

        result_text = None
        
        # TRY OPENROUTER FIRST (no rate limits!)
        if self.openrouter_client:
            try:
                response = self.openrouter_client.chat.completions.create(
                    model="google/gemini-3-pro-preview",  # Gemini 3 Pro via OpenRouter (no rate limits)
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                result_text = response.choices[0].message.content.strip()
                print(f"✅ OpenRouter Gemini 3 Pro classified email")
            except Exception as e:
                print(f"OpenRouter error (falling back to Gemini): {e}")
        
        # FALLBACK TO DIRECT GEMINI API (with rate limiting)
        if not result_text and self.gemini_client:
            import time
            time.sleep(0.15)  # Rate limiting for direct API
            
            try:
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',  # Updated fallback model
                    contents=prompt
                )
                result_text = response.text.strip()
            except Exception as e:
                print(f"Gemini Flash classification error: {e}")
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
            
            # Skip non-subscriptions based on semantic analysis
            if result.get('skip'):
                return None
            
            # Only return TRUE subscriptions
            payment_type = result.get('payment_type', 'unknown')
            is_subscription = result.get('is_subscription', False)
            
            if payment_type in ['marketplace', 'payout', 'skip', 'one_time']:
                print(f"[Subscription Filter] REJECTED: {result.get('vendor_name', 'Unknown')} - {result.get('reason', payment_type)}")
                return None
            
            if not is_subscription:
                print(f"[Subscription Filter] REJECTED (not subscription): {result.get('vendor_name', 'Unknown')}")
                return None
                
            return result
            
        except Exception as e:
            print(f"JSON parsing error: {e}")
            return None
            
    def aggregate_subscription_data(self, events):
        """
        Aggregate individual email events into subscription analytics
        
        Args:
            events: List of analyzed email events
            
        Returns:
            Dict with aggregated subscription data
        """
        vendors = defaultdict(lambda: {
            'payments': [],
            'first_seen': None,
            'last_seen': None,
            'domain': None,
            'is_subscription': False,
            'paid_by_emails': set()
        })
        
        for event in events:
            if not event or not event.get('vendor_name'):
                continue
                
            vendor_key = event['vendor_name'].lower()
            vendor_data = vendors[vendor_key]
            
            # Track payment
            if event.get('amount', 0) > 0:
                vendor_data['payments'].append({
                    'amount': event['amount'],
                    'currency': event.get('currency', 'USD'),
                    'date': event.get('email_date'),
                    'email_id': event.get('email_id')
                })
                
            # Update timestamps
            event_date = event.get('email_date')
            if event_date:
                if not vendor_data['first_seen'] or event_date < vendor_data['first_seen']:
                    vendor_data['first_seen'] = event_date
                if not vendor_data['last_seen'] or event_date > vendor_data['last_seen']:
                    vendor_data['last_seen'] = event_date
                    
            # Track other metadata
            vendor_data['domain'] = event.get('domain') or vendor_data['domain']
            vendor_data['is_subscription'] = vendor_data['is_subscription'] or event.get('is_subscription', False)
            vendor_data['vendor_name'] = event['vendor_name']
            
            if event.get('paid_by_email'):
                vendor_data['paid_by_emails'].add(event['paid_by_email'])
                
        # Calculate aggregates
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
            'monthly_spend': 0,
            'potential_savings': 0,
            'alerts': []
        }
        
        now = datetime.utcnow()
        
        for vendor_key, data in vendors.items():
            if not data['payments']:
                continue
                
            # Calculate stats
            amounts = [p['amount'] for p in data['payments']]
            lifetime_spend = sum(amounts)
            avg_amount = lifetime_spend / len(amounts) if amounts else 0
            last_amount = amounts[-1] if amounts else 0
            
            # Determine frequency and calculate average days between payments
            avg_days_between_payments = 30  # Default to monthly
            if len(data['payments']) >= 2:
                dates = sorted([p['date'] for p in data['payments'] if p['date']])
                if len(dates) >= 2:
                    avg_days_between_payments = (dates[-1] - dates[0]).days / (len(dates) - 1) if len(dates) > 1 else 30
                    frequency = 'annual' if avg_days_between_payments > 180 else 'monthly'
                else:
                    frequency = 'monthly'
            else:
                frequency = 'one-time' if not data['is_subscription'] else 'monthly'
                
            # SMART CHURN DETECTION: Based on subscription frequency
            # - Monthly subscriptions: If no payment in last 45 days, likely stopped
            # - Annual subscriptions: If no payment in last 13 months, likely stopped
            # - One-time: Never "stopped" (they aren't recurring)
            if frequency == 'monthly':
                churn_threshold = timedelta(days=45)  # 1.5x monthly cycle
            elif frequency == 'annual':
                churn_threshold = timedelta(days=400)  # 13 months
            else:
                churn_threshold = timedelta(days=9999)  # One-time never churns
                
            churn_cutoff = now - churn_threshold
            
            # Determine status based on last payment date
            last_seen = data['last_seen']
            status = 'active'  # Default
            
            if last_seen:
                try:
                    last_seen_dt = last_seen if isinstance(last_seen, datetime) else datetime.fromisoformat(str(last_seen).replace('Z', '+00:00'))
                    if hasattr(last_seen_dt, 'tzinfo') and last_seen_dt.tzinfo:
                        last_seen_dt = last_seen_dt.replace(tzinfo=None)
                    
                    # Check if subscription has churned
                    if last_seen_dt < churn_cutoff:
                        status = 'stopped'
                        # Add churn alert
                        days_since_payment = (now - last_seen_dt).days
                        results['alerts'].append({
                            'type': 'zombie',
                            'title': f'{data["vendor_name"]} may have stopped',
                            'description': f'No payment in {days_since_payment} days (last: {last_seen_dt.strftime("%b %d, %Y")})'
                        })
                except Exception as e:
                    print(f"Error parsing last_seen for {data['vendor_name']}: {e}")
                
            # Get category
            category = self._get_vendor_category(data['vendor_name'])
            
            vendor_record = {
                'vendor_id': hashlib.md5(vendor_key.encode()).hexdigest()[:12],
                'vendor_name': data['vendor_name'],
                'domain': data['domain'],
                'category': category,
                'status': status,
                'first_seen': data['first_seen'].isoformat() if data['first_seen'] else None,
                'last_seen': data['last_seen'].isoformat() if data['last_seen'] else None,
                'frequency': frequency,
                'monthly_amount': avg_amount if frequency == 'monthly' else avg_amount / 12,
                'last_amount': last_amount,
                'lifetime_spend': lifetime_spend,
                'payment_count': len(data['payments']),
                'is_subscription': data['is_subscription'],
                'payment_history': amounts[-12:],  # Last 12 payments for sparkline
                'paid_by_emails': list(data['paid_by_emails'])
            }
            
            results['all_vendors'].append(vendor_record)
            
            if status == 'active' and data['is_subscription']:
                results['active_subscriptions'].append(vendor_record)
                results['monthly_spend'] += vendor_record['monthly_amount']
            elif status == 'stopped':
                results['stopped_subscriptions'].append(vendor_record)
                
            # Detect price changes
            if len(amounts) >= 3:
                recent_avg = sum(amounts[-3:]) / 3
                historical_avg = sum(amounts[:-3]) / len(amounts[:-3]) if len(amounts) > 3 else recent_avg
                if historical_avg > 0:
                    change_percent = ((recent_avg - historical_avg) / historical_avg) * 100
                    if abs(change_percent) >= 10:  # 10% or more change
                        results['price_alerts'].append({
                            'vendor_name': data['vendor_name'],
                            'old_amount': historical_avg,
                            'new_amount': recent_avg,
                            'change_percent': change_percent
                        })
                        results['alerts'].append({
                            'type': 'price',
                            'title': f'{data["vendor_name"]} price {"increased" if change_percent > 0 else "decreased"}',
                            'description': f'Changed by {abs(change_percent):.1f}% from ${historical_avg:.2f} to ${recent_avg:.2f}'
                        })
                        
            # Shadow IT detection (personal email payments)
            if data['paid_by_emails']:
                for email in data['paid_by_emails']:
                    if not self._is_corporate_email(email):
                        results['shadow_it'].append({
                            'id': vendor_record['vendor_id'],
                            'vendor_name': data['vendor_name'],
                            'paid_by_email': email,
                            'amount': last_amount
                        })
                        results['alerts'].append({
                            'type': 'shadow',
                            'title': f'Shadow IT detected: {data["vendor_name"]}',
                            'description': f'Paid by personal account: {email}'
                        })
                        break
                        
            # Build timeline
            for payment in data['payments']:
                results['timeline'].append({
                    'vendor_name': data['vendor_name'],
                    'event_type': 'Payment',
                    'amount': payment['amount'],
                    'timestamp': payment['date'].isoformat() if payment['date'] else None,
                    'type': 'payment'
                })
                
        # Detect duplicates
        results['duplicates'] = self._detect_duplicate_tools(results['active_subscriptions'])
        for dup in results['duplicates']:
            results['potential_savings'] += dup.get('potential_savings', 0)
            results['alerts'].append({
                'type': 'duplicate',
                'title': f'Duplicate {dup["category"]} tools detected',
                'description': f'{len(dup["vendors"])} similar tools. Save ${dup["potential_savings"]:.0f}/year by consolidating.'
            })
            
        # Sort and finalize
        results['active_subscriptions'].sort(key=lambda x: x['monthly_amount'], reverse=True)
        results['stopped_subscriptions'].sort(key=lambda x: x['lifetime_spend'], reverse=True)
        results['timeline'].sort(key=lambda x: x['timestamp'] or '', reverse=True)
        results['active_count'] = len(results['active_subscriptions'])
        results['stopped_count'] = len(results['stopped_subscriptions'])
        
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
        """Store subscription analytics results in BigQuery"""
        dataset_id = f"{self.config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai"
        
        # Store vendor summaries
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
                    payment_count = @payment_count,
                    updated_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
                INSERT (vendor_id, vendor_name, domain, category, is_subscription,
                        first_seen, last_seen, status, payment_frequency,
                        average_amount, last_amount, lifetime_spend, payment_count,
                        created_at, updated_at)
                VALUES (@vendor_id, @vendor_name, @domain, @category, @is_subscription,
                        @first_seen, @last_seen, @status, @frequency,
                        @avg_amount, @last_amount, @lifetime_spend, @payment_count,
                        CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("vendor_id", "STRING", vendor_id),
                    bigquery.ScalarQueryParameter("vendor_name", "STRING", vendor['vendor_name']),
                    bigquery.ScalarQueryParameter("domain", "STRING", vendor.get('domain')),
                    bigquery.ScalarQueryParameter("category", "STRING", vendor.get('category')),
                    bigquery.ScalarQueryParameter("is_subscription", "BOOL", vendor.get('is_subscription', False)),
                    bigquery.ScalarQueryParameter("first_seen", "TIMESTAMP", vendor.get('first_seen')),
                    bigquery.ScalarQueryParameter("last_seen", "TIMESTAMP", vendor.get('last_seen')),
                    bigquery.ScalarQueryParameter("status", "STRING", vendor.get('status', 'active')),
                    bigquery.ScalarQueryParameter("frequency", "STRING", vendor.get('frequency', 'monthly')),
                    bigquery.ScalarQueryParameter("avg_amount", "FLOAT64", vendor.get('monthly_amount', 0)),
                    bigquery.ScalarQueryParameter("last_amount", "FLOAT64", vendor.get('last_amount', 0)),
                    bigquery.ScalarQueryParameter("lifetime_spend", "FLOAT64", vendor.get('lifetime_spend', 0)),
                    bigquery.ScalarQueryParameter("payment_count", "INT64", vendor.get('payment_count', 0)),
                ]
            )
            
            try:
                self.bq_client.query(query, job_config=job_config).result()
            except Exception as e:
                print(f"Error storing subscription vendor: {e}")
                
        return True
        
    def get_cached_results(self, client_email):
        """Get cached subscription results from BigQuery"""
        dataset_id = f"{self.config.GOOGLE_CLOUD_PROJECT_ID}.vendors_ai"
        
        query = f"""
        SELECT *
        FROM `{dataset_id}.subscription_vendors`
        WHERE updated_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        ORDER BY lifetime_spend DESC
        """
        
        try:
            results = list(self.bq_client.query(query).result())
            if not results:
                return None
                
            # Reconstruct results format
            active = []
            stopped = []
            monthly_spend = 0
            
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
                    'monthly_amount': row.get('average_amount', 0),
                    'last_amount': row.get('last_amount', 0),
                    'lifetime_spend': row.get('lifetime_spend', 0),
                    'payment_count': row.get('payment_count', 0),
                    'is_subscription': row.get('is_subscription', False),
                }
                
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
                    'monthly_spend': monthly_spend,
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
