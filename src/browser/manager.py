from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from typing import Optional

class BrowserManager:
    """
    Manages the lifecycle of the Playwright browser instance.
    Implements custom stealth overrides to bypass bot detection without external dependencies.
    """
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None

    async def launch_browser(self, headless: bool = True) -> Browser:
        """
        Launches a Playwright Chromium browser with stealth-optimized arguments.
        """
        if self.browser:
            return self.browser

        try:
            logger.info(f"Launching stealth browser (headless={headless})...")
            self.playwright = await async_playwright().start()
            
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-position=0,0",
                    "--window-size=1920,1080",
                ]
            )
            logger.success("Browser launched successfully.")
            return self.browser
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    async def create_context(self, **kwargs) -> BrowserContext:
        """
        Creates a standard browser context.
        """
        if not self.browser:
            raise RuntimeError("Browser must be launched before creating a context.")
        return await self.browser.new_context(**kwargs)

    async def apply_stealth(self, page: Page):
        """
        Applies a comprehensive set of JS overrides to mask Playwright automation.
        Mimics a real Chrome browser by overriding navigator and window properties.
        """
        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        
        // Mask permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return originalQuery(parameters);
        };

        // Mask WebGL vendor/renderer
        const getParameter = HTMLCanvasElement.prototype.getContext;
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel(R) Iris(R) Plus Graphics 640';
            return originalGetParameter.apply(this, arguments);
        };
        """
        await page.add_init_script(stealth_js)
        logger.debug("Manual stealth overrides applied to page.")

    async def close(self):
        """Cleanly closes the browser and playwright instance."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        logger.info("Browser resources released.")
