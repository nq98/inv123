#!/usr/bin/env python3
"""
Standalone subscription scan worker that runs independently of the web server.
This script is spawned as a detached subprocess so it survives gunicorn worker recycling.

Usage: python subscription_scan_worker.py <job_id> <creds_file> <days> <user_email>
"""

import sys
import os
import json
import time
import fcntl
import traceback
from datetime import datetime, timedelta

# CRITICAL: Dynamically compute BASE_DIR instead of hard-coding
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

JOBS_DIR = "/tmp/subscription_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

def log(msg):
    """Print with timestamp for debugging"""
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)

def read_job(job_id):
    """Read job from file"""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return data
    except:
        return None

def write_job(job_id, data):
    """Write job to file with proper sync"""
    path = os.path.join(JOBS_DIR, f"{job_id}.json")
    try:
        with open(path, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        log(f"Error writing job file: {e}")

def update_job(job_id, **kwargs):
    """Update job status"""
    job = read_job(job_id) or {}
    job.update(kwargs)
    job['updated_at'] = datetime.now().isoformat()
    write_job(job_id, job)
    log(f"Job {job_id}: {kwargs.get('message', kwargs.get('status', ''))}")

def add_subscription_found(job_id, vendor_name, amount):
    """Track a found subscription"""
    job = read_job(job_id) or {}
    if 'subscriptions_found' not in job:
        job['subscriptions_found'] = []
    job['subscriptions_found'].append({
        'vendor': vendor_name,
        'amount': amount,
        'found_at': datetime.now().isoformat()
    })
    write_job(job_id, job)

def run_scan(job_id, credentials, days, user_email):
    """Run the full subscription scan"""
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    import base64
    import re
    import html as html_lib
    
    log(f"Starting scan for {user_email}, {days} days")
    update_job(job_id, status='running', progress=5, message='Connecting to Gmail...')
    
    last_refresh_time = time.time()
    REFRESH_INTERVAL = 45 * 60
    
    creds = OAuthCredentials(
        token=credentials.get('token'),
        refresh_token=credentials.get('refresh_token'),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv('GMAIL_CLIENT_ID'),
        client_secret=os.getenv('GMAIL_CLIENT_SECRET')
    )
    
    try:
        creds.refresh(Request())
        last_refresh_time = time.time()
        log("Token refreshed successfully")
    except Exception as e:
        log(f"Token refresh warning: {e}")
    
    service = build('gmail', 'v1', credentials=creds)
    
    update_job(job_id, progress=8, message='Counting total emails...')
    
    after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
    
    try:
        total_result = service.users().messages().list(
            userId='me', q=f'after:{after_date}', maxResults=1
        ).execute()
        total_inbox_emails = total_result.get('resultSizeEstimate', 0)
        update_job(job_id, progress=10, 
            message=f'📬 Total inbox: ~{total_inbox_emails:,} emails in last {days} days')
    except:
        total_inbox_emails = 0
    
    update_job(job_id, progress=12, message='🔍 Filtering for subscription keywords...')
    
    transactional_subjects = (
        'subject:receipt OR subject:invoice OR subject:payment OR subject:charged OR '
        'subject:subscription OR subject:billing OR subject:renewal OR '
        'subject:"your receipt" OR subject:"payment received" OR subject:"payment successful" OR '
        'subject:"your invoice" OR subject:"order confirmation"'
    )
    
    payment_processors = (
        'from:stripe.com OR from:paypal.com OR from:paddle.com OR '
        'from:gumroad.com OR from:chargebee.com OR from:recurly.com'
    )
    
    exclusions = '-subject:"newsletter" -subject:"webinar" -subject:"marketing"'
    
    query = f'after:{after_date} (({transactional_subjects}) OR ({payment_processors})) {exclusions}'
    
    all_message_ids = []
    page_token = None
    max_emails = min(days * 15, 10000)
    
    while True:
        if time.time() - last_refresh_time > REFRESH_INTERVAL:
            try:
                creds.refresh(Request())
                service = build('gmail', 'v1', credentials=creds)
                last_refresh_time = time.time()
                log("Token refreshed proactively")
            except Exception as e:
                log(f"Token refresh failed: {e}")
        
        results = service.users().messages().list(
            userId='me', q=query, pageToken=page_token, maxResults=500
        ).execute()
        
        messages = results.get('messages', [])
        all_message_ids.extend([m['id'] for m in messages])
        
        update_job(job_id, progress=15, 
            message=f'🔍 Keyword filter: {len(all_message_ids):,} potential emails...')
        
        page_token = results.get('nextPageToken')
        if not page_token or len(all_message_ids) >= max_emails:
            break
    
    potential_emails = len(all_message_ids)
    filter_pct = round((1 - potential_emails / max(total_inbox_emails, 1)) * 100, 1) if total_inbox_emails > 0 else 0
    update_job(job_id, progress=20, 
        message=f'📊 {total_inbox_emails:,} total → {potential_emails:,} potential ({filter_pct}% filtered)')
    
    if potential_emails == 0:
        update_job(job_id, status='complete', progress=100,
            message='No subscription emails found',
            results={'active_subscriptions': [], 'stopped_subscriptions': [], 
                    'active_count': 0, 'stopped_count': 0, 'monthly_spend': 0})
        return
    
    def extract_email_body(payload, snippet=""):
        plain_texts = []
        html_texts = []
        
        def decode_body(data):
            if not data:
                return ""
            try:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            except:
                return ""
        
        def sanitize_html(raw_html):
            if not raw_html:
                return ""
            text = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = html_lib.unescape(text)
            return text.strip()
        
        def extract_parts(part_payload):
            if 'parts' in part_payload:
                for part in part_payload['parts']:
                    extract_parts(part)
            else:
                mime_type = part_payload.get('mimeType', '')
                body_data = part_payload.get('body', {}).get('data', '')
                if mime_type == 'text/plain' and body_data:
                    plain_texts.append(decode_body(body_data))
                elif mime_type == 'text/html' and body_data:
                    html_texts.append(sanitize_html(decode_body(body_data)))
        
        extract_parts(payload)
        
        if plain_texts:
            return '\n'.join(plain_texts)[:3000]
        if html_texts:
            return '\n'.join(html_texts)[:3000]
        return snippet[:500]
    
    all_emails = []
    batch_size = 100
    
    for batch_start in range(0, len(all_message_ids), batch_size):
        batch_ids = all_message_ids[batch_start:batch_start + batch_size]
        progress = 20 + int((batch_start / len(all_message_ids)) * 30)
        update_job(job_id, progress=progress,
            message=f'Downloading emails {batch_start+1}-{min(batch_start+batch_size, len(all_message_ids))} of {len(all_message_ids)}...')
        
        if time.time() - last_refresh_time > REFRESH_INTERVAL:
            try:
                creds.refresh(Request())
                service = build('gmail', 'v1', credentials=creds)
                last_refresh_time = time.time()
                log("Token refreshed during download")
            except:
                pass
        
        for msg_id in batch_ids:
            try:
                msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
                
                email_data = {
                    'id': msg_id,
                    'subject': headers.get('subject', ''),
                    'sender': headers.get('from', ''),
                    'date': headers.get('date', ''),
                    'body': extract_email_body(msg.get('payload', {}), msg.get('snippet', ''))
                }
                all_emails.append(email_data)
            except Exception as e:
                if '401' in str(e):
                    try:
                        creds.refresh(Request())
                        service = build('gmail', 'v1', credentials=creds)
                        last_refresh_time = time.time()
                    except:
                        pass
    
    from services.subscription_pulse_service import SubscriptionPulseService
    pulse_service = SubscriptionPulseService()
    
    def stage1_progress(msg):
        update_job(job_id, progress=55, message=msg)
    
    update_job(job_id, progress=55, 
        message=f'⚡ Stage 1: AI analyzing {len(all_emails):,} emails...')
    
    email_queue = pulse_service.parallel_semantic_filter(all_emails, progress_callback=stage1_progress)
    
    def stage2_progress(msg):
        update_job(job_id, progress=70, message=msg)
    
    update_job(job_id, progress=70, 
        message=f'⚡ Stage 2: Deep extraction on {len(email_queue):,} emails...')
    
    processed_events = pulse_service.parallel_deep_extraction(email_queue, progress_callback=stage2_progress)
    
    for result in processed_events:
        if result:
            vendor_name = result.get('vendor_name', 'Unknown')
            amount = result.get('amount')
            add_subscription_found(job_id, vendor_name, f"${amount:.2f}" if amount else 'analyzing...')
    
    update_job(job_id, progress=85, 
        message=f'Aggregating data from {len(processed_events)} payment events...')
    
    results = pulse_service.aggregate_subscription_data(processed_events)
    
    update_job(job_id, progress=95, message='Saving results...')
    
    try:
        pulse_service.store_subscription_results(user_email, results)
    except Exception as e:
        log(f"Save error: {e}")
    
    final_count = results.get("active_count", 0)
    update_job(job_id, status='complete', progress=100,
        message=f'✅ COMPLETE: {total_inbox_emails:,} emails → {potential_emails:,} keyword → {len(email_queue):,} AI → {final_count} subscriptions',
        results=results)
    
    log(f"Scan complete: {final_count} subscriptions found")

def main():
    # Ensure job directory exists at the very start
    os.makedirs(JOBS_DIR, exist_ok=True)
    
    if len(sys.argv) != 5:
        print("Usage: subscription_scan_worker.py <job_id> <creds_file> <days> <user_email>", flush=True)
        sys.exit(1)
    
    job_id = sys.argv[1]
    creds_file = sys.argv[2]
    days = int(sys.argv[3])
    user_email = sys.argv[4]
    
    # Write initial job status immediately to confirm worker is alive
    update_job(job_id, status='running', progress=1, message='Worker process started...')
    log(f"Worker started: job={job_id}, days={days}, user={user_email}")
    
    try:
        with open(creds_file, 'r') as f:
            credentials = json.load(f)
    except Exception as e:
        log(f"Failed to load credentials: {e}")
        update_job(job_id, status='error', error=str(e), message='Failed to load credentials')
        sys.exit(1)
    
    try:
        run_scan(job_id, credentials, days, user_email)
    except Exception as e:
        log(f"Scan failed: {e}")
        traceback.print_exc()
        update_job(job_id, status='error', error=str(e), message=f'Scan failed: {str(e)}')
    finally:
        try:
            os.remove(creds_file)
        except:
            pass

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Last-resort error logging
        print(f"FATAL: Worker crashed at boot: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)
