import asyncio
import json
from loguru import logger
from playwright.async_api import async_playwright

from src.utils.database import DatabaseManager
from src.browser.manager import BrowserManager
from src.browser.harvester import SessionHarvester
from src.sniper.api_client import SniperAPIClient

# Real Target Data
TARGET_URL = "https://weekendplanent.kktix.cc/events/8946d178"
API_ENDPOINT = "https://weekendplanent.kktix.cc/api/v1/events/8946d178"
TEST_PROFILE = "clc_real_test"

async def run_integration_test():
    logger.info("🚀 Starting End-to-End Integration Test: Browser -> DB -> Sniper")
    
    db = DatabaseManager("data/session_cache.db")
    browser_mgr = BrowserManager()
    
    try:
        # =========================================================================
        # PHASE 1: REAL HARVESTING
        # =========================================================================
        logger.info("--- Phase 1: Harvesting Real Session ---")
        
        # Launch browser and context
        # Use headless=True for the VM environment, but stealth is active
        browser = await browser_mgr.launch_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        # Initialize Harvester
        harvester = SessionHarvester(db, TEST_PROFILE)
        await harvester.attach(context)
        
        page = await context.new_page()
        logger.info(f"Navigating to target event: {TARGET_URL}")
        
        # Navigate and wait for responses to be harvested
        await page.goto(TARGET_URL, wait_until="networkidle")
        # Give the harvester a moment to process any trailing API responses
        await asyncio.sleep(5) 
        
        logger.info("Harvesting complete. Closing browser...")
        await browser.close()
        
        # =========================================================================
        # PHASE 2: REAL SNIPING
        # =========================================================================
        logger.info("--- Phase 2: Sniping with Harvested State ---")
        
        # Initialize Sniper Client
        # This should pull the real cookies/tokens we just saved into the DB
        sniper = SniperAPIClient(profile_name=TEST_PROFILE)
        await sniper.initialize()
        
        logger.info(f"Attempting real API poll on: {API_ENDPOINT}")
        
        # Perform a few real requests to verify identity and connectivity
        for i in range(3):
            result = await sniper._request_with_backoff("GET", API_ENDPOINT)
            if result:
                logger.success(f"Request {i+1} SUCCESS: Received real data from KKTIX API")
                # Log a snippet of the real data for verification
                logger.debug(f"API Response Snippet: {str(result)[:200]}...")
            else:
                logger.error(f"Request {i+1} FAILED: API returned non-200 or errored.")
            await asyncio.sleep(1)
            
        await sniper.close()
        logger.success("Integration Test Completed Successfully!")

    except Exception as e:
        logger.exception(f"Integration test crashed: {e}")
    finally:
        # Optional: Cleanup test profile from DB
        with db.get_connection() as conn:
            conn.execute("DELETE FROM active_sessions WHERE profile_name = ?", (TEST_PROFILE,))
            conn.commit()

if __name__ == "__main__":
    asyncio.run(run_integration_test())
