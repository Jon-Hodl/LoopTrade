#!/bin/bash
# LoopTrade User Service Installer (runs only when you're logged in)

echo "Installing LoopTrade as a user service..."

# Copy plist to LaunchAgents (user level, no sudo needed)
cp /Users/hal/LoopTrade/com.looptrade.server.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.looptrade.server.plist

# Start the service
launchctl start com.looptrade.server

echo "✅ LoopTrade user service installed and started!"
echo ""
echo "It will now:"
echo "- Start when you log in"
echo "- Restart if it crashes"
echo "- Run in background (no terminal needed)"
echo ""
echo "Access at: http://localhost:5001"
echo "Logs at: ~/LoopTrade/server.log"
echo ""
echo "To stop: launchctl stop com.looptrade.server"
echo "To disable: launchctl unload ~/Library/LaunchAgents/com.looptrade.server.plist"
