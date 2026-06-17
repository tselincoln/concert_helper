import json
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger
from playwright.async_api import BrowserContext, Response
from src.utils.database import DatabaseManager

class SessionHarvester:
    TARGET_TOKENS = {
        "cf_clearance", "reese84", "bm_sz", "sid", "auth_token", "session_id", "csrftoken",
    }

    def __init__(self, db_manager: DatabaseManager, profile_name: str, proxy_url: Optional[str] = None):
        self.db = db_manager
        self.profile_name = profile_name
        self.proxy_url = proxy_url
        self._last_saved_state = set()
        self._context = None
        self._ua = "Unknown"
        logger.info(f"SessionHarvester initialized for profile: {profile_name}")

    async def attach(self, context: BrowserContext):
        try:
            self._context = context
            pages = context.pages
            if pages:
                try:
                    self._ua = await pages[0].evaluate("navigator.userAgent")
                except:
                    pass
            context.on("response", self._handle_response)
            logger.debug(f"Network listeners attached to context for {self.profile_name}")
        except Exception as e:
            logger.error(f"Failed to attach network listeners: {e}")
            raise

    async def _handle_response(self, response: Response):
        try:
            # Relaxed filter for testing: trigger on any 200 OK response
            if response.status == 200:
                await self.harvest()
        except Exception as e:
            logger.debug(f"Response handler skipped: {e}")

    async def harvest(self):
        try:
            if not self._context:
                return
            cookies = await self._context.cookies()
            tokens = self._extract_bot_tokens(cookies)
            current_state_hash = frozenset(tokens.keys())
            # For testing, we'll save even if the token set is empty to prove the DB write works
            self._save_to_db(cookies, self._ua, tokens)
            self._last_saved_state = current_state_hash
        except Exception as e:
            logger.error(f"Harvesting error for {self.profile_name}: {e}")

    def _extract_bot_tokens(self, cookies: List[Dict[str, Any]]) -> Dict[str, str]:
        extracted = {}
        for cookie in cookies:
            name = cookie.get("name")
            if name in self.TARGET_TOKENS:
                extracted[name] = cookie.get("value")
        return extracted

    def _save_to_db(self, cookies: List[Dict[str, Any]], ua: str, tokens: Dict[str, str]):
        try:
            metadata = {**tokens, "_proxy": self.proxy_url}
            self.db.save_session(self.profile_name, cookies, ua, metadata)
            logger.success(f"📦 [SESSION CACHED] Profile: {self.profile_name} | Tokens: {list(tokens.keys())}")
        except Exception as e:
            logger.error(f"Database persistence failed: {e}")
