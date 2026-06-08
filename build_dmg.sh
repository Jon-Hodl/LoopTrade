#!/bin/bash
# Build LoopTrade macOS DMG Installer

APP_NAME="LoopTrade"
VERSION="1.0.0"
BUILD_DIR="build"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"

echo "🏗️ Building LoopTrade DMG Installer..."

# Clean build directory
rm -rf ${BUILD_DIR}
mkdir -p ${BUILD_DIR}

# Create app bundle structure
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources"

# Create Info.plist
cat > "${APP_BUNDLE}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>LoopTrade</string>
    <key>CFBundleIdentifier</key>
    <string>com.jonhodl.looptrade</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>LoopTrade</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.12</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2024 Jon Hodl. All rights reserved.</string>
</dict>
</plist>
PLIST

# Create launcher script
cat > "${APP_BUNDLE}/Contents/MacOS/LoopTrade" << 'SCRIPT'
#!/bin/bash

# Get the directory where the app is located
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL_DIR="$HOME/LoopTrade"

# Check if LoopTrade is installed
if [ ! -d "$INSTALL_DIR" ]; then
    # First run - install to home directory
    osascript << 'APPLESCRIPT'
        display dialog "LoopTrade needs to be installed to ~/LoopTrade. Proceed?" buttons {"Cancel", "Install"} default button "Install" with icon note
        set buttonPressed to button returned of result
        if buttonPressed is "Cancel" then
            return
        end if
APPLESCRIPT
    
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    # Copy files
    mkdir -p "$INSTALL_DIR"
    cp -R "${APP_DIR}/../Resources/looptrade_src/"* "$INSTALL_DIR/"
    
    # Create config from template
    if [ ! -f "$INSTALL_DIR/looptrade_config.json" ]; then
        cp "$INSTALL_DIR/looptrade_config.template.json" "$INSTALL_DIR/looptrade_config.json"
    fi
fi

# Open Terminal and run
tell application "Terminal"
    do script "cd $INSTALL_DIR && source venv/bin/activate && python looptrade.py"
    set frontmost to true
end tell

delay 4

# Open browser
open "http://localhost:5001"
SCRIPT

chmod +x "${APP_BUNDLE}/Contents/MacOS/LoopTrade"

# Copy source code to Resources
mkdir -p "${APP_BUNDLE}/Contents/Resources/looptrade_src"
cp -r *.py templates scripts requirements.txt "${APP_BUNDLE}/Contents/Resources/looptrade_src/"
cp looptrade_config.template.json "${APP_BUNDLE}/Contents/Resources/looptrade_src/"

# Create DMG
echo "📦 Creating DMG..."

# Create temporary directory for DMG contents
DMG_TEMP=$(mktemp -d)
cp -r "${APP_BUNDLE}" "${DMG_TEMP}/"

# Create Applications symlink
ln -s /Applications "${DMG_TEMP}/Applications"

# Create README
cat > "${DMG_TEMP}/README.txt" << 'README'
LoopTrade - Automated Bitcoin Grid Trading

INSTALLATION:
1. Drag LoopTrade.app to Applications folder
2. Double-click LoopTrade from Applications
3. On first run, it will install to ~/LoopTrade
4. Configure your LN Markets API keys in the web interface

REQUIREMENTS:
- macOS 10.12 or later
- Python 3.12+ (will be installed if needed)
- LN Markets account with API access

SUPPORT:
https://github.com/Jon-Hodl/LoopTrade
README

# Build DMG
hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_TEMP}" -ov -format UDZO "${DMG_NAME}"

# Cleanup
rm -rf "${DMG_TEMP}" "${BUILD_DIR}"

echo "✅ Created ${DMG_NAME}"
echo "📍 Location: $(pwd)/${DMG_NAME}"
