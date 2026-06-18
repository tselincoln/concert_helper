"""
src/sniper/context_factory.py

This module provides the LeanContextFactory, designed to create high-performance, 
low-overhead Playwright BrowserContexts for ticket sniping operations.

RESOURCE BLOCKING STRATEGY:
To minimize latency and reduce bandwidth consumption during high-frequency 
polling/checkout, the factory implements a request interception layer that 
aborts the loading of non-essential assets:
- images: Visuals are not required for DOM interaction or API dispatch.
- media: Videos/audio are completely irrelevant to the automation flow.
- fonts: Custom web-fonts increase page load time without affecting logic.

Note: Stylesheets (css) are EXPLICITLY NOT blocked. Many modern anti-bot 
implementations and dynamic UIs use CSS properties (e.g., 'display: none' or 
'visibility: hidden') to determine if an element is actually visible to a 
human. Blocking CSS can lead to 'ElementNotInteractable' errors or trigger 
bot-detection flags when a script attempts to click a hidden element.
"""

import json
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from playwright.async_api import Browser, BrowserContext, Route
from src.utils.database import DatabaseManager as Store

@dataclass
class BillingProfile:
    """
    Encapsulates user payment and identity information for the checkout process.
    """
    name: str
    email: str
    phone: str
    card_number: str
    expiry: str
    cvv: str
    proxy_url: Optional[str] = None

class LeanContextFactory:
    """
    Factory for creating optimized BrowserContexts tailored for sniping.
    Handles proxy configuration, session restoration, and resource pruning.
    """

    def __init__(
        self, 
        browser: Browser, 
        proxy: Optional[Dict[str, Any]], 
        billing_profile: BillingProfile
    ):
        """
        Initialize the factory with required orchestration dependencies.

        Args:
            browser: The active Playwright browser instance.
            proxy: Proxy configuration dictionary (server, username, password).
            billing_profile: The identity profile used for this specific context.
        """
        self.browser = browser
        self.proxy = proxy
        self.billing_profile = billing_profile
        self.store = Store()
        
        # Defined set of resource types to abort for performance optimization
        self._blocked_resources: Set[str] = {"image", "media", "font"}

    async def _handle_route(self, route: Route) -> None:
        """
        Interceptor handler to prune unnecessary network requests.
        """
        request = route.request
        if request.resource_type in self._blocked_resources:
            await route.abort()
        else:
            await route.continue_()

    async def create(self) -> BrowserContext:
        """
        Configures and returns a production-ready, lean BrowserContext.

        The process follows these steps:
        1. Initialize context with proxy and fixed viewport.
        2. Register the global resource interceptor.
        3. Restore session identity (cookies) from the SQLite store.

        Returns:
            A fully configured playwright.async_api.BrowserContext.
        
        Raises:
            RuntimeError: If session cookies cannot be retrieved for the profile.
        """
        # 1. Create Context with specific viewport and proxy settings
        # Viewport is set to a standard desktop resolution to avoid 'mobile' detection
        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            proxy=self.proxy
        )

        # 2. Register resource blocking route handler
        # Using '**/*' ensures all requests across all domains are intercepted
        await context.route("**/*", self._handle_route)

        # 3. Restore Session Identity
        # Fetch the latest session for this specific billing profile name
        session = self.store.get_latest_session(self.billing_profile.name)
        
        if not session:
            # We cannot proceed with a sniper context without a valid identity
            # This forces the user back to the collector.py HITL flow
            raise RuntimeError(
                f"No active session found in data/session_cache.db for profile: {self.billing_profile.name}. "
                "Please run the collector first to harvest cookies."
            )

        # Handle cookie storage format (assuming JSON string in SQLite)
        try:
            cookies_data = session.get("cookies_json")
            if isinstance(cookies_data, str):
                cookies = json.loads(cookies_data)
            else:
                cookies = cookies_data

            if cookies:
                await context.add_cookies(cookies)
        except (json.JSONDecodeError, TypeError) as e:
            # Log failure but allow context creation to proceed; 
            # the sniper will likely fail on the first request anyway.
            print(f"[CRITICAL] Failed to parse session cookies for {self.billing_profile.name}: {e}")

        return context

# --- Integration Test Block ---
if __name__ == "__main__":
    async def test_factory():
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            
            # Mocking a BillingProfile
            profile = BillingProfile(
                name="test_user",
                email="test@example.com",
                phone="123456789",
                card_number="4111111111111",
                expiry="12/26",
                cvv="123"
            )
            
            factory = LeanContextFactory(browser, None, profile)
            try:
                ctx = await factory.create()
                print("Successfully created lean context.")
                await ctx.close()
            except Exception as e:
                print(f"Factory test failed as expected (no DB session): {e}")
            
            await browser.close()

    asyncio.run(test_factory())
