#!/bin/bash
# Fix LoopTrade Setup Script

echo "Fixing LoopTrade dependencies..."

cd /Users/hal/LoopTrade

# Make sure we're in the venv
source venv/bin/activate

# Upgrade pip first
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install required packages
echo "Installing Flask and aiohttp..."
pip install flask aiohttp

# Install LN Markets SDK
echo "Installing LN Markets SDK..."
pip install git+https://github.com/ln-markets/sdk-python.git

echo ""
echo "Testing installation..."
python -c "import lnmarkets_sdk; import flask; import aiohttp; print('✓ All dependencies installed!')"

echo ""
echo "Starting LoopTrade..."
python looptrade.py
