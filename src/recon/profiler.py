import asyncio
import json
from urllib.parse import urlparse
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Page
from src.utils.database import DatabaseManager
from loguru import logger

class SiteProfiler:
    """
    ----------------- Autonomous Research Module --------------------------
    Analyzes a target site via a 'sandbox' URL to map out structural element selectors.
    """

    # Heuristic signatures for common high-value elements
    HEURISTICS = {
        "login_fields": [
            {"attr": "type", "val": "email"},
            {"attr": "type", "val": "password"},
            {"attr": "name", "val": "email"},
            {"attr": "name", "val": "username"},
            {"attr": "placeholder", "val": "Email Address"},
        ],
        "seat_selectors": [
            {"attr": "role", "val": "button"},
            {"attr": "class", "val": "seat"},
            {"attr": "data-type", "val": "selection"},
            {"attr": "aria-label", "val": "Select"},
        ],
        "checkout_elements": [
            {"attr": "name", "val": "payment"},
            {"attr": "id", "val": "checkout"},
            {"attr": "role", "val": "button"},
            {"attr": "type", "val": "submit"},
        ]
    }

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def _get_robust_xpath(self, element: any) -> str:
        name = await element.get_attribute("name")
        if name and not any(char.isdigit() for char in name):
            return f"//{await element.evaluate('el => el.tagName.toLowerCase()')} [@name='{name}']"

        elem_type = await element.get_attribute("type")
        if elem_type:
            tag = await element.evaluate('el => el.tagName.toLowerCase()')
            return f"//{tag}[@type='{elem_type}']"

        placeholder = await element.get_attribute("placeholder")
        if placeholder:
            tag = await element.evaluate('el => el.tagName.toLowerCase()')
            return f"//{tag}[contains(@placeholder, '{placeholder}')]"

        role = await element.get_attribute("role")
        if role:
            tag = await element.evaluate('el => el.tagName.toLowerCase()')
            return f"//{tag}[@role='{role}']"

        tag = await element.evaluate('el => el.tagName.toLowerCase()')
        return f"//body//{tag}"

    async def perform_scan(self, page: Page):
        full_schema = {}
        for category in self.HEURISTICS.keys():
            signatures = self.HEURISTICS[category]
            for sig in signatures:
                attr = sig["attr"]
                val = sig["val"]
                selector = f"[{attr}='{val}']"
                try:
                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        xpath = await self._get_robust_xpath(el)
                        key = f"{category}_{attr}_{val}"
                        full_schema[key] = xpath
                except Exception:
                    continue
        return full_schema

    async def profile_site(self, target_url: str, sandbox_url: str):
        domain = urlparse(target_url).netloc
        logger.info(f"Starting recon for domain: {domain} using sandbox: {sandbox_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
            page = await context.new_page()

            try:
                await page.goto(sandbox_url, wait_until="networkidle")
                logger.debug("Sandbox navigation complete. Beginning element scan...")

                full_schema = await self.perform_scan(page)

                if not full_schema:
                    logger.warning(f"No heuristic-based elements discovered for {domain}.")

                for field_id, xpath in full_schema.items():
                    await self.db.update_site_schema(
                        domain=domain,
                        field_id=field_id,
                        sel_type="xpath",
                        sel_val=xpath
                    )

                logger.info(f"Successfully mapped {len(full_schema)} elements for {domain}")
                return full_schema

            except Exception as e:
                logger.error(f"Profiling failed for {domain}: {e}")
                raise
            finally:
                await browser.close()
