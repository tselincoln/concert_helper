"""
src/sniper/click_sniper.py

This module implements the ClickSniper class, the primary orchestration engine for 
browser-based ticket acquisition. It uses a schema-driven approach to interact 
with the target website, employing human-mimicking actions to avoid bot detection.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from loguru import logger
from playwright.async_api import Browser, Page, TimeoutError

from src.utils.database import DatabaseManager
from src.config.loader import load_profiles
from src.sniper.context_factory import LeanContextFactory
from src.sniper.stealth_actions import wait_for_active, human_click, human_type

class ClickSniper:
    """
    The central sniper class responsible for the full checkout flow.
    It decouples selectors (recon schema) and user data (profiles) from 
    the execution logic.
    """

    def __init__(self, browser: Browser, profile: Any, event_id: str, db_path: str):
        self.browser = browser
        self.profile = profile
        self.event_id = event_id
        self.db_path = db_path
        
        # Initialize data access
        self.store = DatabaseManager()
        
        # Load recon schema for the specific event
        # Expects a JSON dict of selectors from the site_schemas table
        self.schema = self._load_event_schema(event_id)
        if not self.schema:
            raise RuntimeError(f"No recon schema found for event_id: {event_id}")
        
        # Set target URL from the schema
        self.target_url = self.schema.get("target_url")
        if not self.target_url:
            raise RuntimeError(f"target_url missing in schema for event {event_id}")
            
        # Configurable API path patterns to monitor in the response observer
        self.api_patterns = ["/api/", "/checkout/", "/payment/", "/order/"]

    def _load_event_schema(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the mapped DOM selectors for the event from the database.
        """
        # Use the DatabaseManager to fetch the schema for the event
        return self.store.get_schema(event_id)

    async def _handle_response(self, response):
        """
        Network Response Observer: Logs interactions with sensitive API endpoints.
        """
        url = response.url
        if any(pattern in url for pattern in self.api_patterns):
            status = response.status
            logger.info(f"API Interaction Detected: {url} | Status: {status}")
            
            # Log the event to SQLite checkout_logs
            try:
                self.store.log_checkout(
                    profile=self.profile.name,
                    status="API_CALL",
                    payload={"url": url, "status": status},
                    error=None
                )
            except Exception as e:
                logger.error(f"Failed to log API response to DB: {e}")

    async def _fill_checkout(self, page: Page) -> None:
        """
        Iterates through required billing fields and fills them if the elements exist.
        """
        # Assuming profile is a dataclass/object from loader.py
        # If it's a dict, use .get()
        billing = getattr(self.profile, 'billing', {}) if not isinstance(self.profile, dict) else self.profile.get('billing', {})
        
        # Map schema keys to profile data keys
        field_mapping = {
            "field_username": billing.get("name"),
            "field_email": billing.get("email"),
            "field_phone": billing.get("phone"),
            "field_card": billing.get("card_number"),
            "field_expiry": billing.get("expiry"),
            "field_cvv": billing.get("cvv"),
        }

        for schema_key, value in field_mapping.items():
            if value is None:
                continue
            
            selector = self.schema.get(schema_key)
            if not selector:
                continue

            # Check if the element actually exists on the current page before typing
            element = await page.query_selector(selector)
            if element:
                logger.debug(f"Filling field {schema_key} using selector {selector}")
                await human_type(page, selector, str(value))
            else:
                logger.debug(f"Field {schema_key} not found on page; skipping.")

    async def run(self) -> bool:
        """
        Executes the full snipe sequence from navigation to form submission.
        Returns True on success, False on TimeoutError.
        """
        context = None
        try:
            # Step 1 — Context Setup
            # Create a lean context (Cookies, UA, Fingerprints) via the factory
            proxy_conf = {"server": self.profile.proxy_url} if self.profile.proxy_url else None
            from src.sniper.context_factory import BillingProfile as BillingProfileDC
            billing_obj = BillingProfileDC(
                name=self.profile.name,
                email=self.profile.billing.get("email", ""),
                phone=self.profile.billing.get("phone", ""),
                card_number=self.profile.billing.get("card_number", ""),
                expiry=self.profile.billing.get("expiry", ""),
                cvv=self.profile.billing.get("cvv", ""),
                proxy_url=self.profile.proxy_url,
            )
            factory = LeanContextFactory(self.browser, proxy_conf, billing_obj)
            context = await factory.create()
            page = await context.new_page()

            # Step 7 — Network Response Observer
            # Attach listener before any navigation occurs
            page.on("response", self._handle_response)

            # Step 2 — Navigation
            logger.info(f"Navigating to event page: {self.target_url}")
            await page.goto(self.target_url, wait_until="domcontentloaded")
            logger.info("Navigated to event page")

            # Step 3 — Ticket Selection
            select_btn = self.schema.get("next_step_btn") # Match recon schema key
            await wait_for_active(page, select_btn)
            await human_click(page, select_btn)
            logger.info("Ticket type selected")

            # Step 4 — Add to Cart / Proceed
            # In some KKTIX flows, this is a separate btn. If not in schema, skip.
            add_btn = self.schema.get("quantity_plus_btn")
            if add_btn:
                await wait_for_active(page, add_btn)
                await human_click(page, add_btn)
                logger.info("Quantity adjusted")

            # Step 5 — Proceed to Checkout
            checkout_btn = self.schema.get("payment_confirm_btn")
            if checkout_btn:
                await wait_for_active(page, checkout_btn)
                await human_click(page, checkout_btn)
                logger.info("Navigated to checkout")

            # Step 6 — Form Fill
            await self._fill_checkout(page)
            logger.info("Checkout form filled successfully")

            return True

        except TimeoutError:
            logger.error(f"Snipe failed: Timeout reached while waiting for elements.")
            self.store.log_checkout(
                profile=self.profile.name,
                status="TIMEOUT",
                payload=None,
                error="Playwright TimeoutError during execution flow"
            )
            return False
            
        except Exception as e:
            logger.exception(f"Unexpected error during snipe: {e}")
            self.store.log_checkout(
                profile=self.profile.name,
                status="CRASH",
                payload=None,
                error=str(e)
            )
            return False
            
        finally:
            if context:
                await context.close()
