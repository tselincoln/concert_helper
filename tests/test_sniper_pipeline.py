import asyncio
import time
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import async_playwright

# Assuming these exist in the project as per architectural context
try:
    from src.sniper.click_sniper import ClickSniper
except ImportError:
    # For test environment if not installed via uv yet
    class ClickSniper:
        def __init__(self, *args, **kwargs): pass
        async def run(self): return False
        async def human_type(self, selector, text): pass

try:
    from src.browser.lean_context import LeanContextFactory
except ImportError:
    class LeanContextFactory:
        @staticmethod
        async def create_context(browser, proxy=None):
            return await browser.new_context()

@pytest.fixture
async def pw_context():
    """Fixture to provide playwright and a browser instance."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        yield pw, browser
        await browser.close()

@pytest.mark.asyncio
async def test_resource_blocking(pw_context):
    """TEST 1: Validates that no images are requested in a lean context."""
    pw, browser = pw_context
    # Using the specified LeanContextFactory
    context = await LeanContextFactory.create_context(browser)
    page = await context.new_page()
    
    request_count = 0
    async def handle_request(request):
        nonlocal request_count
        if request.resource_type == "image":
            request_count += 1

    # Setup listener before navigation
    page.on("request", handle_request)
    
    await page.goto("https://example.com")
    
    # Small sleep to ensure all async requests have a chance to fire
    await asyncio.sleep(0.5)
    
    assert request_count == 0, f"Expected 0 image requests, but found {request_count}"
    await context.close()

@pytest.mark.asyncio
async def test_human_type_timing(pw_context):
    """TEST 2: Validates that human_type applies jitter and fills value correctly."""
    pw, browser = pw_context
    page = await browser.new_page()
    
    # Mock a simple HTML page
    await page.set_content('<input id="test-input" type="text">')
    
    # We assume ClickSniper or a similar utility handles the human_type logic
    profile = MagicMock() 
    sniper = ClickSniper(browser=browser, profile=profile, event_id="test", db_path=":memory:")
    
    start_time = time.perf_counter()
    await sniper.human_type("#test-input", "HelloWorld")
    end_time = time.perf_counter()
    
    # Verify value
    val = await page.input_value("#test-input")
    assert val == "HelloWorld"
    
    # Verify jitter timing (requirement: > 0.4s)
    elapsed = end_time - start_time
    assert elapsed >= 0.4, f"Human typing too fast ({elapsed:.2f}s). Jitter might be missing."
    await page.close()

@pytest.mark.asyncio
async def test_sniper_timeout_handling(tmp_path):
    """TEST 3: Validates error handling on element timeout and DB logging."""
    # Use a temporary file for the SQLite database to avoid side effects
    db_file = tmp_path / "test_session.db"
    db_path = str(db_file)
    
    # Setup empty schema in SQLite for testing logs
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE checkout_logs (event_id TEXT, status TEXT)")
        await db.commit()

    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        profile = MagicMock()
        profile.name = "test_profile"
        
        # Mock schema pointing to a non-existent selector
        mock_schema = {"selectors": {"button": "#never-exists"}}
        
        # Pass mock_schema into sniper (assuming it accepts or we inject it)
        sniper = ClickSniper(browser=browser, profile=profile, event_id="event_123", db_path=db_path)
        # We manually inject the schema for this test instance
        sniper.schema = mock_schema 

        # Execute run
        result = await sniper.run()
        
        assert result is False, "Sniper should return False on timeout"

        # Verify DB contents
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT status FROM checkout_logs WHERE event_id='event_123'")
            row = await cursor.fetchone()
            assert row is not None, "No log entry found in database"
            assert row[0] == "TIMEOUT", f"Expected status TIMEOUT, got {row[0]}"

        await browser.close()

@pytest.mark.asyncio
async def test_orchestrator_browser_isolation():
    """TEST 4: Validates that each scale session gets its own unique browser instance."""
    from src.sniper.orchestrator import SniperOrchestrator
    from unittest.mock import AsyncMock

    # Mock Profiles
    profile_a = MagicMock(name="ProfileA")
    profile_a.proxy_url = "http://a:p@h:80"
    profile_a.name = "Alpha"

    profile_b = MagicMock(name="ProfileB")
    profile_b.proxy_url = "http://b:p@h:80"
    profile_b.name = "Beta"

    # Mock the load_profiles function to return our two profiles
    with patch("src.config.loader.load_profiles", return_value=[profile_a, profile_b]):
        orchestrator = SniperOrchestrator(config_path="fake_path", event_id="test_evt", max_sessions=2)

        # We need to mock the Playwright object and its chromium.launch method
        mock_pw = AsyncMock()
        mock_browser = AsyncMock()
        mock_pw.chromium.launch.return_value = mock_browser

        # Use patch to inject our mock playwright into the orchestrator's context
        with patch("playwright.async_api.async_playwright", return_value=mock_pw):
            # We also need to make sure ClickSniper doesn't crash during test (it's called inside)
            # Since we are testing isolation, we just mock the task logic
            with patch("src.sniper.orchestrator.ClickSniper.run", return_value=True):
                await orchestrator.run_all()

        # Verify launch was called exactly once per profile (total 2)
        assert mock_pw.chromium.launch.call_count == 2
        
        # High-level verification of proxy separation
        calls = mock_pw.chromium.launch.call_args_list
        assert calls[0].kwargs['proxy'] == {"server": "http://a:p@h:80"}
        assert calls[1].kwargs['proxy'] == {"server": "http://b:p@h:80"}
