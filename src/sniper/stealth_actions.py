import asyncio
import random
from playwright.async_api import Page

async def human_pause(min_ms: int = 80, max_ms: int = 220) -> None:
    """
    Sleeps for a random duration between min_ms and max_ms milliseconds.
    Used to mimic human hesitation and prevent pattern detection.
    """
    duration = random.uniform(min_ms, max_ms) / 1000.0
    await asyncio.sleep(duration)

async def wait_for_active(page: Page, selector: str, timeout_ms: int = 30000) -> None:
    """
    Waits for the selector to be present in the DOM and not have the 'disabled' attribute.
    Appends the :not([disabled]) pseudo-class to the provided selector.
    """
    active_selector = f"{selector}:not([disabled])"
    await page.wait_for_selector(active_selector, state="visible", timeout=timeout_ms)

async def human_click(page: Page, selector: str) -> None:
    """
    Performs a human-like click on an element.
    1. Ensures the element is active and visible.
    2. Introduces a natural pause before interaction.
    3. Clicks at a random coordinate within the first 30% of the element's area 
       to avoid clicking the exact center (a common bot signature).
    """
    # Ensure element is ready
    await wait_for_active(page, selector)
    
    # Natural hesitation
    await human_pause(60, 180)
    
    # Calculate random offset within the element's bounding box
    element = page.locator(selector)
    box = await element.bounding_box()
    
    if box:
        # Calculate a random offset within the top-left 30% of the element
        # This avoids the exact center (0.5, 0.5) which is a high-signal bot pattern
        offset_x = random.uniform(0, box["width"] * 0.3)
        offset_y = random.uniform(0, box["height"] * 0.3)
        
        # Click using relative position
        await element.click(position={"x": offset_x, "y": offset_y})
    else:
        # Fallback to standard click if bounding box is unavailable
        await element.click()

async def human_type(page: Page, selector: str, value: str) -> None:
    """
    Performs human-like text input into a field.
    1. Focuses the field via human_click.
    2. Introduces a pause before typing.
    3. Types each character with a randomized delay to simulate human keystrokes.
    """
    # Focus the field first
    await human_click(page, selector)
    
    # Hesitation before starting to type
    await human_pause(80, 200)
    
    # Randomize typing speed per character
    typing_delay = random.randint(45, 115)
    
    # use press_sequentially (modern replacement for page.type) 
    # to simulate actual keyboard events
    await page.locator(selector).press_sequentially(value, delay=typing_delay)
