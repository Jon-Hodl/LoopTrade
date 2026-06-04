# LoopTrade

Automated Bitcoin grid trading bot for LN Markets. LoopTrade places limit orders at strategic price levels and automatically sets take-profits, creating a hands-off trading strategy that works while you sleep.

![LoopTrade](https://img.shields.io/badge/Bitcoin-Loop%20Trading-orange)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![LN Markets](https://img.shields.io/badge/LN%20Markets-Integrated-green)

## Features

- **Grid Trading**: Place multiple limit orders at configured price levels
- **Automatic Take-Profits**: Each entry order gets an automatic exit order
- **Smart Market Logic**: Won't place orders that would execute as market orders
- **Loop Continuation**: Automatically places new entry orders after take-profits fill
- **Periodic Rescan**: Every 5 minutes, ensures all configured loops have orders
- **Mirror Mode**: Sync your configured loops exactly with LN Markets
- **Directional Trading**: Support for both Long (buy first) and Short (sell first) strategies
- **Per-Loop Leverage**: Configure leverage individually for each trading loop
- **Fear & Greed Index**: Market sentiment indicator
- **Real-time Dashboard**: Web interface to monitor and control your trading

## Quick Start

### Prerequisites

- Python 3.12 or higher
- LN Markets API key with futures trading permission
- Some Bitcoin to trade (start small!)

### Installation

```bash
# Clone the repository
git clone https://github.com/Jon-Hodl/LoopTrade.git
cd LoopTrade

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install flask aiohttp
pip install git+https://github.com/ln-markets/sdk-python.git

# Start the bot
python looptrade.py
```

Open http://localhost:5001 in your browser.

### API Key Setup

1. Go to [LN Markets](https://lnmarkets.com)
2. Navigate to API settings
3. Generate an API key with **futures trading** permission
4. Copy the key, secret, and passphrase into LoopTrade dashboard

## How It Works

### The Grid Strategy

LoopTrade uses a grid trading strategy:

1. **Configure Loops**: Set buy prices below market, sell prices above
2. **Place Orders**: Bot places limit orders at your configured prices
3. **Auto Take-Profit**: Each filled entry automatically sets an exit order
4. **Loop Continuation**: When exit fills, bot immediately places new entry
5. **Periodic Rescan**: Every 5 minutes, ensures all loops have active orders

### Example Long Loop

```
Buy Price: $60,000 (below current market)
Sell Price: $61,000 (take-profit target)
Quantity: $10
Leverage: 2x
```

When BTC drops to $60k:
- Limit buy order fills
- Automatic take-profit set at $61k
- When $61k hits, position closes with profit
- Bot immediately places new $60k buy order

### Smart Order Validation

LoopTrade **won't** place orders that don't make sense:

- **Long orders**: Buy price must be BELOW current market
- **Short orders**: Sell price must be ABOVE current market

This prevents accidental market orders and protects your capital.

## Dashboard

The web dashboard provides:

- **Configuration**: Add/edit trading loops
- **Market Data**: Live BTC price, Fear & Greed index
- **Performance**: P&L tracking per loop and total
- **Order Status**: See which loops have active orders
- **Mirror Mode**: Force sync between config and LN Markets
- **Logs**: Real-time bot activity

## Configuration

Loops are configured via the dashboard or `looptrade_config.json`:

```json
{
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "api_passphrase": "your-passphrase",
  "loops": [
    {
      "id": 1,
      "name": "60K → 61K",
      "direction": "long",
      "buy_price": 60000,
      "sell_price": 61000,
      "quantity_usd": 10,
      "leverage": 2,
      "enabled": true
    }
  ]
}
```

## Running as a Service

### macOS (LaunchAgent)

```bash
./install_user_service.sh
```

This installs LoopTrade as a background service that:
- Starts when you log in
- Restarts if it crashes
- Runs without a terminal window

### Linux (systemd)

```bash
sudo cp looptrade.service /etc/systemd/system/
sudo systemctl enable looptrade
sudo systemctl start looptrade
```

## Safety Features

- **Isolated Margin**: Each position is isolated with limited risk
- **Quantity-Based Sizing**: Control exact position size, not margin
- **Rate Limiting**: Respects LN Markets API limits
- **Error Recovery**: Automatically retries on transient errors
- **No Market Orders**: Prevents accidental market execution

## Important Notes

⚠️ **Trading Risk**: This is experimental software. Only trade what you can afford to lose.

⚠️ **Test First**: Start with small amounts to understand the behavior.

⚠️ **API Limits**: LN Markets has rate limits. The bot handles these gracefully.

⚠️ **Price Gaps**: If BTC gaps past your grid, orders won't fill until price returns.

## Troubleshooting

### Bot won't start

Check that dependencies are installed:
```bash
source venv/bin/activate
pip install flask aiohttp
pip install git+https://github.com/ln-markets/sdk-python.git
```

### Orders not placing

- Check that buy prices are BELOW current BTC price (for longs)
- Check that sell prices are ABOVE current BTC price (for shorts)
- Check logs for "SKIPPED" messages explaining why

### Only some loops have orders

This is normal! Loops with entry prices on the "wrong" side of market won't place until price moves. Use the dashboard to adjust prices or wait for market movement.

## License

MIT License - See LICENSE file

## Disclaimer

This software is provided "as is" without warranty. Cryptocurrency trading carries significant risk. The authors are not responsible for any losses incurred through use of this software.

---

**Built with ❤️ by Bitcoiners for Bitcoiners**
