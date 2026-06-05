#!/bin/bash
osascript << 'APPLESCRIPT'
tell application "Terminal"
    set newTab to do script "cd ~/LoopTrade && source venv/bin/activate && python looptrade.py"
    set frontmost to true
end tell

delay 4

tell application "Safari"
    open location "http://localhost:5001"
    activate
end tell
APPLESCRIPT
