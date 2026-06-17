import asyncio
import random
from loguru import logger
from playwright.async_api import async_playwright

from src.browser.manager import BrowserManager
from src.browser.harvester import SessionHarvester
from src.utils.database import DatabaseManager

# Target Event info
EVENT_URL = "https://weekendplanent.kktix.cc/events/8946d178"
TEST_PROFILE = "clc_surgical_test"

async def human_delay():
    """Introduces a random delay to mimic human interaction."""
    await asyncio.sleep(random.uniform(1.0, 3.0))

async def trace_checkout_flow():
    logger.info(f"🔎 Starting Surgical Flow Discovery for: {EVENT_URL}")
    
    db = DatabaseManager("data/session_cache.db")
    browser_mgr = BrowserManager()
    
    try:
        # 1. Setup Browser - Using Headless=True but with a high-fidelity profile
        browser = await browser_mgr.launch_browser(headless=True) 
        
        # Create context with a real device profile
        context = await browser_mgr.create_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
            is_mobile=False
        )
        
        # Attach Harvester
        harvester = SessionHarvester(db, TEST_PROFILE)
        await harvester.attach(context)
        
        page = await context.new_page()
        # Apply the manual stealth overrides we wrote in BrowserManager
        await browser_mgr.apply_stealth(page)
        
        # 2. Direct Navigation to Event Page
        # Bypassing the Home Page to avoid the heaviest bot-detection filters
        logger.info(f"Step 1: Navigating directly to Event Page: {EVENT_URL}")
        await page.goto(EVENT_URL, wait_until="domcontentloaded")
        await human_delay()
        
        # 3. Navigate to Ticket Page
        logger.info("Step 2: Looking for 'Buy Tickets' button")
        try:
            # Try various KKTIX buttons
            selectors = [
                "text='Get Tickets'", 
                "text='Buy Now'", 
                "text='Tickets'", 
                "button:has-text('Get Tickets')",
                "a:has-text('Get Tickets')"
            ]
            
            button_found = False
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible():
                        await element.click()
                        button_found = True
                        logger.info(f"Clicked button using selector: {selector}")
                        break
                except:
                    continue
            
            if not button_found:
                # Try searching for any element that looks like a buy button via text
                logger.warning("Standard selectors failed, searching for any ticket-related text...")
                # This is a broader fallback
                await page.click("text=Tickets", timeout=5000)
                button_found = True

            # Wait for the ticket selection page to load
            await page.wait_for_load_state("domcontentloaded")
            await human_delay()
            logger.success(f"Reached Ticket Page: {page.url}")
            
        except Exception as e:
            logger.error(f"Could not navigate to ticket page: {e}")

        # Final state capture
        await asyncio.sleep(5)
        logger.info(f"Final URL reached: {page.url}")
        logger.success("Surgical Flow discovery complete. Session transitions captured in DB.")
        
        await browser.close()

    except Exception as e:
        logger.exception(f"Flow discovery crashed: {e}")

if __name__ == "__main__":
    asyncio.run(trace_checkout_flow())
