#!/bin/bash
# Restart the Zurg server cleanly via launchd
# Usage: ./restart-server.sh

echo "Restarting Zurg server..."
launchctl unload ~/Library/LaunchAgents/com.zurg.server.plist
sleep 2
launchctl load ~/Library/LaunchAgents/com.zurg.server.plist
sleep 5

# Verify it's up
if curl -s http://localhost:9000/api/rooms/pipeline/config > /dev/null 2>&1; then
  echo "✓ Server is up"
else
  echo "✗ Server not responding — check ~/zurg/logs/server.log"
fi
