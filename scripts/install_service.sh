#!/bin/bash
# LoopTrade Background Service Installer

echo "Installing LoopTrade as a background service..."

# Copy plist to LaunchDaemons (requires sudo)
sudo cp /Users/hal/LoopTrade/com.looptrade.server.plist /Library/LaunchDaemons/

# Set proper permissions
sudo chown root:wheel /Library/LaunchDaemons/com.looptrade.server.plist
sudo chmod 644 /Library/LaunchDaemons/com.looptrade.server.plist

# Load the service
sudo launchctl load /Library/LaunchDaemons/com.looptrade.server.plist

# Start the service
sudo launchctl start com.looptrade.server

echo "✅ LoopTrade service installed and started!"
echo ""
echo "It will now:"
echo "- Start automatically when Mac boots"
echo "- Restart if it crashes"
echo "- Run in background (no terminal needed)"
echo ""
echo "Access at: http://localhost:5001"
echo "Logs at: ~/LoopTrade/server.log"
echo ""
echo "To stop: sudo launchctl stop com.looptrade.server"
echo "To disable: sudo launchctl unload /Library/LaunchDaemons/com.looptrade.server.plist"
