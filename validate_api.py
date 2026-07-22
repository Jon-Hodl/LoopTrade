#!/usr/bin/env python3
"""
API Key Validator for LoopTrade
Checks if LNMarkets API credentials are valid before starting trading
"""

import asyncio
import json
import sys
from datetime import datetime

CONFIG_FILE = "looptrade_config.json"
STATUS_FILE = "api_status.json"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_status(status):
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

async def validate_api_keys():
    """Test API authentication with LNMarkets"""
    from lnmarkets_sdk.rest.v3.http.client import LNMClient
    from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
    
    config = load_config()
    
    api_key = config.get('api_key', '')
    api_secret = config.get('api_secret', '')
    passphrase = config.get('api_passphrase', '')
    testnet = config.get('testnet', False)
    
    # Check if keys are placeholder
    if not api_key or len(api_key) < 10 or 'YOUR_' in api_key:
        return {
            'valid': False,
            'error': 'API keys not configured (placeholder values detected)',
            'timestamp': datetime.now().isoformat()
        }
    
    # Mask keys for display
    masked_key = api_key[:8] + '...' + api_key[-8:] if len(api_key) > 16 else '***'
    
    try:
        auth = APIAuthContext(key=api_key, secret=api_secret, passphrase=passphrase)
        network = "testnet" if testnet else "mainnet"
        cfg = APIClientConfig(authentication=auth, network=network)
        
        async with LNMClient(cfg) as client:
            # Try to fetch positions (lightweight API call that requires auth)
            positions = await client.futures.isolated.get_open_trades()
            
            return {
                'valid': True,
                'network': network,
                'positions_count': len(positions) if positions else 0,
                'api_key_masked': masked_key,
                'timestamp': datetime.now().isoformat()
            }
            
    except Exception as e:
        error_msg = str(e)
        
        # Common error patterns
        if 'authentication' in error_msg.lower() or 'unauthorized' in error_msg.lower():
            error_msg = 'Authentication failed - check API keys, secret, and passphrase'
        elif 'forbidden' in error_msg.lower():
            error_msg = 'Access forbidden - check API key scopes (need positions + user)'
        elif 'network' in error_msg.lower():
            error_msg = 'Network error - check internet connection'
        
        return {
            'valid': False,
            'error': error_msg,
            'api_key_masked': masked_key,
            'timestamp': datetime.now().isoformat()
        }

def print_status(status):
    """Print human-readable status"""
    print("\n" + "="*60)
    print("🔐 LoopTrade API Key Validation")
    print("="*60)
    
    if status['valid']:
        print(f"✅ API Status: VALID")
        print(f"   Network: {status.get('network', 'unknown')}")
        print(f"   Open Positions: {status.get('positions_count', 0)}")
        print(f"   API Key: {status.get('api_key_masked', '***')}")
        print(f"   Last Check: {status.get('timestamp', 'unknown')}")
        print("\n🚀 Ready to trade!")
    else:
        print(f"❌ API Status: INVALID")
        print(f"   Error: {status.get('error', 'Unknown error')}")
        print(f"   API Key: {status.get('api_key_masked', '***')}")
        print(f"   Last Check: {status.get('timestamp', 'unknown')}")
        print("\n⚠️  Please fix API keys in looptrade_config.json")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        status = asyncio.run(validate_api_keys())
        save_status(status)
        print_status(status)
        
        # Exit with error code if invalid (for automation)
        sys.exit(0 if status['valid'] else 1)
        
    except KeyboardInterrupt:
        print("\n\nValidation cancelled.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Validation error: {e}")
        sys.exit(1)
