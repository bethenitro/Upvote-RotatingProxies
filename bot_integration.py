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

def setup_order_logging(order_id: str):
    """Setup logging with order-specific log file."""
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Create order-specific log filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = logs_dir / f'order_{order_id}_{timestamp}.log'
    
    # Create a custom logger for this order
    order_logger = logging.getLogger(f'order_{order_id}')
    order_logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    for handler in order_logger.handlers[:]:
        order_logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    order_logger.addHandler(file_handler)
    order_logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    order_logger.propagate = False
    
    order_logger.info(f"Logging initialized for order {order_id}")
    order_logger.info(f"Log file: {log_filename}")
    
    return order_logger, str(log_filename)

# Setup basic logging for the integration script itself
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
    """Thread-safe progress tracker for monitoring bot process status."""
    
    def __init__(self, total_upvotes: int):
        self.total_upvotes = total_upvotes
        self.status = "pending"
        self.error_message = None
        self.start_time = None
        self.end_time = None
        self.process_task = None
        self.lock = threading.Lock()
    
    def start_process(self, task):
        """Mark the process as started and store the asyncio task."""
        with self.lock:
            self.status = "running"
            self.start_time = datetime.now()
            self.process_task = task
    
    def mark_completed(self, success: bool = True, error: str = None):
        """Mark the process as completed or failed."""
        with self.lock:
            self.end_time = datetime.now()
            if success:
                self.status = "completed"
            else:
                self.status = "failed"
                if error:
                    self.error_message = error
    
    def is_running(self) -> bool:
        """Check if the bot process is currently running."""
        with self.lock:
            if self.process_task is None:
                return False
            return not self.process_task.done()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status based on process state."""
        with self.lock:
            # If we have a task, check if it's still running
            if self.process_task is not None:
                if self.process_task.done():
                    # Process finished, check if it was successful or failed
                    if self.status == "running":
                        # Process finished but status wasn't updated manually
                        try:
                            # Check if task completed successfully or with exception
                            exception = self.process_task.exception()
                            if exception:
                                self.status = "failed"
                                self.error_message = str(exception)
                            else:
                                self.status = "completed"
                        except:
                            self.status = "completed"
                        self.end_time = datetime.now()
                else:
                    # Process is still running
                    self.status = "running"
            
            return {
                "status": self.status,
                "total_upvotes": self.total_upvotes,
                "error": self.error_message,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "is_running": self.is_running()
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
        
        # Setup order-specific logging
        self.logger, self.log_file = setup_order_logging(order_id)
        
        # Default configuration
        self.max_daily_per_account = 5
        self.min_gap_minutes = 30
        
        # Initialize progress tracker
        global _progress_tracker
        _progress_tracker = ProgressTracker(upvotes)
        
        self.logger.info(f"Initialized bot integration for order {order_id}")
        self.logger.info(f"Target URL: {reddit_url}")
        self.logger.info(f"Upvotes requested: {upvotes} at {upvotes_per_minute}/min")
    
    def validate_inputs(self) -> bool:
        """Validate the input parameters."""
        try:
            # Validate URL format
            if not self.reddit_url.startswith('https://') or 'reddit.com' not in self.reddit_url:
                self.logger.error(f"Invalid Reddit URL format: {self.reddit_url}")
                return False
            
            # Validate numeric parameters
            if self.upvotes <= 0:
                self.logger.error(f"Invalid upvotes count: {self.upvotes}")
                return False
                
            if self.upvotes_per_minute <= 0:
                self.logger.error(f"Invalid upvotes per minute: {self.upvotes_per_minute}")
                return False
            
            # Check if accounts file exists
            accounts_path = Path('profiles/accounts.json')
            if not accounts_path.exists():
                self.logger.error(f"Accounts file not found: {accounts_path.absolute()}")
                return False
            
            # Check if mobile proxies file exists and has valid proxies
            proxies_path = Path('mobile_proxies.json')
            if not proxies_path.exists():
                self.logger.error(f"Mobile proxies file not found: {proxies_path.absolute()}")
                return False
                
            try:
                with open(proxies_path, 'r') as f:
                    proxies = json.load(f)
                    if not proxies:
                        self.logger.error("No mobile proxies configured. The mobile_proxies.json file is empty. Please add proxy configurations.")
                        return False
                    
                    # Validate proxy structure
                    for i, proxy in enumerate(proxies):
                        if not all(key in proxy for key in ['server', 'username', 'password', 'rotation_url']):
                            self.logger.error(f"Invalid proxy configuration at index {i}: {proxy}. Missing required fields: server, username, password, rotation_url")
                            return False
                    
                    self.logger.info(f"Validated {len(proxies)} mobile proxy configurations")
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON in mobile_proxies.json: {str(e)}")
                return False
            except Exception as e:
                self.logger.error(f"Error reading mobile_proxies.json: {str(e)}")
                return False
            
            self.logger.info("Input validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Validation error: {str(e)}")
            return False
    
    def load_bot_accounts(self) -> tuple[dict, list]:
        """Load account data and determine available account IDs."""
        try:
            account_data = load_accounts('profiles/accounts.json')
            
            if not account_data:
                self.logger.error("No account data loaded from accounts.json")
                return {}, []
            
            # Extract account IDs (assuming they are numeric keys)
            account_ids = []
            for key in account_data.keys():
                try:
                    account_ids.append(int(key))
                except ValueError:
                    self.logger.warning(f"Skipping non-numeric account ID: {key}")
            
            account_ids.sort()
            self.logger.info(f"Loaded {len(account_ids)} accounts: {account_ids}")
            
            return account_data, account_ids
            
        except Exception as e:
            self.logger.error(f"Error loading accounts: {str(e)}")
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
            
            # Validate inputs
            if not self.validate_inputs():
                _progress_tracker.mark_completed(False, "Input validation failed")
                self.log_order_completion(False, "Input validation failed")
                return False
            
            # Load account data
            account_data, account_ids = self.load_bot_accounts()
            if not account_data or not account_ids:
                _progress_tracker.mark_completed(False, "Failed to load account data")
                self.log_order_completion(False, "Failed to load account data")
                return False
            
            # Check if we have enough accounts for the requested upvotes
            if len(account_ids) == 0:
                _progress_tracker.mark_completed(False, "No valid accounts available")
                self.log_order_completion(False, "No valid accounts available")
                return False
            
            self.logger.info(f"Starting bot execution with {len(account_ids)} accounts")
            
            # Create the bot task
            bot_task = asyncio.create_task(
                orchestrate_batches_low_data(
                    post_url=self.reddit_url,
                    account_ids=account_ids,
                    votes_per_min=self.upvotes_per_minute,
                    total_votes=self.upvotes,
                    account_data=account_data,
                    max_daily_per_account=self.max_daily_per_account,
                    min_gap_minutes=self.min_gap_minutes,
                    custom_logger=self.logger  # Pass the order-specific logger
                )
            )
            
            # Mark the process as started
            _progress_tracker.start_process(bot_task)
            
            # Wait for the bot to complete
            await bot_task
            
            # Mark as completed successfully
            _progress_tracker.mark_completed(True)
            self.log_order_completion(True)
            return True
            
        except Exception as e:
            error_msg = f"Bot execution failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            _progress_tracker.mark_completed(False, error_msg)
            self.log_order_completion(False, error_msg)
            return False
    
def get_progress_status() -> Dict[str, Any]:
    """Get the current progress status."""
    global _progress_tracker
    if _progress_tracker is None:
        return {
            "success": False,
            "status": "not_found",
            "error": "No active session"
        }
    
    status = _progress_tracker.get_status()
    return {
        "success": True,
        **status
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


def create_result_json(success: bool, status: str, error: str = None, order_id: str = None, **kwargs) -> Dict[str, Any]:
    """Create a standardized result JSON."""
    result = {
        "success": success,
        "status": status
    }
    
    # Add any additional fields from kwargs
    result.update(kwargs)
    
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
            error=final_status["error"],
            order_id=order_id,
            total_upvotes=final_status["total_upvotes"],
            start_time=final_status["start_time"],
            end_time=final_status["end_time"],
            is_running=final_status["is_running"]
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
