#!/usr/bin/env python3
"""
LoopTrade - Minimal
Multiple loops. Each has buy price, sell price. Loops forever.
"""

import asyncio
from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder

# ============================================================================
# CONFIG - EDIT THESE
# ============================================================================

API_KEY = "Yv1WQFz0Jd/zwH9FI8Jm6hC+CF6itdXMI4Rmt713X94="
API_SECRET = "qWim7AW12AQf5kthd6pB/1u8xtoQwns7s94fFqaqiguM6PEVYMvvfg0EmOGs1Ft11EyrnHE2a9eJh3xsnKMWwg=="
API_PASSPHRASE = "Hal Finn"

# Define your loops here
# Format: (name, buy_price, sell_price, quantity_usd)
LOOPS = [
    ("Loop1", 65000, 68000, 50),
    ("Loop2", 68000, 72000, 50),
    ("Loop3", 72000, 76000, 50),
]

LEVERAGE = 1
CHECK_SECONDS = 30

# ============================================================================
# BOT
# ============================================================================

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
    
    async def price(self):
        t = await self.client.futures.get_ticker()
        return float(t.last_price)
    
    async def place(self, name, side, price, qty_usd):
        sat = int((qty_usd / price) * 1e8)
        params = FuturesOrder(type='limit', side=side, price=float(price), quantity=sat, leverage=float(LEVERAGE))
        resp = await self.client.futures.isolated.new_trade(params)
        pid = resp.id if hasattr(resp, 'id') else str(resp)
        print(f"[{name}] Placed {side.upper()}: {sat/1e8:.8f} BTC @ ${price:,.0f}")
        return pid
    
    async def filled(self, pid):
        if not pid:
            return False
        running = {p.id for p in await self.client.futures.isolated.get_running_trades()}
        open_o = {p.id for p in await self.client.futures.isolated.get_open_trades()}
        return pid not in running and pid not in open_o
    
    async def run_loop(self, name, buy, sell, qty):
        side = "buy"
        pid = None
        loops = 0
        
        while True:
            try:
                # Place order if none
                if not pid:
                    price = buy if side == "buy" else sell
                    pid = await self.place(name, side, price, qty)
                    await asyncio.sleep(2)
                
                # Check if filled
                elif await self.filled(pid):
                    print(f"[{name}] {side.upper()} filled!")
                    
                    if side == "buy":
                        side = "sell"
                    else:
                        side = "buy"
                        loops += 1
                        print(f"[{name}] LOOP #{loops} complete")
                    
                    pid = None
                
                await asyncio.sleep(CHECK_SECONDS)
                
            except Exception as e:
                print(f"[{name}] Error: {e}")
                await asyncio.sleep(10)
    
    async def run(self):
        print(f"BTC: ${await self.price():,.0f}")
        print(f"Running {len(LOOPS)} loops...")
        print("Ctrl+C to stop\n")
        
        tasks = [self.run_loop(*loop) for loop in LOOPS]
        await asyncio.gather(*tasks)

# ============================================================================
# MAIN
# ============================================================================

async def main():
    if not API_KEY or len(API_KEY) < 10:
        print("Error: Set API_KEY, API_SECRET, API_PASSPHRASE")
        return
    
    async with Bot() as bot:
        await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")