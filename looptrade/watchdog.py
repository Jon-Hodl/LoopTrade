#!/usr/bin/env python3
"""
LoopTrade Watchdog
Monitors the bot and ensures it stays running
Run this as a separate service or cron job
"""

import json
import time
import urllib.request
import sys
from datetime import datetime

STATE_FILE = "looptrade_state.json"
HEALTH_URL = "http://127.0.0.1:5001/api/health"
START_URL = "http://127.0.0.1:5001/api/start"

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    with open("watchdog.log", "a") as f:
        f.write(f"[{timestamp}] {message}\n")

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"should_be_running": False}

def check_health():
    """Check if server and bot are healthy"""
    try:
        req = urllib.request.Request(HEALTH_URL, method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {'status': 'unreachable', 'error': str(e)}

def start_bot():
    """Start the bot via API"""
    try:
        req = urllib.request.Request(START_URL, method='POST', headers={
            'Content-Type': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {'success': False, 'error': str(e)}

def main():
    log("Watchdog started")
    
    # Wait a bit for server to be ready
    time.sleep(5)
    
    while True:
        try:
            state = load_state()
            should_run = state.get("should_be_running", False)
            
            health = check_health()
            
            if health.get('status') == 'unreachable':
                log("⚠️  Server unreachable - will retry")
                time.sleep(10)
                continue
            
            bot_running = health.get('bot', {}).get('is_running', False)
            
            if should_run and not bot_running:
                log("🔴 Bot should be running but isn't - attempting auto-restart")
                result = start_bot()
                if result.get('success'):
                    log("✅ Bot auto-started successfully")
                else:
                    log(f"❌ Failed to start bot: {result.get('error', 'Unknown error')}")
            elif should_run and bot_running:
                log("✅ Bot running normally")
            elif not should_run:
                log("💤 Bot intentionally stopped")
            
        except Exception as e:
            log(f"❌ Watchdog error: {e}")
        
        # Check every 30 seconds
        time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Watchdog stopped by user")
        sys.exit(0)
