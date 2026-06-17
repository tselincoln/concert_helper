import asyncio
from loguru import logger
from playwright.async_api import async_playwright
from src.utils.database import DatabaseManager
from src.browser.harvester import SessionHarvester

async def test_session_harvesting():
    db = DatabaseManager("data/session_cache.db")
    profile_name = "test_harvester_profile"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        harvester = SessionHarvester(db, profile_name, "http://fake-proxy:8080")
        await harvester.attach(context)
        page = await context.new_page()
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
        await browser.close()
    session = db.get_latest_session(profile_name)
    if session:
        logger.success(f"✅ Session successfully harvested for {profile_name}!")
        logger.info(f"User-Agent: {session['user_agent']}")
        logger.info(f"Cookies Data Length: {len(session['cookies_json'])}")
    else:
        logger.error("❌ No session found in database.")
        raise Exception("Harvesting Test Failed")

if __name__ == "__main__":
    asyncio.run(test_session_harvesting())
