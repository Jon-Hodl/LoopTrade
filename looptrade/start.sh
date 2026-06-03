#!/bin/bash

# LoopTrade Auto-Restart Script
# Keeps the Flask server running automatically

cd "$(dirname "$0")"

# Log startup
echo "[$(date)] LoopTrade start script initiated" >> server.log

while true; do
    echo "[$(date)] Starting LoopTrade server..." >> server.log
    
    # Activate virtual environment and run
    source venv/bin/activate
    python looptrade.py
    
    EXIT_CODE=$?
    echo "[$(date)] Server stopped with exit code $EXIT_CODE" >> server.log
    echo "[$(date)] Restarting in 3 seconds..." >> server.log
    sleep 3
done
