import asyncio
import signal
import sys
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Browser

from src.config.loader import load_profiles
from src.sniper.click_sniper import ClickSniper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("SniperOrchestrator")


class SniperOrchestrator:
    """
    Orchestrates multiple concurrent ticket sniping sessions, each with its own 
    browser instance and proxy to ensure unique TLS fingerprints and session isolation.
    """

    def __init__(self, config_path: str, event_id: str, max_sessions: int = 5):
        self.config_path = config_path
        self.event_id = event_id
        self.max_sessions = max_sessions
        
        # Load billing profiles from YAML
        self.profiles = load_profiles(self.config_path)
        
        # Enforce session limit vs available profiles
        if len(self.profiles) < self.max_sessions:
            raise ValueError(
                f"Insufficient profiles available. Required: {max_sessions}, "
                f"Found: {len(self.profiles)} in {config_path}."
            )

        # Extract db_path from the loaded config (assuming load_profiles returns config objects)
        # If load_profiles only returns profile lists, we assume the path is standardized 
        # or passed via a global config loader. Here we derive from project structure.
        self.db_path = "data/session_cache.db"
        
        # Track active browsers for clean termination on SIGINT/SIGTERM
        self.active_browsers: List[Browser] = []
        self._stop_requested = False

        # Register Signal Handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Registers system signals to ensure all Chromium processes are killed."""
        loop = asyncio.get_event_loop()
        
        # Use add_signal_handler for async-friendly signal management on Unix
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_exit_signal)
            except NotImplementedError:
                # Fallback for non-Unix platforms if necessary
                signal.signal(sig, self._handle_exit_sync)

    def _handle_exit_sync(self, signum, frame):
        """Synchronous fallback for signal handling."""
        logger.warning(f"Received signal {signum}. Forcing shutdown...")
        self._stop_requested = True
        # Since this is sync, we can't await browser.close() here.
        # We rely on the main loop seeing the flag or sys.exit(0) 
        # triggering the async with block cleanup.
        sys.exit(0)

    def _handle_exit_signal(self):
        """Async-compatible signal handler."""
        logger.warning("Interrupt signal received. Cleaning up active browsers...")
        self._stop_requested = True
        
        # Create a task to close all browsers immediately
        asyncio.create_task(self._cleanup_browsers())

    async def _cleanup_browsers(self):
        """Closes all tracked browser instances and exits."""
        while self.active_browsers:
            browser = self.active_browsers.pop()
            try:
                await browser.close()
                logger.info("Closed active browser instance.")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
        
        logger.info("All browsers terminated. Exiting.")
        sys.exit(0)

    async def run_all(self) -> List[Dict[str, Any]]:
        """
        Launches max_sessions concurrent sniper instances and collects their results.
        """
        results = []
        
        async with async_playwright() as pw:
            tasks = []
            
            # Only use the number of profiles requested by max_sessions
            target_profiles = self.profiles[:self.max_sessions]

            for profile in target_profiles:
                if self._stop_requested:
                    break

                try:
                    # IMPORTANT: Launch a SEPARATE browser instance per proxy.
                    # This ensures distinct TLS fingerprints and network stacks.
                    browser = await pw.chromium.launch(
                        headless=True, 
                        proxy={"server": profile.proxy_url} if profile.proxy_url else None
                    )
                    self.active_browsers.append(browser)
                    
                    # Instantiate the specific sniper for this profile/browser pair
                    sniper = ClickSniper(
                        browser=browser,
                        profile=profile,
                        event_id=self.event_id,
                        db_path=self.db_path
                    )
                    
                    # Wrap the sniper execution in a handler to capture results/errors
                    tasks.append(self._execute_sniper(sniper, profile.name))
                    
                except Exception as e:
                    logger.error(f"Failed to launch browser for profile {profile.name}: {e}")
                    results.append({
                        "profile": profile.name,
                        "success": False,
                        "error": f"Launch Error: {str(e)}"
                    })

            if not tasks:
                return results

            # Run all snipers concurrently
            # return_exceptions=True prevents one failed sniper from killing the whole orchestrator
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    logger.error(f"Unexpected task exception: {outcome}")
                elif outcome:
                    results.append(outcome)

            # Final cleanup of any remaining browsers
            await self._cleanup_browsers()

        return results

    async def _execute_sniper(self, sniper: ClickSniper, profile_name: str) -> Dict[str, Any]:
        """
        Executes a single sniper and formats the outcome.
        """
        try:
            success = await sniper.run()
            return {
                "profile": profile_name,
                "success": success,
                "error": None if success else "Sniper failed to secure ticket"
            }
        except Exception as e:
            logger.exception(f"Exception in sniper for profile {profile_name}")
            return {
                "profile": profile_name,
                "success": False,
                "error": str(e)
            }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.sniper.orchestrator <event_id>")
        sys.exit(1)

    event_id_arg = sys.argv[1]
    config_file = "config/profiles.yaml"
    
    try:
        orchestrator = SniperOrchestrator(
            config_path=config_file, 
            event_id=event_id_arg, 
            max_sessions=5
        )
        
        logger.info(f"Starting sniper orchestration for event {event_id_arg}...")
        final_results = asyncio.run(orchestrator.run_all())
        
        # Print summary report
        print("\n" + "="*50)
        print(f"SNIPER EXECUTION SUMMARY - Event: {event_id_arg}")
        print("="*50)
        
        success_count = 0
        for res in final_results:
            status = "✅ SUCCESS" if res["success"] else f"❌ FAILED ({res['error']})"
            print(f"Profile: {res['profile']:<20} | Status: {status}")
            if res["success"]:
                success_count += 1
        
        print("-"*50)
        print(f"Total Sessions: {len(final_results)} | Successful: {success_count}")
        print("="*50 + "\n")

    except Exception as e:
        logger.error(f"Orchestrator failed to start: {e}")
        sys.exit(1)
