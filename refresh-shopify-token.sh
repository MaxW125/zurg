#!/bin/bash
# Refreshes the Shopify access token and updates .env + restarts the server.
# Run by launchd every 23 hours via com.zurg.shopify-refresh.plist

STORE="your-store.myshopify.com"
SCOPES="read_all_orders,read_analytics,read_fulfillments,write_fulfillments,write_inventory,read_inventory,read_locations,read_orders,write_orders,read_products,write_products,read_publications,write_publications"
ENV_FILE="~/zurg/.env"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin"

echo "[$(date)] Refreshing Shopify token..."

JSON=$(/opt/homebrew/bin/shopify store auth \
  --store "$STORE" \
  --scopes "$SCOPES" \
  --json 2>/dev/null)

if [ $? -ne 0 ]; then
  echo "[$(date)] ERROR: shopify store auth failed"
  exit 1
fi

# Extract token from CLI cache (store auth --json doesn't print the token itself)
TOKEN=$(python3 -c "
import json, os
with open(os.path.expanduser('~/Library/Preferences/shopify-cli-store-nodejs/config.json')) as f:
    data = json.load(f)
for key, val in data.items():
    try:
        sessions = val['myshopify']['com']
        for uid, session in sessions.get('sessionsByUserId', {}).items():
            if 'your-store' in session.get('store',''):
                print(session['accessToken'])
                exit()
    except:
        pass
" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "[$(date)] ERROR: could not extract token from CLI cache"
  exit 1
fi

# Update .env
sed -i '' "s|^SHOPIFY_ACCESS_TOKEN=.*|SHOPIFY_ACCESS_TOKEN=${TOKEN}|" "$ENV_FILE"

echo "[$(date)] Token updated: ${TOKEN:0:20}..."

# Restart server
~/zurg/restart-server.sh

echo "[$(date)] Done."
