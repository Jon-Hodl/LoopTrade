# 🔁 LoopTrade

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![LN Markets](https://img.shields.io/badge/LN%20Markets-API-orange)](https://lnmarkets.com)

> Automated Bitcoin grid trading bot for [LN Markets](https://lnmarkets.com). Trade smarter, not harder.

![LoopTrade Screenshot](docs/screenshot.png)

## 🎯 What is LoopTrade?

LoopTrade is an open-source, automated trading bot that executes **grid trading strategies** on Bitcoin. It works with [LN Markets](https://lnmarkets.com) to automatically:

- **Buy low, sell high** (Long strategy)
- **Sell high, buy low** (Short strategy)
- Flip between positions when orders fill
- Earn sats while you sleep

Built for Bitcoiners who want hands-off trading with full control.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔄 **Grid Trading** | Automated buy/sell loops at your set prices |
| 📈 **Long & Short** | Trade both directions — bull or bear markets |
| 🧠 **Smart Signals** | Fear & Greed Index + 24h trend dashboard |
| ⚡ **Lightning Fast** | Built on LN Markets with sub-second execution |
| 🔒 **Self-Custody** | Your API keys, your funds, your control |
| 📊 **Modern UI** | Clean web interface with real-time updates |
| 🎯 **Per-Loop Leverage** | Different leverage for each trading loop |
| 🚀 **Auto-Restart** | Runs as a service — survives reboots |

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- macOS or Linux (Windows WSL works too)
- [LN Markets](https://lnmarkets.com) account with API access

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/looptrade.git
cd looptrade

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. **Get API keys from LN Markets:**
   - Log in to [LN Markets](https://lnmarkets.com)
   - Go to Settings → API → Create New Key
   - Enable permissions: `futures:isolated:read` and `futures:isolated:write`

2. **Start the web interface:**
   ```bash
   python looptrade.py
   ```

3. **Open your browser:**
   ```
   http://127.0.0.1:5001
   ```

4. **Add your API keys** in the Settings tab

5. **Create your first loop** in the Add Loop tab

6. **Start the bot** and watch it trade!

### Auto-Start on Boot (macOS)

```bash
# Copy the launchd service file
cp com.looptrade.server.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.looptrade.server.plist

# Start now
launchctl start com.looptrade.server
```

## 🎮 How It Works

### Grid Trading Explained

1. **Set your range:** Buy price → Sell price
2. **Set your size:** How much USD per trade
3. **Choose direction:** 
   - **Long:** Buy first, then sell higher
   - **Short:** Sell first, then buy lower
4. **Bot takes over:** Places limit orders, flips sides when filled

### Example Loop

```
Buy Price: $95,000
Sell Price: $105,000
Quantity: $50
Leverage: 1x

→ Bot places buy order at $95k
→ When filled, bot places sell order at $105k
→ When sell fills, bot places buy order again
→ Loop repeats forever (or until you stop it)
```

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Flask API  │────▶│  LN Markets │
│  (UI)       │◀────│  (Python)   │◀────│   API       │
└─────────────┘     └─────────────┘     └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   SQLite    │
                     │   (state)   │
                     └─────────────┘
```

### Tech Stack

- **Backend:** Python 3.9+, Flask, asyncio
- **Frontend:** HTML5, vanilla JavaScript
- **API:** LN Markets v3 (isolated futures)
- **Database:** SQLite (local state)
- **Styling:** Custom CSS with glassmorphism

## 📁 Project Structure

```
looptrade/
├── looptrade.py              # Main Flask application
├── looptrade_minimal.py      # Standalone CLI version
├── looptrade_config.json     # Your configuration (created on first run)
├── requirements.txt          # Python dependencies
├── com.looptrade.server.plist # macOS auto-start service
├── start.sh                  # Auto-restart script
├── templates/
│   ├── index.html           # Main trading interface
│   └── landing.html         # Entry page
├── static/                  # CSS, JS, images
└── docs/
    └── screenshot.png       # UI screenshot
```

## 🔐 Security

- **API keys stored locally** — Never leave your machine
- **Isolated margin only** — No cross-margin risks
- **No withdrawal permissions** — Bot can only trade, not withdraw
- **Input validation** — Prices and quantities validated before execution
- **Rate limiting** — Respects LN Markets API limits

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas we need help with:**
- 🧪 Unit tests
- 🐳 Docker support
- 📊 Additional indicators
- 🔔 Telegram/Discord notifications
- 🌐 Multi-exchange support

## 📝 License

MIT License — see [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

**LoopTrade is provided as-is for educational purposes.**

- Trading involves risk of loss
- Past performance does not guarantee future results
- Only trade with funds you can afford to lose
- Review all code before running with real funds

## 🙏 Acknowledgments

- Built for the Bitcoin community
- Powered by [LN Markets](https://lnmarkets.com)
- Fear & Greed data from [Alternative.me](https://alternative.me/crypto/fear-and-greed-index/)
- Price data from [CoinGecko](https://www.coingecko.com/)

---

**Made with 🔥 by Bitcoiners, for Bitcoiners.**

[Report Bug](https://github.com/yourusername/looptrade/issues) · [Request Feature](https://github.com/yourusername/looptrade/issues)
