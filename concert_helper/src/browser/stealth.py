from playwright.async_api import Page
from playwright_stealth import stealth_async
from loguru import logger
import random
import asyncio

class StealthManager:
    """
    ----------------- Browser Stealth Manager --------------------------
    Orchestrates browser fingerprint masking using playwright-stealth
    and adds behavioral humanity layers.
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]

    @staticmethod
    async def apply_stealth(page: Page):
        """
        Uses the official playwright-stealth library to mask webdriver flags.
        """
        try:
            await stealth_async(page)
            logger.debug("Official playwright-stealth applied to page.")
        except Exception as e:
            logger.error(f"Failed to apply playwright-stealth: {e}")

    @staticmethod
    def get_human_context_args():
        """Returns a set of realistic browser context arguments."""
        return {
            "user_agent": random.choice(StealthManager.USER_AGENTS),
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

    @staticmethod
    async def human_delay(min_sec: float = 0.5, max_sec: float = 1.5):
        """Simulates human thinking time to avoid pattern detection."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    @staticmethod
    async def jitter_mouse(page: Page):
        """Moves the mouse randomly to trigger 'isHuman' events."""
        try:
            x = random.randint(100, 500)
            y = random.randint(100, 500)
            await page.mouse.move(x, y, steps=10)
            logger.debug(f"Mouse jittered to {x}, {y}")
        except Exception as e:
            logger.warning(f"Mouse jitter failed: {e}")
