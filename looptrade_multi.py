#!/usr/bin/env python3
"""
LoopTrade Multi - Run Multiple Independent Loops
Each loop has its own buy price, sell price, and optional stoploss/takeprofit.
Loops run independently - when one fills, it flips and waits for the other side.
"""

import asyncio
import sqlite3
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from datetime import datetime

from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder

# ============================================================================
# USER CONFIGURATION - EDIT THESE VALUES
# ============================================================================

@dataclass
class LoopConfig:
    """Configuration for a single loop"""
    name: str              # Name/label for this loop (e.g., "Loop 1", "Conservative", etc.)
    buy_price: float       # Price to buy at
    sell_price: float      # Price to sell at  
    quantity_usd: float    # USD amount per trade
    stoploss: Optional[float] = None      # Optional stoploss price
    takeprofit: Optional[float] = None    # Optional take profit price
    leverage: int = 1      # Leverage for this loop
    enabled: bool = True   # Enable/disable this loop


# ============================================================================
# DEFINE YOUR LOOPS HERE
# ============================================================================

MY_LOOPS: List[LoopConfig] = [
    # Example loops - edit or replace these with your own
    LoopConfig(
        name="Loop 1 - Lower Range",
        buy_price=65000.0,
        sell_price=68000.0,
        quantity_usd=50.0,
    ),
    LoopConfig(
        name="Loop 2 - Mid Range", 
        buy_price=68000.0,
        sell_price=72000.0,
        quantity_usd=50.0,
        stoploss=62000.0,  # Optional protection
    ),
    LoopConfig(
        name="Loop 3 - Upper Range",
        buy_price=72000.0,
        sell_price=76000.0,
        quantity_usd=50.0,
    ),
    # Add more loops as needed!
    # LoopConfig(name="Loop 4", buy_price=..., sell_price=..., quantity_usd=...),
]


@dataclass
class GlobalConfig:
    """Global settings for the bot"""
    # LNMarkets API Credentials
    API_KEY: str = ""
    API_SECRET: str = ""
    API_PASSPHRASE: str = ""
    
    # Bot Settings
    CHECK_INTERVAL_SECONDS: int = 30
    NETWORK: str = "mainnet"
    
    # Loops to run (uses MY_LOOPS above)
    LOOPS: List[LoopConfig] = None
    
    def __post_init__(self):
        if self.LOOPS is None:
            self.LOOPS = MY_LOOPS


# ============================================================================
# DATABASE FOR PERSISTENCE
# ============================================================================

class LoopDatabase:
    def __init__(self, db_path: str = "looptrade_multi.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS loop_states (
                    loop_name TEXT PRIMARY KEY,
                    current_side TEXT NOT NULL,  -- 'buy' or 'sell'
                    position_id TEXT,
                    loops_completed INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loop_name TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity_sat INTEGER NOT NULL,
                    position_id TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def get_loop_state(self, loop_name: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM loop_states WHERE loop_name = ?", (loop_name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def save_loop_state(self, loop_name: str, side: str, position_id: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO loop_states (loop_name, current_side, position_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(loop_name) DO UPDATE SET
                   current_side = excluded.current_side,
                   position_id = excluded.position_id,
                   updated_at = CURRENT_TIMESTAMP""",
                (loop_name, side, position_id)
            )
            conn.commit()
    
    def increment_loop_count(self, loop_name: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE loop_states 
                   SET loops_completed = loops_completed + 1,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE loop_name = ?""",
                (loop_name,)
            )
            conn.commit()
    
    def record_trade(self, loop_name: str, side: str, price: float, quantity_sat: int, position_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO trades (loop_name, side, price, quantity_sat, position_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (loop_name, side, price, quantity_sat, position_id)
            )
            conn.commit()
    
    def get_all_stats(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT loop_name, current_side, loops_completed FROM loop_states"
            )
            return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# SINGLE LOOP HANDLER
# ============================================================================

class SingleLoop:
    def __init__(self, config: LoopConfig, global_config: GlobalConfig, db: LoopDatabase, client: LNMClient, logger: logging.Logger):
        self.config = config
        self.global_config = global_config
        self.db = db
        self.client = client
        self.logger = logger
        
        self.loop_name = config.name
        self.current_side: str = "buy"
        self.position_id: Optional[str] = None
        self.running = True
        
    async def initialize(self):
        """Initialize loop state from database or determine starting side"""
        state = self.db.get_loop_state(self.loop_name)
        
        if state:
            # Restore from database
            self.current_side = state['current_side']
            self.position_id = state['position_id']
            self.logger.info(f"[{self.loop_name}] Restored state: {self.current_side.upper()} (loops: {state['loops_completed']})")
        else:
            # New loop - determine starting side based on current price
            current_price = await self._get_current_price()
            
            if current_price <= self.config.buy_price:
                self.current_side = "buy"
            elif current_price >= self.config.sell_price:
                self.current_side = "sell"
            else:
                # Price is between - wait for it to come down to buy
                self.current_side = "buy"
            
            self.db.save_loop_state(self.loop_name, self.current_side, None)
            self.logger.info(f"[{self.loop_name}] New loop starting with {self.current_side.upper()} @ current price ${current_price:,.2f}")
    
    async def _get_current_price(self) -> float:
        """Get current BTC price"""
        ticker = await self.client.futures.get_ticker()
        return float(ticker.get('lastPrice', 0))
    
    def _calculate_quantity(self, price: float) -> int:
        """Calculate satoshi quantity from USD amount"""
        btc_amount = self.config.quantity_usd / price
        return int(btc_amount * 1e8)
    
    async def _place_order(self, side: str, price: float) -> Optional[str]:
        """Place a limit order"""
        try:
            quantity = self._calculate_quantity(price)
            
            order_params = {
                'type': 'limit',
                'side': side,
                'price': float(price),
                'quantity': quantity,
                'leverage': float(self.config.leverage)
            }
            
            # Add optional protection orders
            if self.config.stoploss:
                order_params['stoploss'] = float(self.config.stoploss)
            if self.config.takeprofit:
                order_params['takeprofit'] = float(self.config.takeprofit)
            
            params = FuturesOrder(**order_params)
            response = await self.client.futures.isolated.new_trade(params)
            
            position_id = response.id if hasattr(response, 'id') else str(response)
            
            self.logger.info(f"[{self.loop_name}] ✅ Placed {side.upper()}: {quantity/1e8:.8f} BTC @ ${price:,.2f}")
            
            # Record in database
            self.db.record_trade(self.loop_name, side, price, quantity, position_id)
            
            return position_id
            
        except Exception as e:
            self.logger.error(f"[{self.loop_name}] ❌ Failed to place {side} order: {e}")
            return None
    
    async def _check_position_filled(self) -> bool:
        """Check if current position has filled"""
        if not self.position_id:
            return False
        
        try:
            # Check running positions
            running = await self.client.futures.isolated.get_running_trades()
            running_ids = {p.id for p in running}
            
            if self.position_id in running_ids:
                return False  # Still waiting
            
            # Check closed trades
            closed = await self.client.futures.isolated.get_closed_trades()
            closed_ids = {p.id for p in closed}
            
            if self.position_id in closed_ids:
                return True  # Filled!
            
            # Check open orders
            open_orders = await self.client.futures.isolated.get_open_trades()
            open_ids = {p.id for p in open_orders}
            
            return self.position_id not in open_ids  # Not in any list = filled/cancelled
            
        except Exception as e:
            self.logger.error(f"[{self.loop_name}] Error checking position: {e}")
            return False
    
    async def run_once(self) -> bool:
        """Run one iteration of the loop. Returns True if a flip happened."""
        flipped = False
        
        # If no position, place one
        if not self.position_id:
            price = self.config.buy_price if self.current_side == "buy" else self.config.sell_price
            self.position_id = await self._place_order(self.current_side, price)
            
            if self.position_id:
                self.db.save_loop_state(self.loop_name, self.current_side, self.position_id)
            else:
                self.logger.warning(f"[{self.loop_name}] Failed to place order, will retry...")
                await asyncio.sleep(5)
        
        # Check if position filled
        elif await self._check_position_filled():
            self.logger.info(f"[{self.loop_name}] 🎯 {self.current_side.upper()} filled @ ${self._get_current_price():,.2f}!")
            
            # Flip side
            if self.current_side == "buy":
                self.current_side = "sell"
            else:
                self.current_side = "buy"
                self.db.increment_loop_count(self.loop_name)
                self.logger.info(f"[{self.loop_name}] 🔄 LOOP COMPLETE!")
            
            self.position_id = None
            self.db.save_loop_state(self.loop_name, self.current_side, None)
            flipped = True
        
        return flipped
    
    async def run(self):
        """Main loop for this single loop instance"""
        await self.initialize()
        
        while self.running:
            try:
                await self.run_once()
                await asyncio.sleep(self.global_config.CHECK_INTERVAL_SECONDS)
            except Exception as e:
                self.logger.error(f"[{self.loop_name}] Error: {e}")
                await asyncio.sleep(10)
    
    def stop(self):
        self.running = False


# ============================================================================
# MAIN BOT CONTROLLER
# ============================================================================

class LoopTradeMulti:
    def __init__(self, config: GlobalConfig):
        self.config = config
        self.client: Optional[LNMClient] = None
        self.db = LoopDatabase()
        self.logger = self._setup_logger()
        self.loops: List[SingleLoop] = []
        
    def _setup_logger(self):
        logger = logging.getLogger("LoopTradeMulti")
        logger.setLevel(logging.INFO)
        
        # Console
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # File
        file_handler = logging.FileHandler('looptrade_multi.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    async def __aenter__(self):
        auth = APIAuthContext(
            key=self.config.API_KEY,
            secret=self.config.API_SECRET,
            passphrase=self.config.API_PASSPHRASE
        )
        client_config = APIClientConfig(
            authentication=auth,
            network=self.config.NETWORK,
            timeout=60.0
        )
        self.client = LNMClient(client_config)
        await self.client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def print_status(self):
        """Print status of all loops"""
        stats = self.db.get_all_stats()
        self.logger.info("\n" + "=" * 60)
        self.logger.info("📊 ALL LOOPS STATUS")
        self.logger.info("=" * 60)
        for stat in stats:
            self.logger.info(f"  {stat['loop_name']}: {stat['current_side'].upper()} | Loops: {stat['loops_completed']}")
        self.logger.info("=" * 60 + "\n")
    
    async def run(self):
        """Run all loops concurrently"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 LoopTrade Multi Starting")
        self.logger.info(f"Total loops: {len(self.config.LOOPS)}")
        self.logger.info("=" * 60)
        
        # Show current price
        ticker = await self.client.futures.get_ticker()
        current = float(ticker.get('lastPrice', 0))
        self.logger.info(f"Current BTC price: ${current:,.2f}\n")
        
        # Create loop instances
        for loop_config in self.config.LOOPS:
            if not loop_config.enabled:
                self.logger.info(f"⏸️  {loop_config.name} - DISABLED")
                continue
            
            loop = SingleLoop(loop_config, self.config, self.db, self.client, self.logger)
            self.loops.append(loop)
            
            self.logger.info(f"✅ {loop_config.name}")
            self.logger.info(f"   Buy: ${loop_config.buy_price:,.2f} → Sell: ${loop_config.sell_price:,.2f}")
            self.logger.info(f"   Quantity: ${loop_config.quantity_usd:,.2f} | Leverage: {loop_config.leverage}x")
            if loop_config.stoploss:
                self.logger.info(f"   Stoploss: ${loop_config.stoploss:,.2f}")
            if loop_config.takeprofit:
                self.logger.info(f"   Take Profit: ${loop_config.takeprofit:,.2f}")
            self.logger.info("")
        
        self.logger.info("-" * 60)
        self.logger.info("Press Ctrl+C to stop all loops\n")
        
        # Run all loops concurrently
        tasks = [asyncio.create_task(loop.run()) for loop in self.loops]
        
        # Status reporter
        async def status_reporter():
            while True:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.print_status()
        
        reporter_task = asyncio.create_task(status_reporter())
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            reporter_task.cancel()
            for loop in self.loops:
                loop.stop()
            await self.print_status()
            self.logger.info("👋 All loops stopped.")


# ============================================================================
# INTERACTIVE SETUP
# ============================================================================

def get_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("Please enter a valid number.")

def get_optional_float(prompt: str) -> Optional[float]:
    val = input(prompt).strip()
    return float(val) if val else None

def interactive_setup() -> GlobalConfig:
    config = GlobalConfig()
    
    print("\n" + "=" * 60)
    print("🔄 LoopTrade Multi - Setup")
    print("=" * 60)
    
    # Check API keys
    if not config.API_KEY or len(config.API_KEY) < 10:
        print("\n⚠️  Please set your API credentials in the GlobalConfig section.")
        print("   Edit lines 52-54 in this file.")
        return None
    
    # Show current loops
    print(f"\n📋 Current Loops ({len(config.LOOPS)} defined):")
    for i, loop in enumerate(config.LOOPS, 1):
        status = "✅" if loop.enabled else "⏸️"
        print(f"   {status} {loop.name}: Buy ${loop.buy_price:,.0f} → Sell ${loop.sell_price:,.0f}")
    
    print("\nOptions:")
    print("  1. Use existing loops")
    print("  2. Add new loop interactively")
    print("  3. Clear all and start fresh")
    
    choice = input("\nChoice (1/2/3) [1]: ").strip() or "1"
    
    if choice == "2":
        print("\n--- Add New Loop ---")
        name = input("Loop name: ").strip()
        buy = get_float("Buy price: $")
        sell = get_float("Sell price: $")
        qty = get_float("Quantity per trade (USD): $")
        sl = get_optional_float("Stoploss (optional, press Enter to skip): $")
        tp = get_optional_float("Take profit (optional, press Enter to skip): $")
        
        new_loop = LoopConfig(
            name=name,
            buy_price=buy,
            sell_price=sell,
            quantity_usd=qty,
            stoploss=sl,
            takeprofit=tp
        )
        config.LOOPS.append(new_loop)
        print(f"✅ Added {name}")
        
    elif choice == "3":
        config.LOOPS = []
        num = int(input("How many loops? "))
        for i in range(num):
            print(f"\n--- Loop {i+1} ---")
            name = input("Name: ").strip() or f"Loop {i+1}"
            buy = get_float("Buy price: $")
            sell = get_float("Sell price: $")
            qty = get_float("Quantity (USD): $")
            config.LOOPS.append(LoopConfig(name=name, buy_price=buy, sell_price=sell, quantity_usd=qty))
    
    # Validate loops
    total_capital = sum(loop.quantity_usd * 2 for loop in config.LOOPS if loop.enabled)  # *2 for buy+sell
    print(f"\n💰 Estimated capital needed: ${total_capital:,.2f}")
    
    confirm = input("\nStart trading with these loops? (y/n): ").strip().lower()
    if confirm != 'y':
        return None
    
    return config


# ============================================================================
# MAIN
# ============================================================================

async def main():
    config = interactive_setup()
    if not config:
        return
    
    async with LoopTradeMulti(config) as bot:
        await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 LoopTrade stopped by user.")