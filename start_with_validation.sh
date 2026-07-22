#!/bin/bash
# LoopTrade Startup with API Validation
# Only starts trading if API keys are valid

cd "$(dirname "$0")"

echo "🔐 Validating API keys..."
./venv/bin/python3 validate_api.py

if [ $? -eq 0 ]; then
    echo "✅ API keys valid. Starting LoopTrade..."
    exec ./venv/bin/python3 -m looptrade
else
    echo ""
    echo "❌ Cannot start LoopTrade - API keys invalid"
    echo "   Please check your API credentials in looptrade_config.json"
    echo "   Get valid keys at: https://lnmarkets.com/settings/api"
    exit 1
fi
