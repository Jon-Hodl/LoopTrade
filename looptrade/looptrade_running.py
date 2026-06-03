
import asyncio
import json
import time
from datetime import datetime
from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder, UpdateTakeprofitParams

CONFIG_FILE = "looptrade_config.json"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

config = load_config()
API_KEY = config['api_key']
API_SECRET = config['api_secret']
API_PASSPHRASE = config['api_passphrase']
LEVERAGE = config['leverage']
CHECK_SECONDS = config['check_seconds']

# Global dict to track prices we're already trying to place orders at
# Key: price, Value: timestamp when added (for auto-expiry)
_orders_being_placed = {}
_ORDERS_TIMEOUT_SECONDS = 120  # Expire after 2 minutes if stuck

def is_price_being_placed(price):
    """Check if a price is currently being processed, with timeout cleanup"""
    global _orders_being_placed
    now = time.time()
    
    # Clean up expired entries
    expired = [p for p, t in _orders_being_placed.items() if now - t > _ORDERS_TIMEOUT_SECONDS]
    for p in expired:
        print(f"[TRACKER] Cleaning up expired price ${p:,.0f} (stuck for {int(now - _orders_being_placed[p])}s)")
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

# Rate limiter to prevent 429 errors
class RateLimiter:
    def __init__(self, min_delay=2.0):
        self.min_delay = min_delay  # Minimum seconds between API calls
        self.last_call_time = 0
        self.consecutive_errors = 0
    
    async def wait(self):
        """Wait if needed to respect rate limits"""
        elapsed = time.time() - self.last_call_time
        delay = self.min_delay + (self.consecutive_errors * 0.5)  # Increase delay after errors
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self.last_call_time = time.time()
    
    def report_error(self, is_rate_limit=False):
        """Track errors to increase backoff"""
        if is_rate_limit:
            self.consecutive_errors = min(self.consecutive_errors + 1, 10)  # Cap at 10
        else:
            self.consecutive_errors = max(self.consecutive_errors - 1, 0)
    
    def report_success(self):
        """Reduce backoff on success"""
        self.consecutive_errors = max(self.consecutive_errors - 1, 0)

# Shared rate limiter across all loops
_rate_limiter = RateLimiter(min_delay=5.0)  # 5 second minimum between calls

# Cache for ticker price (valid for 60 seconds - price doesn't change that fast)
_ticker_cache = {'price': None, 'timestamp': 0, 'lock': asyncio.Lock()}

# Cache for position data (shared across all loops)
_position_cache = {
    'open_trades': [],
    'running_trades': [],
    'closed_trades': [],
    'timestamp': 0,
    'lock': asyncio.Lock()
}

async def get_cached_positions(client):
    """Get all position data with caching - shared across all loops"""
    global _position_cache
    now = time.time()
    
    # Return cached data if fresh (within 30 seconds)
    if now - _position_cache['timestamp'] < 30:
        return (
            _position_cache['open_trades'],
            _position_cache['running_trades'],
            _position_cache['closed_trades']
        )
    
    # Use lock to prevent multiple simultaneous fetches
    async with _position_cache['lock']:
        # Double-check after acquiring lock
        if now - _position_cache['timestamp'] < 30:
            return (
                _position_cache['open_trades'],
                _position_cache['running_trades'],
                _position_cache['closed_trades']
            )
        
        # Fetch all three types with rate limiting
        await _rate_limiter.wait()
        try:
            open_trades = await client.futures.isolated.get_open_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch open trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        await _rate_limiter.wait()
        try:
            running_trades = await client.futures.isolated.get_running_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch running trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        await _rate_limiter.wait()
        try:
            closed_trades = await client.futures.isolated.get_closed_trades()
            _rate_limiter.report_success()
        except Exception as e:
            if '429' in str(e):
                _rate_limiter.report_error(is_rate_limit=True)
                print(f"[RATE LIMIT] Could not fetch closed trades, using cache")
                return (
                    _position_cache['open_trades'],
                    _position_cache['running_trades'],
                    _position_cache['closed_trades']
                )
            raise
        
        # Update cache
        _position_cache['open_trades'] = open_trades
        _position_cache['running_trades'] = running_trades
        _position_cache['closed_trades'] = closed_trades
        _position_cache['timestamp'] = time.time()
        
        return (open_trades, running_trades, closed_trades)

async def fetch_price_coingecko():
    """Fetch BTC price from CoinGecko (more reliable than LN Markets)"""
    import urllib.request
    import ssl
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
        data = json.loads(response.read().decode())
        return float(data['bitcoin']['usd'])

async def get_cached_ticker(client):
    """Get ticker price from CoinGecko (not LN Markets to avoid rate limits)"""
    global _ticker_cache
    now = time.time()
    
    # Return cached price if fresh (within 60 seconds)
    if now - _ticker_cache['timestamp'] < 60 and _ticker_cache['price'] is not None:
        return _ticker_cache['price']
    
    # Use lock to prevent multiple simultaneous fetches
    async with _ticker_cache['lock']:
        # Double-check after acquiring lock (another loop might have updated it)
        if now - _ticker_cache['timestamp'] < 60 and _ticker_cache['price'] is not None:
            return _ticker_cache['price']
        
        try:
            price = await fetch_price_coingecko()
            _ticker_cache['price'] = price
            _ticker_cache['timestamp'] = time.time()
            print(f"[PRICE] Updated BTC price from CoinGecko: ${price:,.2f}")
            return price
        except Exception as e:
            print(f"[PRICE] CoinGecko error: {e}")
            # If we have a cached price, use it even if old
            if _ticker_cache['price'] is not None:
                print(f"[PRICE] Using stale cached price: ${_ticker_cache['price']:,.2f}")
                return _ticker_cache['price']
            print(f"[PRICE] No cached price available, retrying in 10s...")
            await asyncio.sleep(10)
            return None

class Bot:
    def __init__(self):
        self.client = None
    
    async def __aenter__(self):
        auth = APIAuthContext(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
        cfg = APIClientConfig(authentication=auth, network="mainnet")
        self.client = LNMClient(cfg)
        await self.client.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.__aexit__(*args)
    
    async def sync_existing_orders(self, loops):
        """Scan LN Markets and match existing orders to loops"""
        print("[SYNC] Scanning LN Markets for existing orders...")
        
        await _rate_limiter.wait()
        try:
            open_trades = await self.client.futures.isolated.get_open_trades()
            running_trades = await self.client.futures.isolated.get_running_trades()
            _rate_limiter.report_success()
        except Exception as e:
            print(f"[SYNC] Error fetching orders: {e}")
            return {}  # Return empty mapping on error
        
        # Create mapping of price -> order ID for existing orders
        existing_orders = {}
        
        print(f"[SYNC] Found {len(open_trades)} open orders, {len(running_trades)} running positions")
        
        # Index open orders by price
        for order in open_trades:
            try:
                if not hasattr(order, 'price') or not hasattr(order, 'id'):
                    print(f"[SYNC] Warning: Skipping invalid order object: {order}")
                    continue
                price = round(order.price * 2) / 2  # Round to match loop prices
                side = getattr(order, 'side', 'unknown')
                existing_orders[price] = order.id
                print(f"[SYNC] Found open order: {order.id[:8]}... @ ${price:,.0f} side={side}")
            except Exception as e:
                print(f"[SYNC] Warning: Error processing order: {e}")
        
        # Index running positions by entry price
        for pos in running_trades:
            try:
                if not hasattr(pos, 'price') or not hasattr(pos, 'id'):
                    print(f"[SYNC] Warning: Skipping invalid position object: {pos}")
                    continue
                price = round(pos.price * 2) / 2
                side = getattr(pos, 'side', 'unknown')
                existing_orders[price] = pos.id
                print(f"[SYNC] Found running position: {pos.id[:8]}... @ ${price:,.0f} side={side}")
            except Exception as e:
                print(f"[SYNC] Warning: Error processing position: {e}")
        
        # Match loops to existing orders
        loop_pids = {}
        print(f"[SYNC] Looking for matches among {len(loops)} configured loops...")
        
        for i, loop in enumerate(loops):
            direction = loop.get('direction', 'long')
            buy_price = loop['buy_price']
            sell_price = loop['sell_price']
            
            if direction == 'short':
                entry_price = sell_price  # Short enters at sell price (higher)
            else:
                entry_price = buy_price   # Long enters at buy price (lower)
            
            price = round(entry_price * 2) / 2
            loop_id = loop.get('id', i)  # Use index as fallback ID
            
            print(f"[SYNC] Checking loop {i}: '{loop.get('name')}' direction={direction} entry=${price:,.0f} (buy=${buy_price:,.0f}, sell=${sell_price:,.0f})")
            
            if price in existing_orders:
                pid = existing_orders[price]
                loop_pids[loop_id] = pid
                print(f"[SYNC] ✓ MATCHED loop '{loop.get('name')}' (ID: {loop_id}) to order {pid[:8]}... @ ${price:,.0f}")
            else:
                print(f"[SYNC] ✗ No match for loop '{loop.get('name')}' @ ${price:,.0f}")
        
        print(f"[SYNC] Summary: Matched {len(loop_pids)} of {len(loops)} loops")
        return loop_pids
    
    async def run_loop(self, loop, existing_pid=None):
        name = loop['name']
        direction = loop.get('direction', 'long')
        buy = loop['buy_price']
        sell = loop['sell_price']
        qty = loop['quantity_usd']
        leverage = loop.get('leverage', 1)  # Per-loop leverage, default 1
        pid = existing_pid  # Use existing PID if provided from sync
        loops_completed = 0
        
        if pid:
            print(f"[{name}] Resuming with existing order: {pid[:8]}...")
        
        # Determine entry/exit based on direction
        if direction == 'short':
            # Short: Sell high first, buy back low
            entry_side = "sell"
            exit_side = "buy"
            entry_price = sell  # Entry = sell price (higher)
            exit_price = buy    # Exit = buy price (lower)
            entry_label = "SELL"
            exit_label = "BUY"
        else:
            # Long: Buy low first, sell high
            entry_side = "buy"
            exit_side = "sell"
            entry_price = buy   # Entry = buy price (lower)
            exit_price = sell   # Exit = sell price (higher)
            entry_label = "BUY"
            exit_label = "SELL"
        
        while True:
            try:
                if not pid:
                    # Get current BTC price (with caching and rate limiting)
                    current_price = await get_cached_ticker(self.client)
                    if not current_price:
                        print(f"[{name}] Waiting for price data...")
                        await asyncio.sleep(5)
                        continue
                    
                    # Round entry price to nearest 0.5 (LNMarkets requirement)
                    price = round(entry_price * 2) / 2
                    
                    # Check if entry price is valid for current market
                    if direction == 'long' and price >= current_price:
                        print(f"[{name}] SKIPPED: Buy price ${price:,.0f} is at or above current market price ${current_price:,.0f}")
                        print(f"[{name}] Waiting for price to drop below ${price:,.0f}...")
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    elif direction == 'short' and price <= current_price:
                        print(f"[{name}] SKIPPED: Sell price ${price:,.0f} is at or below current market price ${current_price:,.0f}")
                        print(f"[{name}] Waiting for price to rise above ${price:,.0f}...")
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    
                    # Check global tracker for orders being placed by other loops
                    if is_price_being_placed(price):
                        print(f"[{name}] SKIPPED: Another loop is already placing order at ${price:,.0f}")
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    
                    # CRITICAL FIX: Mark price as placing BEFORE slow API call to prevent race conditions
                    # This ensures no other loop can try to place at this price while we check LNMarkets
                    mark_price_placing(price)
                    
                    # Check for existing orders at same price on LNMarkets (with rate limiting)
                    await _rate_limiter.wait()
                    try:
                        existing_orders = await self.client.futures.isolated.get_open_trades()
                        _rate_limiter.report_success()
                    except Exception as e:
                        if '429' in str(e):
                            _rate_limiter.report_error(is_rate_limit=True)
                            print(f"[RATE LIMIT] Hit rate limit checking open orders, backing off...")
                            unmark_price_placing(price)  # Unmark on error
                            await asyncio.sleep(10)
                            continue
                        raise
                    
                    # Check if order already exists
                    order_exists = False
                    for order in existing_orders:
                        if abs(order.price - price) < 0.5:  # Within $0.50
                            order_exists = True
                            break
                    
                    if order_exists:
                        print(f"[{name}] SKIPPED: Order already exists at ${price:,.0f}")
                        unmark_price_placing(price)  # Unmark since we're not placing
                        await asyncio.sleep(CHECK_SECONDS)
                        continue
                    
                    # For isolated margin: pass QUANTITY to control position size directly
                    # LN Markets will calculate margin automatically based on leverage
                    params = FuturesOrder(type='limit', side=entry_side, price=float(price), leverage=float(leverage), quantity=float(qty))
                    
                    # Place order with rate limiting
                    await _rate_limiter.wait()
                    try:
                        resp = await self.client.futures.isolated.new_trade(params)
                        pid = resp.id if hasattr(resp, 'id') else str(resp)
                        print(f"[{name}] Placed {entry_label}: ${qty} position @ ${price:,.0f} (market: ${current_price:,.0f}) with {leverage}x leverage")
                        _rate_limiter.report_success()
                    except Exception as order_error:
                        error_msg = str(order_error)
                        # Check for rate limit errors
                        if '429' in error_msg or 'rate' in error_msg.lower():
                            _rate_limiter.report_error(is_rate_limit=True)
                            print(f"[{name}] RATE LIMIT: Too many requests, backing off...")
                            unmark_price_placing(price)
                            await asyncio.sleep(30)  # Wait 30s after rate limit
                            continue
                        # Check for specific LN Markets error types
                        elif 'insufficient' in error_msg.lower() or 'balance' in error_msg.lower():
                            print(f"[{name}] ERROR: Insufficient funds to place {entry_label} order @ ${price:,.0f}")
                            print(f"[{name}] Need: ${qty:,.0f} margin, Error: {error_msg}")
                        elif 'margin' in error_msg.lower():
                            print(f"[{name}] ERROR: Margin issue - {error_msg}")
                        elif 'price' in error_msg.lower():
                            print(f"[{name}] ERROR: Price invalid - {error_msg}")
                        elif 'leverage' in error_msg.lower():
                            print(f"[{name}] ERROR: Leverage issue - {error_msg}")
                        else:
                            print(f"[{name}] ERROR placing order: {error_msg}")
                        # Remove from tracking and wait before retry
                        unmark_price_placing(price)
                        await asyncio.sleep(CHECK_SECONDS * 2)  # Wait longer after error
                        continue
                    
                    # Remove from tracking set since order is now placed
                    unmark_price_placing(price)
                    
                    # Set takeprofit immediately after order is placed (with rate limiting)
                    await _rate_limiter.wait()
                    try:
                        tp_params = UpdateTakeprofitParams(id=resp.id, value=float(exit_price))
                        await self.client.futures.isolated.update_takeprofit(tp_params)
                        print(f"[{name}] Takeprofit set @ ${exit_price:,.0f}")
                        _rate_limiter.report_success()
                    except Exception as tp_error:
                        if '429' in str(tp_error):
                            _rate_limiter.report_error(is_rate_limit=True)
                            print(f"[{name}] RATE LIMIT: Could not set takeprofit due to rate limiting")
                        else:
                            print(f"[{name}] Warning: Could not set takeprofit: {tp_error}")
                
                else:
                    # Check position status using shared cache (all loops share same data)
                    open_trades_list, running_trades_list, closed_trades_list = await get_cached_positions(self.client)
                    
                    # Safely extract IDs with error handling
                    try:
                        open_orders = {p.id for p in open_trades_list if hasattr(p, 'id')}
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading open orders: {e}")
                        open_orders = set()
                    
                    try:
                        running_positions = {p.id for p in running_trades_list if hasattr(p, 'id')}
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading running positions: {e}")
                        running_positions = set()
                    
                    try:
                        closed_ids = {t.id for t in closed_trades_list if hasattr(t, 'id')}
                    except Exception as e:
                        print(f"[{name}] Warning: Error reading closed trades: {e}")
                        closed_ids = set()
                    
                    if pid in open_orders:
                        # Entry order still pending, do nothing
                        pass
                    elif pid in running_positions:
                        # Entry filled, position running with takeprofit set
                        print(f"[{name}] {entry_label} filled! Position running, takeprofit @ ${exit_price:,.0f}")
                    elif pid in closed_ids:
                        # Position closed (takeprofit executed)
                        loops_completed += 1
                        print(f"[{name}] {exit_label} filled (takeprofit)! LOOP #{loops_completed} complete")
                        # Remove from tracking so we can place new entry order
                        unmark_price_placing(entry_price)
                        pid = None  # Reset to place new entry order
                    else:
                        # Order ID not found anywhere — may have been cancelled
                        print(f"[{name}] Order {pid[:8]} not found, resetting...")
                        unmark_price_placing(entry_price)
                        pid = None
                
                await asyncio.sleep(CHECK_SECONDS)
            except Exception as e:
                error_msg = str(e)
                # Log specific error types for better debugging
                if 'insufficient' in error_msg.lower() or 'balance' in error_msg.lower():
                    print(f"[{name}] ERROR: Insufficient balance - {error_msg}")
                elif 'margin' in error_msg.lower():
                    print(f"[{name}] ERROR: Margin calculation issue - {error_msg}")
                elif 'unauthorized' in error_msg.lower() or 'auth' in error_msg.lower():
                    print(f"[{name}] ERROR: API authentication failed - check your API keys")
                elif 'rate' in error_msg.lower() or 'limit' in error_msg.lower():
                    print(f"[{name}] ERROR: Rate limited by LN Markets - backing off...")
                    await asyncio.sleep(60)  # Wait longer for rate limits
                elif 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                    print(f"[{name}] ERROR: Connection issue - {error_msg}")
                else:
                    print(f"[{name}] Error: {error_msg}")
                await asyncio.sleep(10)
    
    async def run(self):
        print("Starting bot... monitoring for new loops")
        active_loops = {}  # Map of loop ID to task
        started_prices = set()  # Track which prices we've already started loops for
        synced = False  # Track if we've done initial sync
        
        while True:
            try:
                # Reload config to check for new loops
                config = load_config()
                loops = config.get('loops', [])
                
                # Sync existing orders on first run
                if not synced and loops:
                    existing_pids = await self.sync_existing_orders(loops)
                    synced = True
                else:
                    existing_pids = {}
                
                # Start tasks for any new loops
                for i, loop in enumerate(loops):
                    if loop.get('enabled', True):
                        loop_id = loop.get('id', i)
                        buy_price = round(loop['buy_price'] * 2) / 2
                        
                        # Use combined key of loop_id + price to track unique entries
                        unique_key = f"{loop_id}_{buy_price}"
                        
                        # Skip if already started
                        if unique_key in started_prices:
                            continue
                        
                        # Skip if this loop was matched to an existing order during sync
                        # (another loop task is already tracking it)
                        if loop_id in existing_pids:
                            print(f"Skipping loop '{loop.get('name')}' - already synced to existing order")
                            started_prices.add(unique_key)  # Mark as started so we don't try again
                            continue
                        
                        print(f"Starting new loop: {loop.get('name', f'Loop {i}')} @ ${buy_price:,.0f}")
                        # Pass existing PID if we found one during sync
                        existing_pid = existing_pids.get(loop_id)
                        task = asyncio.create_task(self.run_loop(loop, existing_pid))
                        active_loops[unique_key] = task
                        started_prices.add(unique_key)
                
                # Wait a bit before checking again
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Error checking for new loops: {e}")
                await asyncio.sleep(5)

async def main():
    async with Bot() as bot:
        await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
