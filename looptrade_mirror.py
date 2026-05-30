
import sys
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add virtual environment to path if it exists  
venv_paths = [
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.13', 'site-packages'),
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.12', 'site-packages'),
    os.path.join(SCRIPT_DIR, 'venv', 'lib', 'python3.11', 'site-packages'),
]
for venv_path in venv_paths:
    if os.path.exists(venv_path) and venv_path not in sys.path:
        sys.path.insert(0, venv_path)
        break

import asyncio
import json
import time
from datetime import datetime

LOGS_FILE = os.path.join(SCRIPT_DIR, "looptrade_logs.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "looptrade_config.json")

# Global dict to track prices we're already trying to place orders at
_orders_being_placed = {}
_ORDERS_TIMEOUT_SECONDS = 120

def is_price_being_placed(price):
    """Check if a price is currently being processed, with timeout cleanup"""
    global _orders_being_placed
    now = time.time()
    expired = [p for p, t in _orders_being_placed.items() if now - t > _ORDERS_TIMEOUT_SECONDS]
    for p in expired:
        del _orders_being_placed[p]
    return price in _orders_being_placed

def mark_price_placing(price):
    """Mark a price as being processed"""
    global _orders_being_placed
    _orders_being_placed[price] = time.time()

def unmark_price_placing(price):
    """Remove price from tracking"""
    global _orders_being_placed
    if price in _orders_being_placed:
        del _orders_being_placed[price]

def add_log(message):
    """Add a log entry to the shared log file"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    try:
        # Read existing logs
        logs = []
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                except:
                    logs = []
        
        # Add new log
        logs.append(log_entry)
        
        # Keep only last 500
        while len(logs) > 500:
            logs.pop(0)
        
        # Write back
        with open(LOGS_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Log error: {e}")

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

config = load_config()
API_KEY = config['api_key']
API_SECRET = config['api_secret']
API_PASSPHRASE = config['api_passphrase']

async def mirror():
    from lnmarkets_sdk.rest.v3.http.client import LNMClient
    from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
    from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder, UpdateTakeprofitParams, CancelTradeParams
    
    auth = APIAuthContext(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
    cfg = APIClientConfig(authentication=auth, network="mainnet")
    
    async with LNMClient(cfg) as client:
        add_log("[MIRROR] Starting full mirror operation...")
        
        # Get all loops from config
        loops = config.get('loops', [])
        add_log(f"[MIRROR] Found {len(loops)} loops in LoopTrade")
        
        # Build map of loop entry prices to expected margin
        loop_data = {}  # price -> (qty, leverage, expected_margin)
        for loop in loops:
            direction = loop.get('direction', 'long')
            if direction == 'short':
                entry_price = round(loop['sell_price'] * 2) / 2
            else:
                entry_price = round(loop['buy_price'] * 2) / 2
            qty = loop['quantity_usd']
            leverage = loop.get('leverage', 1)
            # Calculate expected margin (satoshis)
            expected_margin = round((qty / entry_price) * 1e8 / leverage)
            loop_data[entry_price] = (qty, leverage, expected_margin)
        
        # Get all open orders from LN Markets
        try:
            open_orders = await client.futures.isolated.get_open_trades()
            add_log(f"[MIRROR] Found {len(open_orders)} open orders on LN Markets")
        except Exception as e:
            add_log(f"[MIRROR] Error fetching orders: {e}")
            return
        
        # Cancel orders that don't match any loop OR have wrong margin/quantity
        cancelled = 0
        add_log(f"[MIRROR] Loop prices: {sorted(loop_data.keys())}")
        for order in open_orders:
            try:
                order_price = round(order.price * 2) / 2
                order_margin = order.margin  # in satoshis
                order_quantity = order.quantity  # position size in USD
                
                should_cancel = False
                cancel_reason = ""
                
                if order_price not in loop_data:
                    should_cancel = True
                    cancel_reason = "not in loops"
                else:
                    expected_qty = loop_data[order_price][0]
                    expected_margin = loop_data[order_price][2]
                    
                    # Check if quantity is correct (must match exactly)
                    if order_quantity != expected_qty:
                        should_cancel = True
                        cancel_reason = f"wrong quantity (got ${order_quantity}, expected ${expected_qty})"
                    # Also check margin (within 5% tolerance)
                    elif abs(order_margin - expected_margin) / expected_margin * 100 > 5:
                        should_cancel = True
                        cancel_reason = f"wrong margin (got {order_margin}, expected {expected_margin})"
                
                add_log(f"[MIRROR] Checking order @ ${order_price:,.0f} qty=${order_quantity} margin={order_margin} - cancel: {should_cancel}")
                
                if should_cancel:
                    add_log(f"[MIRROR] Cancelling order @ ${order_price:,.0f} ({cancel_reason})")
                    cancel_params = CancelTradeParams(id=str(order.id))
                    await client.futures.isolated.cancel(cancel_params)
                    add_log(f"[MIRROR] Cancelled order {str(order.id)[:8]}... @ ${order_price:,.0f}")
                    # Unmark price so bot can place new order
                    unmark_price_placing(order_price)
                    cancelled += 1
                    await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                add_log(f"[MIRROR] Error cancelling order: {e}")
        
        # Place orders for loops that don't have one
        placed = 0
        for loop in loops:
            try:
                direction = loop.get('direction', 'long')
                buy_price = loop['buy_price']
                sell_price = loop['sell_price']
                qty = loop['quantity_usd']
                leverage = loop.get('leverage', 1)
                
                if direction == 'short':
                    entry_price = round(sell_price * 2) / 2
                    entry_side = 'sell'
                    exit_price = buy_price
                else:
                    entry_price = round(buy_price * 2) / 2
                    entry_side = 'buy'
                    exit_price = sell_price
                
                # Check if order already exists at this price
                existing = False
                for order in open_orders:
                    order_price = round(order.price * 2) / 2
                    if abs(order_price - entry_price) < 0.5:
                        existing = True
                        break
                
                if not existing:
                    # CRITICAL FIX: Check and mark price as placing to prevent race conditions
                    if is_price_being_placed(entry_price):
                        add_log(f"[MIRROR] SKIPPED: Price ${entry_price:,.0f} is being placed by another loop")
                        continue
                    
                    mark_price_placing(entry_price)
                    
                    # Place the order with quantity (not margin) to control position size
                    params = FuturesOrder(
                        type='limit', 
                        side=entry_side, 
                        price=float(entry_price), 
                        leverage=float(leverage), 
                        quantity=float(qty)
                    )
                    resp = await client.futures.isolated.new_trade(params)
                    add_log(f"[MIRROR] Placed {entry_side} order for '{loop.get('name')}' @ ${entry_price:,.0f} qty=${qty}")
                    unmark_price_placing(entry_price)  # Unmark after successful placement
                    
                    # Set takeprofit
                    try:
                        tp_params = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                        await client.futures.isolated.update_takeprofit(tp_params)
                        add_log(f"[MIRROR] Set takeprofit @ ${exit_price:,.0f}")
                    except Exception as e:
                        add_log(f"[MIRROR] Warning: Could not set takeprofit: {e}")
                    
                    placed += 1
                    await asyncio.sleep(2)  # Rate limiting
                else:
                    add_log(f"[MIRROR] Order exists for '{loop.get('name')}' @ ${entry_price:,.0f}")
                    
            except Exception as e:
                add_log(f"[MIRROR] Error placing order: {e}")
                unmark_price_placing(entry_price)  # Unmark on error
        
        add_log(f"[MIRROR] Complete! Cancelled: {cancelled}, Placed: {placed}")

asyncio.run(mirror())
