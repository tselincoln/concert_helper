import asyncio
from src.recon.profiler import SiteProfiler
from src.utils.database import DatabaseManager

async def main():
    # Initialize DB and Profiler
    db = DatabaseManager("data/session_cache.db")
    profiler = SiteProfiler(db)
    
    target = "https://kktix.com/"
    sandbox = "https://kktix.com/" # Using homepage as safe sandbox for initial test
    
    print(f"Testing profiler on: {target}...")
    try:
        schema = await profiler.profile_site(target, sandbox)
        print("\n--- Generated Schema Mapping ---")
        import json
        print(json.dumps(schema, indent=4))
    except Exception as e:
        print(f"Error during profiling: {e}")

if __name__ == "__main__":
    asyncio.run(main())
