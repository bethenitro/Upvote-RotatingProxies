#!/usr/bin/env python3
"""
Bot Integration Script for Upvote-RotatingProxies

This script serves as an integration layer between the backend and the upvote bot.
It accepts order parameters and runs the bot using the low data version.

Supports both JSON input (for backend integration) and command line arguments.

JSON Input (from stdin):
{
    "order_id": "12345",
    "reddit_url": "https://reddit.com/...",
    "upvotes": 10,
    "upvotes_per_minute": 2
}

Command Line Usage:
    python bot_integration.py --order-id "12345" --reddit-url "https://reddit.com/..." --upvotes 10 --upvotes-per-minute 2
"""

import asyncio
import argparse
import json
import logging
import sys
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Import the bot's functions
from target import orchestrate_batches_low_data, load_accounts

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_integration.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ProgressTracker:
    """Thread-safe progress tracker for monitoring upvote progress."""
    
    def __init__(self, total_upvotes: int):
        self.total_upvotes = total_upvotes
        self.upvotes_done = 0
        self.status = "pending"
        self.error_message = None
        self.lock = threading.Lock()
    
    def update_progress(self, upvotes_done: int, status: str = None, error: str = None):
        """Update the progress in a thread-safe manner."""
        with self.lock:
            self.upvotes_done = upvotes_done
            if status:
                self.status = status
            if error:
                self.error_message = error
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status in a thread-safe manner."""
        with self.lock:
            progress_percentage = round((self.upvotes_done / self.total_upvotes) * 100, 2) if self.total_upvotes > 0 else 0
            return {
                "upvotes_done": self.upvotes_done,
                "total_upvotes": self.total_upvotes,
                "progress_percentage": progress_percentage,
                "status": self.status,
                "error": self.error_message
            }


# Global progress tracker
_progress_tracker: Optional[ProgressTracker] = None


class BotIntegration:
    """Integration class for running the upvote bot with order parameters."""
    
    def __init__(self, order_id: str, reddit_url: str, upvotes: int, upvotes_per_minute: int):
        """
        Initialize the bot integration.
        
        Args:
            order_id: Unique identifier for the order
            reddit_url: URL of the Reddit post to upvote
            upvotes: Total number of upvotes to perform
            upvotes_per_minute: Rate of upvotes per minute
        """
        self.order_id = order_id
        self.reddit_url = reddit_url
        self.upvotes = upvotes
        self.upvotes_per_minute = upvotes_per_minute
        
        # Default configuration
        self.max_daily_per_account = 5
        self.min_gap_minutes = 30
        
        # Initialize progress tracker
        global _progress_tracker
        _progress_tracker = ProgressTracker(upvotes)
        
        logger.info(f"Initialized bot integration for order {order_id}")
        logger.info(f"Target URL: {reddit_url}")
        logger.info(f"Upvotes requested: {upvotes} at {upvotes_per_minute}/min")
    
    def validate_inputs(self) -> bool:
        """Validate the input parameters."""
        try:
            # Validate URL format
            if not self.reddit_url.startswith('https://') or 'reddit.com' not in self.reddit_url:
                logger.error(f"Invalid Reddit URL format: {self.reddit_url}")
                return False
            
            # Validate numeric parameters
            if self.upvotes <= 0:
                logger.error(f"Invalid upvotes count: {self.upvotes}")
                return False
                
            if self.upvotes_per_minute <= 0:
                logger.error(f"Invalid upvotes per minute: {self.upvotes_per_minute}")
                return False
            
            # Check if accounts file exists
            accounts_path = Path('profiles/accounts.json')
            if not accounts_path.exists():
                logger.error(f"Accounts file not found: {accounts_path.absolute()}")
                return False
            
            logger.info("Input validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False
    
    def load_bot_accounts(self) -> tuple[dict, list]:
        """Load account data and determine available account IDs."""
        try:
            account_data = load_accounts('profiles/accounts.json')
            
            if not account_data:
                logger.error("No account data loaded from accounts.json")
                return {}, []
            
            # Extract account IDs (assuming they are numeric keys)
            account_ids = []
            for key in account_data.keys():
                try:
                    account_ids.append(int(key))
                except ValueError:
                    logger.warning(f"Skipping non-numeric account ID: {key}")
            
            account_ids.sort()
            logger.info(f"Loaded {len(account_ids)} accounts: {account_ids}")
            
            return account_data, account_ids
            
        except Exception as e:
            logger.error(f"Error loading accounts: {str(e)}")
            return {}, []
    
    def log_order_start(self):
        """Log the start of the order processing."""
        logger.info("=" * 60)
        logger.info(f"STARTING ORDER PROCESSING")
        logger.info(f"Order ID: {self.order_id}")
        logger.info(f"Reddit URL: {self.reddit_url}")
        logger.info(f"Total upvotes: {self.upvotes}")
        logger.info(f"Rate: {self.upvotes_per_minute} upvotes/minute")
        logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
    
    def log_order_completion(self, success: bool, error_msg: str = None):
        """Log the completion of the order processing."""
        logger.info("=" * 60)
        if success:
            logger.info(f"ORDER COMPLETED SUCCESSFULLY")
        else:
            logger.error(f"ORDER FAILED")
            if error_msg:
                logger.error(f"Error: {error_msg}")
        
        logger.info(f"Order ID: {self.order_id}")
        logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
    
    async def run_bot(self) -> bool:
        """
        Run the upvote bot with the specified parameters.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.log_order_start()
            
            # Update status to running
            global _progress_tracker
            _progress_tracker.update_progress(0, "running")
            
            # Validate inputs
            if not self.validate_inputs():
                _progress_tracker.update_progress(0, "failed", "Input validation failed")
                self.log_order_completion(False, "Input validation failed")
                return False
            
            # Load account data
            account_data, account_ids = self.load_bot_accounts()
            if not account_data or not account_ids:
                _progress_tracker.update_progress(0, "failed", "Failed to load account data")
                self.log_order_completion(False, "Failed to load account data")
                return False
            
            # Check if we have enough accounts for the requested upvotes
            if len(account_ids) == 0:
                _progress_tracker.update_progress(0, "failed", "No valid accounts available")
                self.log_order_completion(False, "No valid accounts available")
                return False
            
            logger.info(f"Starting bot execution with {len(account_ids)} accounts")
            
            # Run the low data version of the bot with progress tracking
            await self.run_bot_with_progress_tracking(account_data, account_ids)
            
            # Check final status
            final_status = _progress_tracker.get_status()
            if final_status["status"] == "failed":
                self.log_order_completion(False, final_status.get("error"))
                return False
            else:
                _progress_tracker.update_progress(final_status["upvotes_done"], "completed")
                self.log_order_completion(True)
                return True
            
        except Exception as e:
            error_msg = f"Bot execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            _progress_tracker.update_progress(_progress_tracker.upvotes_done, "failed", error_msg)
            self.log_order_completion(False, error_msg)
            return False
    
    async def run_bot_with_progress_tracking(self, account_data: dict, account_ids: list):
        """Run the bot with progress tracking - exact copy of orchestrate_batches_low_data."""
        from target import load_state, save_state, load_mobile_proxies, rotate_proxy, upvote_post_low_data
        import random
        from datetime import timedelta
        
        global _progress_tracker
        
        # EXACT COPY OF orchestrate_batches_low_data with progress tracking added
        state = load_state()
        last_upvote = {acc: datetime.fromisoformat(state.get(str(acc), {}).get('last_upvote', '1970-01-01T00:00:00')) for acc in account_ids}
        daily_count = {acc: state.get(str(acc), {}).get('daily_count', 0) for acc in account_ids}
        votes_done = 0
        min_gap = timedelta(minutes=self.min_gap_minutes)

        # Load mobile proxies
        mobile_proxies = load_mobile_proxies()
        if not mobile_proxies:
            error_msg = "No mobile proxies available. Exiting."
            logger.error(error_msg)
            _progress_tracker.update_progress(votes_done, "failed", error_msg)
            return

        # Log initial account states
        logger.debug("Initial account states:")
        for acc in account_ids:
            last = last_upvote[acc].strftime('%Y-%m-%d %H:%M') if last_upvote[acc] != datetime.min else "Never"
            logger.debug(f"Account {acc:2}: Last upvote: {last}, Daily uses: {daily_count[acc]}/{self.max_daily_per_account}")

        logger.info(f"Starting orchestrated batches: {self.upvotes} votes at {self.upvotes_per_minute}/min")
        
        while votes_done < self.upvotes:
            batch_size = min(self.upvotes_per_minute, self.upvotes - votes_done)
            now = datetime.now()
            
            # Find eligible accounts
            eligible = [
                acc for acc in account_ids
                if (now - last_upvote[acc] >= min_gap) 
                and (daily_count[acc] < self.max_daily_per_account)
            ]
            
            # Log eligibility check
            logger.debug(f"Eligibility check at {now.strftime('%H:%M:%S')}:")
            for acc in account_ids:
                gap_ok = now - last_upvote[acc] >= min_gap
                daily_ok = daily_count[acc] < self.max_daily_per_account
                status = "ELIGIBLE" if gap_ok and daily_ok else "INELIGIBLE"
                last = last_upvote[acc].strftime('%H:%M') if last_upvote[acc] != datetime.min else "Never"
                logger.debug(f"Account {acc:2}: {status} (Last: {last}, Uses: {daily_count[acc]}/{self.max_daily_per_account}, Gap OK: {gap_ok})")

            if not eligible:
                logger.warning("No eligible accounts available, waiting...")
                await asyncio.sleep(60)
                continue
                
            # Select batch
            batch = random.sample(eligible, min(batch_size, len(eligible)))
            logger.info(f"Selected batch of {len(batch)} accounts: {batch}")
            
            # Log batch details
            logger.debug("Batch account details:")
            for acc in batch:
                last = last_upvote[acc].strftime('%H:%M') if last_upvote[acc] != datetime.min else "Never"
                logger.debug(f"Account {acc:2}: Last upvote: {last}, Daily uses: {daily_count[acc]}/{self.max_daily_per_account}")

            # Process batch
            logger.info(f"Starting upvote batch processing")
            tasks = []
            for acc in batch:
                try:
                    account = account_data[str(acc)]
                    # Rotate proxy before each upvote to get a fresh IP
                    proxy_config = rotate_proxy()
                    logger.debug(f"Using proxy configuration for account {acc}: {proxy_config['server']}")
                    tasks.append(
                        upvote_post_low_data(
                            acc,
                            self.reddit_url,
                            proxy_config=proxy_config
                        )
                    )
                except KeyError:
                    logger.error(f"Account {acc} not found in account data")

            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results with detailed logging
            success_count = 0
            for acc, result in zip(batch, results):
                current_time = datetime.now()
                if isinstance(result, Exception):
                    logger.error(f"Account {acc:2} | ERROR: {str(result)}")
                else:
                    success_count += 1
                    last_upvote[acc] = current_time
                    daily_count[acc] += 1
                    votes_done += 1
                    next_available = (current_time + min_gap).strftime('%H:%M')
                    logger.info(
                        f"Account {acc:2} | SUCCESS | "
                        f"Daily uses: {daily_count[acc]}/{self.max_daily_per_account} | "
                        f"Next available: {next_available}"
                    )
                    
                    # ADDED: Update progress tracker
                    _progress_tracker.update_progress(votes_done, "running")

            logger.info(f"Batch completed: {success_count} successes, {len(batch)-success_count} failures")
            logger.info(f"Total progress: {votes_done}/{self.upvotes} ({votes_done/self.upvotes:.1%})")

            # Save the updated state to the file after each batch
            state = {
                str(acc): {
                    'last_upvote': last_upvote[acc].isoformat(),
                    'daily_count': daily_count[acc]
                } for acc in account_ids
            }
            save_state(state)

            # Wait for next batch
            elapsed = (datetime.now() - now).total_seconds()
            if elapsed < 60:
                wait_time = 60 - elapsed
                logger.debug(f"Sleeping {wait_time:.1f}s until next batch")
                await asyncio.sleep(wait_time)

        logger.info("All batches completed successfully")
        # ADDED: Mark as completed
        _progress_tracker.update_progress(votes_done, "completed")


def get_progress_status() -> Dict[str, Any]:
    """Get the current progress status."""
    global _progress_tracker
    if _progress_tracker is None:
        return {
            "success": False,
            "status": "not_found",
            "error": "No active session",
            "upvotes_done": 0,
            "progress_percentage": 0
        }
    
    status = _progress_tracker.get_status()
    return {
        "success": True,
        "status": status["status"],
        "upvotes_done": status["upvotes_done"],
        "total_upvotes": status["total_upvotes"],
        "progress_percentage": status["progress_percentage"],
        "error": status["error"]
    }


def parse_json_input() -> Optional[Dict[str, Any]]:
    """Parse JSON input from stdin."""
    try:
        input_data = sys.stdin.read().strip()
        if not input_data:
            return None
        return json.loads(input_data)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error reading input: {str(e)}")
        return None


def create_result_json(success: bool, status: str, upvotes_done: int = 0, 
                      total_upvotes: int = 0, progress_percentage: float = 0.0,
                      error: str = None, order_id: str = None) -> Dict[str, Any]:
    """Create a standardized result JSON."""
    result = {
        "success": success,
        "status": status,
        "upvotes_done": upvotes_done,
        "total_upvotes": total_upvotes,
        "progress_percentage": progress_percentage
    }
    
    if error:
        result["error"] = error
    if order_id:
        result["order_id"] = order_id
        
    return result


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Bot Integration Script for Upvote-RotatingProxies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Command line mode
    python bot_integration.py --order-id "12345" --reddit-url "https://www.reddit.com/r/test/comments/abc123/post/" --upvotes 10 --upvotes-per-minute 2
    
    # JSON mode (reads from stdin)
    echo '{"order_id":"12345","reddit_url":"https://reddit.com/...","upvotes":10,"upvotes_per_minute":2}' | python bot_integration.py --json-mode
        """
    )
    
    parser.add_argument(
        '--order-id', '-o',
        type=str,
        required=False,
        help='Unique identifier for the order'
    )
    
    parser.add_argument(
        '--reddit-url', '-u',
        type=str,
        required=False,
        help='URL of the Reddit post to upvote'
    )
    
    parser.add_argument(
        '--upvotes', '-v',
        type=int,
        required=False,
        help='Total number of upvotes to perform'
    )
    
    parser.add_argument(
        '--upvotes-per-minute', '-r',
        type=int,
        required=False,
        help='Rate of upvotes per minute'
    )
    
    parser.add_argument(
        '--json-mode',
        action='store_true',
        help='Read parameters from JSON input via stdin'
    )
    
    return parser.parse_args()


async def main():
    """Main function to run the bot integration."""
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Determine if we're in JSON mode or command line mode
        if args.json_mode or (not args.order_id and not args.reddit_url):
            # JSON mode - read from stdin
            json_data = parse_json_input()
            
            if not json_data:
                result = create_result_json(
                    success=False,
                    status="failed",
                    error="No input data provided or invalid JSON"
                )
                print(json.dumps(result))
                sys.exit(1)
            
            # Extract parameters from JSON
            try:
                order_id = json_data["order_id"]
                reddit_url = json_data["reddit_url"]
                upvotes = int(json_data["upvotes"])
                upvotes_per_minute = int(json_data["upvotes_per_minute"])
            except (KeyError, ValueError) as e:
                result = create_result_json(
                    success=False,
                    status="failed",
                    error=f"Invalid JSON parameters: {str(e)}"
                )
                print(json.dumps(result))
                sys.exit(1)
                
        else:
            # Command line mode
            if not all([args.order_id, args.reddit_url, args.upvotes, args.upvotes_per_minute]):
                result = create_result_json(
                    success=False,
                    status="failed",
                    error="Missing required command line arguments"
                )
                print(json.dumps(result))
                sys.exit(1)
                
            order_id = args.order_id
            reddit_url = args.reddit_url
            upvotes = args.upvotes
            upvotes_per_minute = args.upvotes_per_minute
        
        # Create bot integration instance
        bot_integration = BotIntegration(
            order_id=order_id,
            reddit_url=reddit_url,
            upvotes=upvotes,
            upvotes_per_minute=upvotes_per_minute
        )
        
        # Run the bot
        success = await bot_integration.run_bot()
        
        # Get final status
        final_status = get_progress_status()
        
        # Create result
        result = create_result_json(
            success=success,
            status=final_status["status"],
            upvotes_done=final_status["upvotes_done"],
            total_upvotes=final_status["total_upvotes"],
            progress_percentage=final_status["progress_percentage"],
            error=final_status["error"],
            order_id=order_id
        )
        
        # Output result as JSON
        print(json.dumps(result))
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        result = create_result_json(
            success=False,
            status="failed",
            error="Process interrupted by user"
        )
        print(json.dumps(result))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        result = create_result_json(
            success=False,
            status="failed",
            error=f"Unexpected error: {str(e)}"
        )
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    # Ensure we're in the correct directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Run the main function
    asyncio.run(main())
