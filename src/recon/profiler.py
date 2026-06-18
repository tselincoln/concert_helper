import asyncio
import sys
import json
from typing import List, Dict, Any

# Import project components
from src.utils.database import DatabaseManager

class Profiler:
    """
    ----------------- Autonomous Research Module --------------------------
    Analyzes a target site via a 'sandbox' URL to map out structural element selectors.
    """

    def __init__(self, sandbox_url: str):
        self.sandbox_url = sandbox_url
        # Initialize the DatabaseManager to handle schema persistence
        self.db = DatabaseManager()

    async def perform_scan(self, page, event_id: str, target_url: str) -> Dict[str, str]:
        full_schema = {
            "event_id": event_id,
            "target_url": target_url,
            "next_step_btn": "",
            "ticket_zone_selector": "",
            "quantity_plus_btn": "",
            "terms_checkbox": "",
            "field_username": "",
            "field_email": "",
            "field_phone": "",
            "payment_confirm_btn": ""
        }

        # Heuristic Mapping: selector patterns -> schema key
        heuristics = [
            ("button", "next_step_btn", ["下一步", "Next", "Proceed"]),
            ("radio", "ticket_zone_selector", ["quantity", "selection"]),
            ("button", "quantity_plus_btn", ["+"]),
            ("input", "terms_checkbox", ["terms", "agreement", "check"]),
            ("input", "field_username", ["name", "user"]),
            ("input", "field_email", ["email", "mail"]),
            ("input", "field_phone", ["phone", "mobile"]),
            ("button", "payment_confirm_btn", ["confirm", "pay", "order"])
        ]

        for tag, key, keywords in heuristics:
            try:
                for kw in keywords:
                    # XPath approach for highly flexible text/attribute matching
                    potential_xpath = f"//{tag}[contains(text(), '{kw}') or contains(@placeholder, '{kw}') or contains(@name, '{kw}')]"
                    elements = await page.query_selector_all(potential_xpath)
                    if elements:
                        el = elements[0]
                        selector = await self._get_robust_selector(el)
                        full_schema[key] = selector
                        break
            except Exception:
                continue

        # Save to DB
        domain = target_url.split("//")[-1].split("/")[0]
        for key, val in full_schema.items():
            if key != "event_id" and key != "target_url":
                self.db.update_site_schema(domain, key, "xpath", val)

        return full_schema

    async def scan(self, event_id: str):
        """The main entry point for the profiling session."""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            # Requirement: Headless=False so you can observe the DOM scan
            browser = await p.chromium.launch(headless=False) 
            
            context = await browser.new_context()
            page = await context.new_page()

            try:
                print(f"Navigating to: {self.sandbox_url}")
                await page.goto(self.sandbox_url, wait_until="networkidle")
                
                # Brief sleep to ensure heavy-duty client-side JS finishes loading
                await asyncio.sleep(2) 
                
                print("Scanning for elements...")
                schema = await self.perform_scan(page, event_id, self.sandbox_url)
                
                # Output the JSON schema to stdout as requested
                print(json.dumps(schema, indent=2))
                return schema

            except Exception as e:
                print(f"Error during profiling: {e}")
                raise
            finally:
                await browser.close()

    async def _get_robust_selector(self, element) -> str:
        tag = await element.evaluate("el => el.tagName.toLowerCase()")
        name = await element.get_attribute("name")
        id_attr = await element.get_attribute("id")
        placeholder = await element.get_attribute("placeholder")

        if id_attr:
            return f"//{tag}[@id='{id_attr}']"
        if name:
            return f"//{tag}[@name='{name}']"
        if placeholder:
            return f"//{tag}[contains(@placeholder, '{placeholder}')]"
        
        # Last resort: text-based xpath
        text = await element.inner_text()
        if text:
            clean_text = text.strip().replace("'", "")
            return f"//{tag}[contains(text(), '{clean_text}')]"
        
        return f"//{tag}"
