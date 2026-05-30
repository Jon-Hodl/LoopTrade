# LoopTrade - LNMarkets Grid Trading Bot
# https://github.com/ln-markets/sdk-python

import asyncio
import sqlite3
import logging
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig

# ============================================================================
# CONFIGURATION - FILL IN YOUR VALUES
# ============================================================================

@dataclass
class LoopTradeConfig:
    """Configuration for LoopTrade bot"""
    # API Credentials (Fill these in locally, NEVER commit to git)
    api_key: str = "Yv1WQFz0Jd/zwH9FI8Jm6hC+CF6itdXMI4Rmt713X94="
    api_secret: str = "qWim7AW12AQf5kthd6pB/1u8xtoQwns7s94fFqaqiguM6PEVYMvvfg0EmOGs1Ft11EyrnHE2a9eJh3xsnKMWwg=="
    api_passphrase: str = "Hal Finn"
    network: str = "mainnet"  # or "testnet" if available
    
    # Trading Mode
    # "stack_sats" = keep 1-5% of each trade in BTC (accumulate sats)
    # "grow_fiat" = keep 1-5% of each trade in USD (accumulate dollars)
    mode: str = "stack_sats"  # or "grow_fiat"
    
    # Retention percentage (what to keep per loop)
    # Stack Sats: When selling, keep X% of BTC
    # Grow Fiat: When buying, only use X% of sale proceeds
    retention_pct: float = 0.05  # 5%
    
    # Grid Configuration
    num_loops: int = 10
    price_min: float = 75000  # $60K
    price_max: float = 85000  # $110K
    
    # Capital per loop (in USD equivalent)
    capital_per_loop: float = 100  # ~0.01 BTC at $70K
    
    # Leverage (1x = spot-like, higher = more risk)
    leverage: int = 2
    
    # Telegram Notifications (optional)
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

# ============================================================================
# DATABASE SCHEMA
# ============================================================================

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS loops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grid_index INTEGER UNIQUE NOT NULL,
    buy_price REAL NOT NULL,
    sell_price REAL NOT NULL,
    side TEXT NOT NULL,  -- 'buy' or 'sell' (which side is currently open)
    position_id TEXT,    -- LNMarkets position ID
    quantity REAL NOT NULL,
    filled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_id INTEGER,
    side TEXT NOT NULL,  -- 'buy' or 'sell'
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    position_id TEXT,
    pnl REAL,
    fees REAL,
    retention_amount REAL,  -- BTC or USD kept
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (loop_id) REFERENCES loops(id)
);

CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY,
    total_loops_completed INTEGER DEFAULT 0,
    total_btc_accumulated REAL DEFAULT 0,
    total_usd_accumulated REAL DEFAULT 0,
    total_fees_paid REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    def __init__(self, db_path: str = "looptrade.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database with schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(DB_SCHEMA)
            
            # Initialize stats if empty
            cursor = conn.execute("SELECT COUNT(*) FROM stats")
            if cursor.fetchone()[0] == 0:
                conn.execute("INSERT INTO stats (id) VALUES (1)")
            conn.commit()
    
    def get_loop(self, grid_index: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM loops WHERE grid_index = ?", (grid_index,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_loop(self, grid_index: int, buy_price: float, sell_price: float, 
                    side: str, quantity: float) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO loops (grid_index, buy_price, sell_price, side, quantity)
                   VALUES (?, ?, ?, ?, ?)""",
                (grid_index, buy_price, sell_price, side, quantity)
            )
            conn.commit()
            return cursor.lastrowid
    
    def update_loop_position(self, grid_index: int, side: str, 
                            position_id: Optional[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE loops SET side = ?, position_id = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE grid_index = ?""",
                (side, position_id, grid_index)
            )
            conn.commit()
    
    def record_trade(self, loop_id: int, side: str, price: float, quantity: float,
                    position_id: str, pnl: float = 0, fees: float = 0,
                    retention_amount: float = 0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO trades 
                   (loop_id, side, price, quantity, position_id, pnl, fees, retention_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (loop_id, side, price, quantity, position_id, pnl, fees, retention_amount)
            )
            conn.commit()
    
    def update_stats(self, btc_accumulated: float = 0, usd_accumulated: float = 0,
                    fees: float = 0, loops_completed: int = 0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE stats SET
                   total_btc_accumulated = total_btc_accumulated + ?,
                   total_usd_accumulated = total_usd_accumulated + ?,
                   total_fees_paid = total_fees_paid + ?,
                   total_loops_completed = total_loops_completed + ?,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE id = 1""",
                (btc_accumulated, usd_accumulated, fees, loops_completed)
            )
            conn.commit()
    
    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM stats WHERE id = 1")
            return dict(cursor.fetchone())
    
    def get_all_open_loops(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM loops ORDER BY grid_index")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_state(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value FROM state WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def set_state(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO state (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                   updated_at = CURRENT_TIMESTAMP""",
                (key, value)
            )
            conn.commit()

# ============================================================================
# LOOPTRADE BOT
# ============================================================================

class LoopTrade:
    def __init__(self, config: LoopTradeConfig):
        self.config = config
        self.db = DatabaseManager()
        self.client: Optional[LNMClient] = None
        self.logger = self._setup_logging()
        self.running = False
        
    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("LoopTrade")
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Also log to file
        file_handler = logging.FileHandler('looptrade.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    async def __aenter__(self):
        """Async context manager entry"""
        auth = APIAuthContext(
            key=self.config.api_key,
            secret=self.config.api_secret,
            passphrase=self.config.api_passphrase
        )
        config = APIClientConfig(
            authentication=auth,
            network=self.config.network,
            timeout=60.0
        )
        self.client = LNMClient(config)
        await self.client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.__aexit__(exc_type, exc_val, exc_tb)
    
    def calculate_grids(self) -> List[Dict]:
        """Calculate grid prices (linear spacing)"""
        grids = []
        price_step = (self.config.price_max - self.config.price_min) / self.config.num_loops
        
        for i in range(self.config.num_loops):
            buy_price = self.config.price_min + (i * price_step)
            sell_price = self.config.price_min + ((i + 1) * price_step)
            
            grids.append({
                'index': i,
                'buy_price': round(buy_price, 2),
                'sell_price': round(sell_price, 2),
                'spread_pct': round((sell_price - buy_price) / buy_price * 100, 2)
            })
        
        return grids
    
    async def initialize_grids(self):
        """Initialize all grid loops in the database"""
        self.logger.info(f"Initializing {self.config.num_loops} grids...")
        
        grids = self.calculate_grids()
        current_price = await self.get_current_price()
        
        for grid in grids:
            existing = self.db.get_loop(grid['index'])
            if existing:
                continue
            
            # Determine initial side based on current price
            # If price is above grid → start with buy order below
            # If price is below grid → start with sell order above
            if current_price > grid['sell_price']:
                initial_side = 'buy'
            elif current_price < grid['buy_price']:
                initial_side = 'sell'
            else:
                # Price is within grid → start with buy (conservative)
                initial_side = 'buy'
            
            quantity = self.calculate_quantity(grid['buy_price'])
            
            self.db.create_loop(
                grid_index=grid['index'],
                buy_price=grid['buy_price'],
                sell_price=grid['sell_price'],
                side=initial_side,
                quantity=quantity
            )
            
            self.logger.info(f"Grid {grid['index']}: Buy ${grid['buy_price']:,.2f} → Sell ${grid['sell_price']:,.2f} "
                           f"(Spread: {grid['spread_pct']}%) [{initial_side.upper()}]")
        
        self.logger.info(f"Initialized {len(grids)} grids at current price ${current_price:,.2f}")
    
    def calculate_quantity(self, price: float) -> float:
        """Calculate position size based on capital per loop"""
        # Convert USD capital to BTC quantity
        quantity = self.config.capital_per_loop / price
        # Round to 8 decimal places (satoshi precision)
        return float(Decimal(str(quantity)).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
    
    async def get_current_price(self) -> float:
        """Get current BTC price from LNMarkets"""
        ticker = await self.client.futures.get_ticker()
        return float(ticker.get('lastPrice', 0))
    
    async def place_order(self, side: str, price: float, quantity: float) -> Optional[str]:
        """Place an isolated margin order on LNMarkets"""
        try:
            from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder
            
            # Create order params
            params = FuturesOrder(
                type='limit',
                side=side,  # 'buy' or 'sell'
                price=float(price),
                quantity=int(quantity * 1e8),  # Convert to satoshis
                leverage=float(self.config.leverage)
            )
            
            response = await self.client.futures.isolated.new_trade(params)
            position_id = response.id if hasattr(response, 'id') else str(response)
            
            self.logger.info(f"Placed {side.upper()} order: {quantity:.8f} BTC @ ${price:,.2f} "
                           f"(Position ID: {position_id})")
            
            return position_id
            
        except Exception as e:
            self.logger.error(f"Failed to place {side} order: {e}")
            return None
    
    async def check_and_flip_loop(self, loop: Dict):
        """Check if a loop's order filled and flip it"""
        position_id = loop.get('position_id')
        
        if not position_id:
            # No active position, need to place initial order
            if loop['side'] == 'buy':
                new_position_id = await self.place_order(
                    'buy', loop['buy_price'], loop['quantity']
                )
                if new_position_id:
                    self.db.update_loop_position(loop['grid_index'], 'buy', new_position_id)
            else:
                new_position_id = await self.place_order(
                    'sell', loop['sell_price'], loop['quantity']
                )
                if new_position_id:
                    self.db.update_loop_position(loop['grid_index'], 'sell', new_position_id)
            return
        
        # Check if position is still open
        try:
            positions = await self.client.futures.isolated.get_running_trades()
            open_position_ids = {p['id'] for p in positions}
            
            if position_id not in open_position_ids:
                # Position closed (filled)! Flip the loop.
                await self.handle_filled_order(loop)
                
        except Exception as e:
            self.logger.error(f"Error checking position {position_id}: {e}")
    
    async def handle_filled_order(self, loop: Dict):
        """Handle a filled order and flip to the other side"""
        filled_side = loop['side']
        position_id = loop['position_id']
        
        # Get filled order details
        try:
            closed_trades = await self.client.futures.isolated.get_closed_trades()
            trade = next((t for t in closed_trades if t['id'] == position_id), None)
            
            if not trade:
                self.logger.warning(f"Could not find closed trade {position_id}")
                return
            
            filled_price = float(trade.get('price', 0))
            quantity = loop['quantity']
            pnl = float(trade.get('pl', 0))
            fees = float(trade.get('fees', 0))
            
            # Calculate retention based on mode
            if self.config.mode == 'stack_sats':
                # Keep X% of BTC when selling
                if filled_side == 'sell':
                    retention = quantity * self.config.retention_pct
                    new_quantity = quantity - retention
                    self.logger.info(f"Stacking {retention:.8f} BTC (${retention * filled_price:.2f})")
                else:
                    retention = 0
                    new_quantity = quantity
                    
                self.db.update_stats(btc_accumulated=retention, fees=fees)
                
            else:  # grow_fiat
                # Keep X% of USD when buying (only use 95% of proceeds)
                if filled_side == 'buy':
                    proceeds = quantity * filled_price
                    retention = proceeds * self.config.retention_pct
                    new_quantity = (proceeds - retention) / filled_price
                    self.logger.info(f"Keeping ${retention:.2f} USD")
                else:
                    retention = 0
                    new_quantity = quantity
                    
                self.db.update_stats(usd_accumulated=retention, fees=fees)
            
            # Record the trade
            loop_record = self.db.get_loop(loop['grid_index'])
            self.db.record_trade(
                loop_id=loop_record['id'],
                side=filled_side,
                price=filled_price,
                quantity=quantity,
                position_id=position_id,
                pnl=pnl,
                fees=fees,
                retention_amount=retention
            )
            
            # Flip the loop
            if filled_side == 'buy':
                # Just bought → now place sell
                new_side = 'sell'
                new_price = loop['sell_price']
                flip_quantity = new_quantity if self.config.mode == 'stack_sats' else quantity
            else:
                # Just sold → now place buy
                new_side = 'buy'
                new_price = loop['buy_price']
                flip_quantity = new_quantity if self.config.mode == 'grow_fiat' else quantity
            
            # Place the flipped order
            new_position_id = await self.place_order(new_side, new_price, flip_quantity)
            
            if new_position_id:
                self.db.update_loop_position(loop['grid_index'], new_side, new_position_id)
                self.db.update_stats(loops_completed=1)
                
                self.logger.info(f"🔄 LOOP COMPLETE! Grid {loop['grid_index']}: "
                               f"{filled_side.upper()} @ ${filled_price:,.2f} → {new_side.upper()} @ ${new_price:,.2f} "
                               f"| PnL: ${pnl:+.2f}")
            else:
                self.logger.error(f"Failed to place flipped order for grid {loop['grid_index']}")
                self.db.update_loop_position(loop['grid_index'], new_side, None)
                
        except Exception as e:
            self.logger.error(f"Error handling filled order: {e}", exc_info=True)
    
    async def run_loop(self):
        """Main trading loop"""
        self.logger.info("=" * 60)
        self.logger.info("LoopTrade Bot Starting...")
        self.logger.info(f"Mode: {self.config.mode.upper()}")
        self.logger.info(f"Retention: {self.config.retention_pct * 100}%")
        self.logger.info(f"Grids: {self.config.num_loops} (${self.config.price_min:,.0f} - ${self.config.price_max:,.0f})")
        self.logger.info(f"Capital per loop: ${self.config.capital_per_loop:,.2f}")
        self.logger.info(f"Leverage: {self.config.leverage}x")
        self.logger.info("=" * 60)
        
        # Initialize grids
        await self.initialize_grids()
        
        self.running = True
        cycle = 0
        
        while self.running:
            try:
                cycle += 1
                self.logger.info(f"\n--- Cycle {cycle} ---")
                
                # Get all open loops
                loops = self.db.get_all_open_loops()
                
                # Check each loop
                for loop in loops:
                    await self.check_and_flip_loop(loop)
                    await asyncio.sleep(1.1)  # Rate limit: 1 req/sec
                
                # Print stats every 10 cycles
                if cycle % 10 == 0:
                    stats = self.db.get_stats()
                    self.logger.info(f"\n📊 STATS: {stats['total_loops_completed']} loops completed | "
                                   f"BTC: {stats['total_btc_accumulated']:.8f} | "
                                   f"USD: ${stats['total_usd_accumulated']:.2f} | "
                                   f"Fees: ${stats['total_fees_paid']:.2f}")
                
                # Wait before next cycle
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait longer on error
    
    async def cancel_all_orders(self):
        """Emergency: Cancel all open orders"""
        self.logger.warning("CANCELLING ALL ORDERS...")
        try:
            await self.client.futures.isolated.cancel_all()
            self.logger.info("All orders cancelled")
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e}")
    
    async def get_account_summary(self):
        """Get current account status"""
        try:
            account = await self.client.account.get_account()
            self.logger.info(f"Account Balance: {account}")
            return account
        except Exception as e:
            self.logger.error(f"Error getting account: {e}")
            return None


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main entry point"""
    # Load config (edit LoopTradeConfig above with your values)
    config = LoopTradeConfig()
    
    # Validate config
    if not config.api_key or config.api_key == "YOUR_API_KEY_HERE" or len(config.api_key) < 10:
        print("❌ ERROR: Please fill in your API credentials in LoopTradeConfig!")
        print("Edit the config values at the top of looptrade.py")
        return
    
    async with LoopTrade(config) as bot:
        # Optional: Get account summary before starting
        await bot.get_account_summary()
        
        # Start the bot
        await bot.run_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 LoopTrade stopped by user")