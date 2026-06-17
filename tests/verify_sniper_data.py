import asyncio
import json
from loguru import logger
from src.sniper.api_client import SniperAPIClient
from src.utils.database import DatabaseManager

# Real Target Data
TARGET_EVENT_ID = "8946d178"
API_ENDPOINT = f"https://weekendplanent.kktix.cc/api/v1/events/{TARGET_EVENT_ID}"
TEST_PROFILE = "clc_surgical_test"

async def verify_real_data():
    logger.info(f"🎯 Starting Final Verification for profile: {TEST_PROFILE}")
    
    try:
        # 1. Initialize Sniper with the surgically harvested session
        sniper = SniperAPIClient(profile_name=TEST_PROFILE)
        await sniper.initialize()
        
        logger.info(f"Requesting real-time data from: {API_ENDPOINT}")
        
        # 2. Execute the request
        result = await sniper._request_with_backoff("GET", API_ENDPOINT)
        
        if result:
            logger.success("Successfully retrieved real data from KKTIX API!")
            
            # 3. Extract and print the specific data the user requested
            # We look for common KKTIX JSON keys like 'title', 'start_date', 'ticket_types'
            event_title = result.get("title", "Unknown Title")
            start_date = result.get("start_date") or result.get("date", "Unknown Date")
            
            # Ticket availability is usually in a list of ticket types
            tickets = result.get("ticket_types", [])
            ticket_summary = []
            
            if tickets:
                for t in tickets:
                    name = t.get("name", "Unknown Category")
                    # Look for available count or status
                    avail = t.get("available", t.get("quantity", "Unknown"))
                    ticket_summary.append(f"- {name}: {avail}")
            else:
                # Fallback if ticket_types isn't the key
                ticket_summary.append("No specific ticket availability data found in this endpoint.")

            print("\n" + "="*40)
            print(f"✅ VERIFICATION DATA")
            print(f"Event: {event_title}")
            print(f"Date:  {start_date}")
            print(f"Seats/Availability:\n" + "\n".join(ticket_summary))
            print("="*40 + "\n")
            
        else:
            logger.error("Failed to retrieve data. The session might have expired or the endpoint is incorrect.")
            
        await sniper.close()

    except Exception as e:
        logger.exception(f"Verification crashed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_real_data())
