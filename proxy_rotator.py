import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("reddit_stealth.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# File path for mobile proxies
PROXY_FILE_PATH = "mobile_proxies.json"

# Store the last rotation time for each proxy
last_rotation_times: Dict[str, datetime] = {}

def load_mobile_proxies() -> List[Dict[str, Any]]:
    """
    Load mobile proxy configurations from the JSON file.
    
    Returns:
        List[Dict[str, Any]]: List of proxy configurations
    """
    try:
        with open(PROXY_FILE_PATH, "r") as f:
            proxies = json.load(f)
            # Validate proxy structure
            for proxy in proxies:
                if not all(key in proxy for key in ["server", "username", "password", "rotation_url"]):
                    logger.error(f"Invalid proxy configuration: {proxy}")
                    return []
            logger.info(f"Successfully loaded {len(proxies)} proxies from {PROXY_FILE_PATH}")
            return proxies
    except Exception as e:
        logger.error(f"Failed to load mobile proxies: {str(e)}")
        return []

def can_rotate_proxy(proxy: Dict[str, Any]) -> bool:
    """
    Check if a proxy can be rotated (at least 1 minute since last rotation).
    
    Args:
        proxy: Proxy configuration dictionary
        
    Returns:
        bool: True if the proxy can be rotated, False otherwise
    """
    server_key = proxy["server"]
    if server_key not in last_rotation_times:
        return True
        
    # Check if at least 60 seconds have passed since the last rotation
    time_since_last_rotation = datetime.now() - last_rotation_times[server_key]
    return time_since_last_rotation >= timedelta(minutes=1)

def attempt_proxy_rotation(proxy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Attempt to rotate a single proxy's IP address.
    Returns None if rotation fails or if proxy is on cooldown.
    """
    if not can_rotate_proxy(proxy):
        logger.debug(f"Skipping rotation for {proxy['server']}: Too soon since last rotation")
        return None

    try:
        logger.info(f"Attempting to rotate IP for proxy: {proxy['server']}")
        response = requests.get(proxy["rotation_url"], timeout=30)
        response_data = response.json()
        
        if response_data.get("success") == 1:
            # Update last rotation time on success
            last_rotation_times[proxy["server"]] = datetime.now()
            logger.info(f"Successfully rotated IP for {proxy['server']}: {response_data.get('message')}")
            return {
                "server": proxy["server"],
                "username": proxy["username"],
                "password": proxy["password"]
            }
        else:
            error_msg = response_data.get("error", "Unknown error")
            logger.warning(f"Failed to rotate proxy {proxy['server']}: {error_msg}")
            # If we get the cooldown message, update the last rotation time
            if "rotate IP every 1 minutes" in error_msg:
                last_rotation_times[proxy["server"]] = datetime.now()
            return None
            
    except Exception as e:
        logger.error(f"Error rotating proxy {proxy['server']}: {str(e)}")
        return None

def rotate_proxy() -> Dict[str, Any]:
    """
    Rotate proxies until a successful rotation is achieved.
    Never returns a proxy that hasn't been successfully rotated.
    """
    proxies = load_mobile_proxies()
    if not proxies:
        logger.error("No proxies available for rotation")
        raise ValueError("No proxies available for rotation")
        
    max_attempts = 10
    attempt = 0
    
    while attempt < max_attempts:
        logger.debug(f"Proxy rotation attempt {attempt + 1}/{max_attempts}")
        
        # Check for any proxy that can be rotated
        rotatable_proxies = [p for p in proxies if can_rotate_proxy(p)]
        
        # If no proxy can be rotated right now, wait for the cooldown period
        if not rotatable_proxies:
            wait_time = 60  # Wait 60 seconds (1 minute) before trying again
            logger.info(f"All proxies are on cooldown. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
            attempt += 1
            continue
            
        # Try to rotate each eligible proxy
        for proxy in rotatable_proxies:
            rotated_proxy = attempt_proxy_rotation(proxy)
            if rotated_proxy:  # Only return if rotation was successful
                logger.info(f"Successfully obtained rotated proxy: {proxy['server']}")
                return rotated_proxy
            # If rotation failed due to cooldown, wait for the full cooldown period
            if proxy["server"] in last_rotation_times:
                wait_time = 60  # Wait 60 seconds (1 minute)
                logger.info(f"Proxy {proxy['server']} is on cooldown. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                
        attempt += 1
                
    # If we've exhausted all attempts
    logger.error("Failed to rotate any proxy after multiple attempts")
    raise RuntimeError("Failed to rotate any proxy after multiple attempts")
