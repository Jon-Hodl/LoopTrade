# 🔄 LoopTrade

> Automated Bitcoin grid trading bot for LN Markets

LoopTrade places limit orders at strategic price levels and automatically sets take-profits, creating a hands-off trading strategy that works while you sleep.

[![Bitcoin](https://img.shields.io/badge/Bitcoin-Loop%20Trading-F7931A?style=for-the-badge&logo=bitcoin&logoColor=white)](https://bitcoin.org)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LN Markets](https://img.shields.io/badge/LN%20Markets-Integrated-792EE5?style=for-the-badge)](https://lnmarkets.com)

## 🎯 What is LoopTrade?

LoopTrade implements a **grid trading strategy** on LN Markets:
- Place limit buy orders below market price
- Automatically set take-profit sell orders
- When trades complete, the loop restarts automatically
- Profit from Bitcoin's natural volatility without constant monitoring

## 📁 Project Structure

```
LoopTrade/
├── looptrade/              # Main application package
│   ├── __init__.py
│   ├── __main__.py         # Main Flask app
│   ├── watchdog.py         # Process monitor
│   └── templates/          # HTML templates
├── scripts/                # Helper scripts
│   ├── start.sh            # Start the bot
│   ├── install_service.sh  # Install as service (macOS/Linux)
│   └── build_dmg.sh        # Build macOS installer
├── requirements.txt        # Python dependencies
├── LICENSE
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- LN Markets API key with futures trading permission

### Installation

```bash
# Clone repository
git clone https://github.com/Jon-Hodl/LoopTrade.git
cd LoopTrade

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
# Copy looptrade_config.example.json to looptrade_config.json
# Add your LN Markets API credentials

# Start the bot
python -m looptrade
```

Open http://localhost:5001 in your browser.

## ⚙️ Configuration

1. Go to [LN Markets](https://lnmarkets.com) → API settings
2. Generate API key with **futures trading** permission
3. Copy `looptrade_config.example.json` to `looptrade_config.json`
4. Add your API credentials

Example configuration:
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

## 🖥️ Running as a Service

### macOS
```bash
./scripts/install_service.sh
```

### Linux (systemd)
```bash
sudo cp scripts/looptrade.service /etc/systemd/system/
sudo systemctl enable looptrade
sudo systemctl start looptrade
```

## 🛡️ Security

- **API keys** are stored in `looptrade_config.json` (gitignored)
- **Never commit** your configuration file
- Use environment variables for production deployments

## ⚠️ Disclaimer

This software is experimental. Only trade what you can afford to lose. The authors are not responsible for any losses incurred through use of this software.

## 📄 License

MIT License - See [LICENSE](LICENSE)

---

**Built with ❤️ by Bitcoiners for Bitcoiners**
