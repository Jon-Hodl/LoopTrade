#!/usr/bin/env python3
import sys
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Use the venv Python
import subprocess
result = subprocess.run(
    [sys.executable, '-c', '''
import asyncio
import json
import os
from datetime import datetime

SCRIPT_DIR = "''' + SCRIPT_DIR + '''"
LOGS_FILE = os.path.join(SCRIPT_DIR, "looptrade_logs.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "looptrade_config.json")

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    try:
        logs = []
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                except:
                    logs = []
        logs.append(log_entry)
        while len(logs) > 500:
            logs.pop(0)
        with open(LOGS_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Log error: {e}")

async def main():
    add_log("[MIRROR] Starting mirror operation...")
    
    try:
        from lnmarkets_sdk.rest.v3.http.client import LNMClient
        from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
        from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder, UpdateTakeprofitParams
        add_log("[MIRROR] Imports successful")
    except Exception as e:
        add_log(f"[MIRROR] Import error: {e}")
        return
    
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        add_log(f"[MIRROR] Loaded config with {len(config.get('loops', []))} loops")
    except Exception as e:
        add_log(f"[MIRROR] Config error: {e}")
        return
    
    auth = APIAuthContext(
        key=config['api_key'], 
        secret=config['api_secret'], 
        passphrase=config['api_passphrase']
    )
    cfg = APIClientConfig(authentication=auth, network="mainnet")
    
    async with LNMClient(cfg) as client:
        add_log("[MIRROR] Connected to LN Markets")
        
        # Get loops
        loops = config.get('loops', [])
        add_log(f"[MIRROR] Processing {len(loops)} loops")
        
        # Get open orders
        try:
            open_orders = await client.futures.isolated.get_open_trades()
            add_log(f"[MIRROR] Found {len(open_orders)} open orders on LN Markets")
        except Exception as e:
            add_log(f"[MIRROR] Error fetching orders: {e}")
            return
        
        # Build loop price map
        loop_prices = {}
        for loop in loops:
            direction = loop.get('direction', 'long')
            if direction == 'short':
                price = round(loop['sell_price'] * 2) / 2
            else:
                price = round(loop['buy_price'] * 2) / 2
            loop_prices[price] = loop
        
        add_log(f"[MIRROR] Loop entry prices: {sorted(loop_prices.keys())}")
        
        # Cancel orders not in loops
        cancelled = 0
        for order in open_orders:
            try:
                order_price = round(order.price * 2) / 2
                if order_price not in loop_prices:
                    await client.futures.isolated.cancel_trade(order.id)
                    add_log(f"[MIRROR] Cancelled order @ ${order_price:,.0f}")
                    cancelled += 1
                    await asyncio.sleep(1)
            except Exception as e:
                add_log(f"[MIRROR] Error cancelling: {e}")
        
        # Place orders for loops without them
        placed = 0
        for price, loop in loop_prices.items():
            try:
                direction = loop.get('direction', 'long')
                qty = loop['quantity_usd']
                leverage = loop.get('leverage', 1)
                
                if direction == 'short':
                    entry_side = 'sell'
                    exit_price = loop['buy_price']
                else:
                    entry_side = 'buy'
                    exit_price = loop['sell_price']
                
                # Check if exists
                exists = any(round(o.price * 2) / 2 == price for o in open_orders)
                if exists:
                    add_log(f"[MIRROR] Order exists for '{loop.get('name')}' @ ${price:,.0f}")
                    continue
                
                # Place order
                sat = int((qty / price) * 1e8)
                params = FuturesOrder(
                    type='limit',
                    side=entry_side,
                    price=float(price),
                    leverage=float(leverage),
                    margin=sat
                )
                resp = await client.futures.isolated.new_trade(params)
                add_log(f"[MIRROR] Placed {entry_side} order for '{loop.get('name')}' @ ${price:,.0f}")
                
                # Set takeprofit
                try:
                    tp = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                    await client.futures.isolated.update_takeprofit(tp)
                    add_log(f"[MIRROR] Set takeprofit @ ${exit_price:,.0f}")
                except Exception as e:
                    add_log(f"[MIRROR] TP error: {e}")
                
                placed += 1
                await asyncio.sleep(2)
                
            except Exception as e:
                add_log(f"[MIRROR] Error placing order: {e}")
        
        add_log(f"[MIRROR] COMPLETE! Cancelled: {cancelled}, Placed: {placed}")

asyncio.run(main())
'''],
    capture_output=True,
    text=True,
    cwd=SCRIPT_DIR
)

if result.stderr:
    print("Errors:", result.stderr)
