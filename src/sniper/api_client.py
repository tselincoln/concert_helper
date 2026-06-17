import asyncio
import json
import random
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from curl_cffi.requests import AsyncSession
from loguru import logger

# Import the existing DatabaseManager from our utils
from src.utils.database import DatabaseManager

class SniperAPIClient:
    """
    High-performance asynchronous API client designed for request-based sniping.
    Utilizes curl_cffi to impersonate browser TLS fingerprints and JA4 signatures.
    """

    def __init__(
        self, 
        profile_name: str, 
        db_path: str = "data/session_cache.db", 
        impersonate: str = "chrome110"
    ):
        self.profile_name = profile_name
        self.db_path = db_path
        self.impersonate = impersonate
        self.db = DatabaseManager(self.db_path)
        
        # Session state
        self.session: Optional[AsyncSession] = None
        self.user_agent: Optional[str] = None
        self.proxy: Optional[str] = None
        self.base_headers: Dict[str, str] = {}
        
        # Backoff settings
        self.base_backoff = 1.0  # Seconds
        self.max_backoff = 60.0
        self.backoff_multiplier = 2

    async def initialize(self):
        """
        Prepares the client by loading the latest session state from SQLite 
        and configuring the AsyncSession fingerprint.
        """
        logger.info(f"Initializing Sniper Client for profile: {self.profile_name}...")
        
        # 1. Retrieve session state from DB
        session_data = self.db.get_latest_session(self.profile_name)
        if not session_data:
            raise RuntimeError(f"No active session found in DB for profile {self.profile_name}. Run the Harvester first.")

        self.user_agent = session_data.get("user_agent")
        cookies_list = json.loads(session_data.get("cookies_json", "[]"))
        tokens = json.loads(session_data.get("anti_bot_tokens", "{}"))
        
        # In a real scenario, we would map the profile to a proxy from config.yaml
        # For this self-contained client, we assume the proxy is stored or passed.
        # If not in DB, we default to None (direct connection).
        self.proxy = session_data.get("proxy") 

        # 2. Configure the AsyncSession with Browser Impersonation
        # impersonate="chrome110" enforces the TLS/JA3 and HTTP/2 frame layout of Chrome
        self.session = AsyncSession(
            impersonate=self.impersonate,
            proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None
        )

        # 3. Inject Cookies and Headers
        # Map Playwright cookie list to a dict for curl_cffi
        cookie_dict = {c['name']: c['value'] for c in cookies_list}
        self.session.cookies.update(cookie_dict)

        # Setup headers to match the User-Agent and inject anti-bot tokens (reese84, etc.)
        self.base_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://target-site.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        # Merge anti-bot tokens into headers
        self.base_headers.update(tokens)
        
        logger.success(f"Sniper Client ready. Impersonating {self.impersonate} for {self.profile_name}")

    async def _request_with_backoff(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Internal wrapper to handle network jitter and HTTP 429 Rate Limiting 
        using an exponential backoff strategy.
        """
        attempt = 0
        current_delay = self.base_backoff

        while True:
            try:
                # Merge base headers with request-specific headers
                headers = {**self.base_headers, **kwargs.pop("headers", {})}
                
                response = await self.session.request(
                    method=method, 
                    url=url, 
                    headers=headers, 
                    **kwargs
                )

                # Handle HTTP 429 Too Many Requests
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after and retry_after.isdigit() else current_delay
                    
                    logger.warning(f"HTTP 429 Detected. Backing off for {wait_time:.2f}s... (Attempt {attempt + 1})")
                    await asyncio.sleep(wait_time)
                    
                    # Update delay for next time (Exponential)
                    current_delay = min(current_delay * self.backoff_multiplier, self.max_backoff)
                    attempt += 1
                    continue

                # Handle other non-200 responses
                if response.status_code != 200:
                    logger.error(f"Unexpected Status {response.status_code} for {url}: {response.text[:100]}")
                    return None

                # Parse JSON with safety
                return response.json()

            except Exception as e:
                logger.error(f"Network error during request: {e}")
                # Apply exponential backoff on network failure
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * self.backoff_multiplier, self.max_backoff)
                attempt += 1
                
        return None

    async def poll_inventory(self, target_url: str, interval_ms: int = 100):
        """
        Asynchronous polling loop that checks a target API endpoint.
        Executes at the same millisecond interval requested.
        """
        logger.info(f"Starting inventory poll on {target_url} at {interval_ms}ms intervals...")
        
        poll_count = 0
        while True:
            try:
                start_time = asyncio.get_event_loop().time()
                
                # Execute the request
                result = await self._request_with_backoff("GET", target_url)
                
                if result:
                    # Logical placeholder for inventory check
                    logger.info(f"Poll {poll_count + 1}: Data received. Status: {result.get('status', 'Unknown')}")
                else:
                    logger.info(f"Poll {poll_count + 1}: API returned empty or malformed data.")
                
                poll_count += 1
                
                # Precision timing for the interval
                # We subtract the request time from the sleep time to maintain a constant frequency
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, (interval_ms / 1000.0) - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("Polling loop cancelled by user.")
                break
            except Exception as e:
                logger.error(f"Critical error in polling loop: {e}")
                # Prevent a tight loop of crashes (Safety)
                await asyncio.sleep(1)
                
        return None

    async def close(self):
        """
        Cleanup the session resources.
        """
        if self.session:
            await self.session.close()
        logger.info(f"Sniper Client for {self.profile_name} closed.")
