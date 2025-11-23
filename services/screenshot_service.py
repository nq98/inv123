import os
import subprocess
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time

class ScreenshotService:
    """Service for capturing web receipt screenshots using Playwright"""
    
    def __init__(self):
        self.timeout = 30000  # 30 seconds
        self.chromium_path = self._find_chromium_executable()
    
    def _find_chromium_executable(self):
        """Find system Chromium executable (Nix-installed or system)"""
        possible_paths = [
            '/nix/store/*/bin/chromium',  # Nix-installed Chromium
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            'chromium',  # Try PATH
        ]
        
        # Check Nix store first
        try:
            result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                print(f"✓ Found Chromium at: {result.stdout.strip()}")
                return result.stdout.strip()
        except:
            pass
        
        # Fallback to default
        return None
        
    def capture_receipt_screenshot(self, url, wait_for_selector=None):
        """
        Capture screenshot of web receipt page
        
        Args:
            url: URL to screenshot
            wait_for_selector: Optional CSS selector to wait for before screenshot
        
        Returns:
            bytes: PNG screenshot data, or None if failed
        """
        
        try:
            with sync_playwright() as p:
                # Launch Chromium in headless mode
                launch_options = {
                    'headless': True,
                    'args': [
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu'
                    ]
                }
                
                # Use system Chromium if available (Nix-installed)
                if self.chromium_path:
                    launch_options['executable_path'] = self.chromium_path
                
                browser = p.chromium.launch(**launch_options)
                
                # Create new page
                page = browser.new_page(
                    viewport={'width': 1280, 'height': 1024},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                print(f"📸 Navigating to: {url[:100]}...")
                
                # Navigate to URL
                try:
                    page.goto(url, timeout=self.timeout, wait_until='networkidle')
                except PlaywrightTimeout:
                    print(f"⚠️ Timeout navigating to {url}, continuing anyway...")
                    pass
                
                # Wait for specific selector if provided
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=5000)
                    except PlaywrightTimeout:
                        print(f"⚠️ Selector {wait_for_selector} not found, continuing...")
                        pass
                
                # Give page a moment to fully render
                time.sleep(2)
                
                # Take screenshot
                screenshot_bytes = page.screenshot(
                    full_page=True,
                    type='png'
                )
                
                print(f"✅ Screenshot captured: {len(screenshot_bytes):,} bytes")
                
                browser.close()
                
                return screenshot_bytes
                
        except Exception as e:
            print(f"❌ Screenshot capture failed: {str(e)}")
            return None
    
    def capture_with_scroll(self, url, scroll_delay=1):
        """
        Capture screenshot with scrolling to trigger lazy-loaded content
        
        Args:
            url: URL to screenshot
            scroll_delay: Seconds to wait between scrolls
        
        Returns:
            bytes: PNG screenshot data, or None if failed
        """
        
        try:
            with sync_playwright() as p:
                launch_options = {
                    'headless': True,
                    'args': ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                }
                
                if self.chromium_path:
                    launch_options['executable_path'] = self.chromium_path
                
                browser = p.chromium.launch(**launch_options)
                
                page = browser.new_page(
                    viewport={'width': 1280, 'height': 1024}
                )
                
                # Navigate
                page.goto(url, timeout=self.timeout, wait_until='networkidle')
                
                # Scroll down to load lazy content
                page.evaluate("""
                    async () => {
                        const scrollHeight = document.body.scrollHeight;
                        const scrollStep = window.innerHeight;
                        let currentScroll = 0;
                        
                        while (currentScroll < scrollHeight) {
                            window.scrollBy(0, scrollStep);
                            currentScroll += scrollStep;
                            await new Promise(resolve => setTimeout(resolve, 500));
                        }
                        
                        // Scroll back to top
                        window.scrollTo(0, 0);
                    }
                """)
                
                time.sleep(scroll_delay)
                
                # Take screenshot
                screenshot_bytes = page.screenshot(
                    full_page=True,
                    type='png'
                )
                
                browser.close()
                
                return screenshot_bytes
                
        except Exception as e:
            print(f"❌ Screenshot with scroll failed: {str(e)}")
            return None
