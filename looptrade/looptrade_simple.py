#!/usr/bin/env python3
"""
LoopTrade Simple - Single Ping-Pong Loop
Enter a buy price and sell price. Bot loops between them until you cancel.
"""

import asyncio
import sqlite3
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from lnmarkets_sdk.rest.v3.http.client import LNMClient
from lnmarkets_sdk.rest.v3._internal.models import APIAuthContext, APIClientConfig
from lnmarkets_sdk.rest.v3.models.futures_isolated import FuturesOrder

# ============================================================================
# USER CONFIGURATION - EDIT THESE VALUES
# ============================================================================

@dataclass
class Config:
    # LNMarkets API Credentials (from https://lnmarkets.com → API Keys)
    API_KEY: str = ""
    API_SECRET: str = ""
    API_PASSPHRASE: str = ""
    
    # Trading Parameters
    BUY_PRICE: float = 65000.0      # Price to buy at
    SELL_PRICE: float = 70000.0     # Price to sell at
    QUANTITY_USD: float = 100.0     # USD amount per trade
    LEVERAGE: int = 1               # 1x = no leverage
    
    # Optional Protection Orders
    STOPLOSS_PRICE: Optional[float] = None    # Stoploss for each position (optional)
    TAKEPROFIT_PRICE: Optional[float] = None  # Take profit for each position (optional)
    
    # Bot Settings
    CHECK_INTERVAL_SECONDS: int = 30
    NETWORK: str = "mainnet"

# ============================================================================
# SIMPLE LOOP TRADE BOT
# ============================================================================

class SimpleLoopTrade:
    def __init__(self, config: Config):
        self.config = config
        self.client: Optional[LNMClient] = None
        self.current_side: str = "buy"  # Start with buy
        self.position_id: Optional[str] = None
        self.logger = self._setup_logger()
        self.stats = {"loops": 0, "buys": 0, "sells": 0, "errors": 0}
        
    def _setup_logger(self):
        logger = logging.getLogger("LoopTrade")
        logger.setLevel(logging.INFO)
        
        # Console handler
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # File handler
        file_handler = logging.FileHandler('looptrade.log')
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
    
    async def get_current_price(self) -> float:
        """Get current BTC price"""
        ticker = await self.client.futures.get_ticker()
        return float(ticker.get('lastPrice', 0))
    
    def calculate_quantity(self, price: float) -> int:
        """Calculate satoshi quantity from USD amount"""
        btc_amount = self.config.QUANTITY_USD / price
        satoshis = int(btc_amount * 1e8)
        return satoshis
    
    async def place_order(self, side: str, price: float) -> Optional[str]:
        """Place a limit order"""
        try:
            quantity = self.calculate_quantity(price)
            
            # Build order params
            order_params = {
                'type': 'limit',
                'side': side,
                'price': float(price),
                'quantity': quantity,
                'leverage': float(self.config.LEVERAGE)
            }
            
            # Add optional stoploss/takeprofit
            if self.config.STOPLOSS_PRICE:
                order_params['stoploss'] = float(self.config.STOPLOSS_PRICE)
            if self.config.TAKEPROFIT_PRICE:
                order_params['takeprofit'] = float(self.config.TAKEPROFIT_PRICE)
            
            params = FuturesOrder(**order_params)
            response = await self.client.futures.isolated.new_trade(params)
            
            position_id = response.id if hasattr(response, 'id') else str(response)
            
            self.logger.info(f"✅ Placed {side.upper()} order: {quantity/1e8:.8f} BTC @ ${price:,.2f}")
            
            return position_id
            
        except Exception as e:
            self.logger.error(f"❌ Failed to place {side} order: {e}")
            self.stats["errors"] += 1
            return None
    
    async def check_position_status(self, position_id: str) -> bool:
        """Check if position is still open. Returns False if filled/closed."""
        try:
            # Get running (open) positions
            running = await self.client.futures.isolated.get_running_trades()
            running_ids = {p.id for p in running}
            
            if position_id in running_ids:
                return True  # Still open/waiting
            
            # Check if it was filled (in closed trades)
            closed = await self.client.futures.isolated.get_closed_trades()
            closed_ids = {p.id for p in closed}
            
            if position_id in closed_ids:
                return False  # Filled!
            
            # Not in running or closed - might be pending/open orders
            open_orders = await self.client.futures.isolated.get_open_trades()
            open_ids = {p.id for p in open_orders}
            
            return position_id in open_ids
            
        except Exception as e:
            self.logger.error(f"Error checking position: {e}")
            return True  # Assume still open on error
    
    async def run(self):
        """Main loop - runs forever until stopped"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 LoopTrade Simple Starting")
        self.logger.info(f"Buy: ${self.config.BUY_PRICE:,.2f}")
        self.logger.info(f"Sell: ${self.config.SELL_PRICE:,.2f}")
        self.logger.info(f"Quantity: ${self.config.QUANTITY_USD:,.2f} per trade")
        self.logger.info(f"Leverage: {self.config.LEVERAGE}x")
        if self.config.STOPLOSS_PRICE:
            self.logger.info(f"Stoploss: ${self.config.STOPLOSS_PRICE:,.2f}")
        if self.config.TAKEPROFIT_PRICE:
            self.logger.info(f"Take Profit: ${self.config.TAKEPROFIT_PRICE:,.2f}")
        self.logger.info("=" * 60)
        
        # Show current price
        current = await self.get_current_price()
        self.logger.info(f"Current BTC price: ${current:,.2f}")
        
        # Determine starting side based on price
        if current <= self.config.BUY_PRICE:
            self.current_side = "buy"
            self.logger.info("Price is at/below buy level - starting with BUY order")
        elif current >= self.config.SELL_PRICE:
            self.current_side = "sell"
            self.logger.info("Price is at/above sell level - starting with SELL order")
        else:
            self.current_side = "buy"
            self.logger.info("Price is between levels - starting with BUY order (will fill when price drops)")
        
        running = True
        
        while running:
            try:
                # If no position, place one
                if not self.position_id:
                    price = self.config.BUY_PRICE if self.current_side == "buy" else self.config.SELL_PRICE
                    self.position_id = await self.place_order(self.current_side, price)
                    
                    if self.position_id:
                        self.logger.info(f"Waiting for {self.current_side.upper()} to fill...")
                    else:
                        self.logger.error("Failed to place order, retrying in 60s...")
                        await asyncio.sleep(60)
                        continue
                
                # Check if position filled
                is_open = await self.check_position_status(self.position_id)
                
                if not is_open:
                    # Position filled! Flip side.
                    self.logger.info(f"🎯 {self.current_side.upper()} filled!")
                    
                    if self.current_side == "buy":
                        self.stats["buys"] += 1
                        self.current_side = "sell"
                    else:
                        self.stats["sells"] += 1
                        self.current_side = "buy"
                        self.stats["loops"] += 1
                        self.logger.info(f"🔄 LOOP #{self.stats['loops']} COMPLETE!")
                    
                    self.position_id = None  # Will place new order next iteration
                
                # Print status every 10 checks
                if self.stats["loops"] > 0 and self.stats["loops"] % 10 == 0:
                    self.logger.info(f"📊 Stats: {self.stats['loops']} loops | {self.stats['buys']} buys | {self.stats['sells']} sells")
                
                await asyncio.sleep(self.config.CHECK_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                self.logger.info("\n👋 Stopping LoopTrade...")
                running = False
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)
        
        # Cleanup
        self.logger.info(f"Final Stats: {self.stats}")


# ============================================================================
# INTERACTIVE SETUP
# ============================================================================

def get_float_input(prompt: str, default: Optional[float] = None) -> float:
    """Get float input from user"""
    while True:
        try:
            if default:
                user_input = input(f"{prompt} [{default}]: ").strip()
                if not user_input:
                    return default
            else:
                user_input = input(f"{prompt}: ").strip()
            return float(user_input)
        except ValueError:
            print("Please enter a valid number.")

def get_optional_float(prompt: str) -> Optional[float]:
    """Get optional float input"""
    user_input = input(f"{prompt} (press Enter to skip): ").strip()
    if not user_input:
        return None
    try:
        return float(user_input)
    except ValueError:
        return None

def interactive_setup():
    """Interactive configuration"""
    print("\n" + "=" * 60)
    print("🔄 LoopTrade Simple - Setup")
    print("=" * 60)
    
    config = Config()
    
    # Check if API keys are already set
    if not config.API_KEY or len(config.API_KEY) < 10:
        print("\n⚠️  Please set your API credentials in the Config section at the top of this file.")
        print("Get them from: https://lnmarkets.com → Profile → API Keys")
        return None
    
    print("\n📊 Current Settings:")
    print(f"  Buy Price: ${config.BUY_PRICE:,.2f}")
    print(f"  Sell Price: ${config.SELL_PRICE:,.2f}")
    print(f"  Quantity: ${config.QUANTITY_USD:,.2f}")
    
    change = input("\nChange these settings? (y/n) [n]: ").strip().lower()
    
    if change == 'y':
        config.BUY_PRICE = get_float_input("Buy price (USD)", config.BUY_PRICE)
        config.SELL_PRICE = get_float_input("Sell price (USD)", config.SELL_PRICE)
        config.QUANTITY_USD = get_float_input("Quantity per trade (USD)", config.QUANTITY_USD)
        config.STOPLOSS_PRICE = get_optional_float("Stoploss price (optional)")
        config.TAKEPROFIT_PRICE = get_optional_float("Take profit price (optional)")
    
    # Validate
    if config.BUY_PRICE >= config.SELL_PRICE:
        print("❌ Error: Buy price must be LESS than sell price!")
        return None
    
    if config.QUANTITY_USD < 10:
        print("❌ Error: Minimum quantity is $10")
        return None
    
    print("\n" + "=" * 60)
    print("✅ Configuration complete!")
    print(f"Loop: Buy ${config.BUY_PRICE:,.2f} → Sell ${config.SELL_PRICE:,.2f}")
    print("=" * 60)
    
    confirm = input("\nStart trading? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return None
    
    return config


# ============================================================================
# MAIN
# ============================================================================

async def main():
    # Get configuration
    config = interactive_setup()
    if not config:
        return
    
    # Run bot
    async with SimpleLoopTrade(config) as bot:
        await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 LoopTrade stopped.")