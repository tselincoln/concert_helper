import asyncio
import json
import random
from datetime import datetime
from typing import Any, Dict, Optional, List

from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from src.utils.database import DatabaseManager

class HybridSniper:
    """
    Hybrid Browser-Fetch Sniper.
    Bypasses dynamic request-bound tokens by executing native JS fetch() 
    within a stealth-hardened Playwright context.
    """

    def __init__(self, profile_name: str, db_manager: DatabaseManager):
        self.profile_name = profile_name
        self.db = db_manager
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Backoff settings
        self.base_delay = 1.0
        self.max_delay = 60.0
        self.backoff_multiplier = 2.0

    async def _setup_browser(self):
        """
        Initializes the stealth browser context and injects cached identity.
        """
        logger.info(f"Initializing Hybrid Sniper context for profile: {self.profile_name}")
        
        # 1. Retrieve freshest session from DB
        session = self.db.get_latest_session(self.profile_name)
        if not session:
            raise RuntimeError(f"No active session found in database for profile: {self.profile_name}")

        cookies = json.loads(session['cookies_json'])
        user_agent = session['user_agent']
        
        # Optional: Extract proxy from config if available (simplified for this implementation)
        # In a production env, this would pull from config.yaml via a ProxyProvider
        proxy_settings = None 

        self.playwright = await async_playwright().start()
        
        # 2. Launch isolated Chromium instance
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        # 3. Create stealth context
        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
            proxy=proxy_settings
        )

        # Inject cached cookies
        await self.context.add_cookies(cookies)

        # Apply stealth JS overrides to mask webdriver and hardware signals
        self.page = await self.context.new_page()
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """)

        # 4. Establish Origin Context
        # Navigating to the root domain prevents CORS blocks during JS fetch()
        domain = "https://weekendplanent.kktix.cc/" 
        logger.info(f"Establishing origin context at {domain}...")
        try:
            await self.page.goto(domain, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"Initial navigation failed, but proceeding with fetch: {e}")

        logger.success(f"Hybrid Sniper ready. Session injected for {self.profile_name}")

    async def _execute_js_fetch(self, url: str, method: str, payload: Dict = None, headers: Dict = None) -> Dict[str, Any]:
        """
        Executes a native JavaScript fetch() call within the browser page.
        """
        # Construct the JS payload
        # We use a self-invoking async function to handle the fetch and JSON parsing
        # We use destructuring in the arguments to receive a single object
        js_code = """
        async ({url, method, payload, headers}) => {
            try {
                const response = await fetch(url, {
                    method: method,
                    headers: headers || { 'Content-Type': 'application/json' },
                    body: payload ? JSON.stringify(payload) : null
                });
                
                const data = await response.json();
                return {
                    status: response.status,
                    ok: response.ok,
                    data: data
                };
            } catch (e) {
                return {
                    status: 0,
                    ok: false,
                    error: e.toString()
                };
            }
        }
        """
        
        # Pass all arguments as a single dictionary to comply with page.evaluate API
        result = await self.page.evaluate(js_code, {
            "url": url,
            "method": method,
            "payload": payload,
            "headers": headers
        })
        return result

    async def run_sniper_loop(self, target_url: str, request_payload: Dict, success_condition_key: str):
        """
        Asynchronous execution loop with exponential backoff.
        """
        current_delay = self.base_delay
        attempt = 1

        logger.info(f"Starting Hybrid Sniper loop on {target_url}")

        try:
            while True:
                logger.info(f"Attempt {attempt}: Dispatching Hybrid-Fetch request...")
                
                response = await self._execute_js_fetch(
                    url=target_url, 
                    method="POST", 
                    payload=request_payload
                )

                status = response.get('status')
                data = response.get('data', {})

                if status == 200 and response.get('ok'):
                    logger.success(f"Request successful! Payload: {data}")
                    
                    if success_condition_key in str(data):
                        logger.critical("!!! TARGET ACQUIRED: Ticket availability detected !!!")
                        return data
                    
                    # Reset backoff on a successful (but empty) response
                    current_delay = self.base_delay
                
                elif status == 429:
                    logger.warning(f"HTTP 429 Rate Limited. Backing off...")
                    await asyncio.sleep(current_delay)
                    current_delay = min(self.max_delay, current_delay * self.backoff_multiplier)
                
                elif status == 403 or status == 401:
                    logger.error(f"HTTP {status}: Session expired or Token Invalid. Breaking loop.")
                    break
                
                else:
                    logger.error(f"Unexpected response status {status}: {response.get('error')}")
                    await asyncio.sleep(current_delay)

                attempt += 1
                # Add slight jitter to avoid rhythmic detection
                await asyncio.sleep(current_delay + random.uniform(0.1, 0.5))

        except asyncio.CancelledError:
            logger.info("Sniper loop cancelled by user.")
        except Exception as e:
            logger.exception(f"Critical loop failure: {e}")
        finally:
            await self.close()

    async def close(self):
        """
        Ensures a clean termination of the browser process.
        """
        logger.info("Shutting down Hybrid Sniper resources...")
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Clean shutdown complete.")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

async def main():
    db = DatabaseManager()
    sniper = HybridSniper(profile_name="clc_surgical_test", db_manager=db)
    
    try:
        await sniper._setup_browser()
        
        target_url = "https://weekendplanent.kktix.cc/api/v1/events/8946d178/tickets"
        payload = {
            "ticket_type": "VIP",
            "quantity": 1
        }
        
        await sniper.run_sniper_loop(
            target_url=target_url, 
            request_payload=payload, 
            success_condition_key="available"
        )
        
    except Exception as e:
        logger.exception(f"Main execution error: {e}")
    finally:
        await sniper.close()

if __name__ == "__main__":
    asyncio.run(main())
