import asyncio
import argparse
import logging
import signal
import sys
from typing import List, Dict, Any

# Import project components
from src.recon.profiler import Profiler
from src.browser.manager import BrowserManager as BrowserCollector
from src.sniper.orchestrator import SniperOrchestrator

# Configure logging at the entry point
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("concert_helper.main")

def signal_handler(signum, frame):
    """
    Top-level safety net for SIGINT.
    Logs the interruption and allows the specific mode's 
    handler (e.g., Orchestrator) to perform detailed cleanup.
    """
    logger.info("Interrupted. Cleaning up...")
    # Propagate the signal or exit
    sys.exit(0)

async def handle_recon(args):
    """
    MODE: recon
    Performs DOM scanning on a sandbox URL and saves the schema for a specific event.
    """
    logger.info(f"Starting recon for event {args.event_id} at {args.url}...")
    try:
        profiler = Profiler(sandbox_url=args.url)
        # Profiler.scan() is expected to perform the scan and save to site_schemas table
        await profiler.scan(event_id=args.event_id)
        print(f"Recon complete. Schema saved for event {args.event_id}.")
    except Exception as e:
        logger.exception(f"Recon failed: {e}")
        sys.exit(1)

async def handle_hitl(args):
    """
    MODE: hitl
    Launches a browser session for Human-In-The-Loop authentication and session collection.
    """
    logger.info(f"Starting HITL session collection for profile: {args.profile}...")
    try:
        collector = BrowserCollector()
        # BrowserCollector.collect() launches browser and saves result to active_sessions table
        await collector.collect(profile_name=args.profile)
        print(f"Session saved for profile {args.profile}.")
    except Exception as e:
        logger.exception(f"HITL collection failed: {e}")
        sys.exit(1)

async def handle_snipe(args):
    """
    MODE: snipe
    Orchestrates concurrent ticket sniping sessions.
    """
    logger.info(f"Starting snipe operation for event {args.event_id} with {args.sessions} sessions...")
    try:
        config_path = "config/profiles.yaml"
        orchestrator = SniperOrchestrator(
            config_path=config_path, 
            event_id=args.event_id, 
            max_sessions=args.sessions
        )
        
        results = await orchestrator.run_all()
        
        # Print a formatted results table
        print("\n" + "="*60)
        print(f"{'PROFILE':<25} | {'STATUS':<15} | {'ERROR'}")
        print("-" * 60)
        
        success_count = 0
        for res in results:
            status = "✅ SUCCESS" if res["success"] else "❌ FAILED"
            error = res["error"] if res["error"] else ""
            print(f"{res['profile']:<25} | {status:<15} | {error}")
            if res["success"]:
                success_count += 1
        
        print("-" * 60)
        print(f"Total: {len(results)} | Successful: {success_count}")
        print("="*60 + "\n")
        
    except Exception as e:
        logger.exception(f"Snipe operation failed: {e}")
        sys.exit(1)

def main():
    # Register top-level SIGINT handler
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
        description="concert_helper: Unified CLI for concert ticket automation."
    )
    
    # Required Mode Argument
    parser.add_argument(
        "--mode", 
        required=True, 
        choices=["recon", "hitl", "snipe"],
        help="Operation mode: 'recon' (DOM scan), 'hitl' (session collection), or 'snipe' (execution)."
    )
    
    # Mode-specific arguments
    parser.add_argument("--event-id", help="The unique identifier for the concert event.")
    parser.add_argument("--url", help="The sandbox URL to scan (required for recon mode).")
    parser.add_argument("--profile", help="The billing profile name to use (required for hitl mode).")
    parser.add_argument("--sessions", type=int, default=3, help="Number of concurrent sessions for snipe mode (default: 3).")

    args = parser.parse_args()

    # Validation and Dispatch
    if args.mode == "recon":
        if not args.event_id or not args.url:
            parser.error("--mode recon requires --event-id and --url")
        asyncio.run(handle_recon(args))
        
    elif args.mode == "hitl":
        if not args.profile:
            parser.error("--mode hitl requires --profile")
        asyncio.run(handle_hitl(args))
        
    elif args.mode == "snipe":
        if not args.event_id:
            parser.error("--mode snipe requires --event-id")
        asyncio.run(handle_snipe(args))
    
    else:
        # This block is technically unreachable due to choices=[] in add_argument, 
        # but kept for structural completeness.
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
