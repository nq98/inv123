#!/usr/bin/env python3
"""
Standalone HTML-to-PDF converter script that runs Playwright in an isolated process.
Used by gmail_service.py to avoid blocking the main gevent event loop.
"""
import sys
import os
import base64
import json
import glob
import shutil

def find_chromium():
    """Find system Chromium executable"""
    possible_paths = [
        '/nix/store/*/bin/chromium',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
    ]
    
    for pattern in possible_paths:
        if '*' in pattern:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
        elif os.path.exists(pattern):
            return pattern
    
    return shutil.which('chromium') or shutil.which('chromium-browser')

def generate_pdf(html_content):
    """Generate PDF from HTML content using Playwright"""
    from playwright.sync_api import sync_playwright
    import time
    
    chromium_path = find_chromium()
    
    with sync_playwright() as p:
        launch_options = {
            'headless': True,
            'timeout': 15000,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        }
        
        if chromium_path:
            launch_options['executable_path'] = chromium_path
        
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(
            viewport={'width': 800, 'height': 1200},
            bypass_csp=True,
            java_script_enabled=False
        )
        page = context.new_page()
        
        page.set_content(html_content, wait_until='commit', timeout=10000)
        
        time.sleep(0.3)
        
        pdf_data = page.pdf(
            format='A4',
            print_background=True,
            margin={'top': '20px', 'right': '20px', 'bottom': '20px', 'left': '20px'}
        )
        
        context.close()
        browser.close()
        
        return pdf_data

def main():
    """Main entry point - reads HTML from stdin, outputs base64 PDF to stdout"""
    try:
        html_content = sys.stdin.read()
        
        if not html_content:
            print(json.dumps({'success': False, 'error': 'No HTML content provided'}))
            sys.exit(1)
        
        pdf_data = generate_pdf(html_content)
        
        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        
        print(json.dumps({
            'success': True,
            'pdf_data': pdf_base64,
            'size': len(pdf_data)
        }))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({
            'success': False,
            'error': str(e)
        }))
        sys.exit(1)

if __name__ == '__main__':
    main()
