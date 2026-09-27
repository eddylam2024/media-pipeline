#!/usr/bin/env python3
"""Refresh the IG access token before it expires (60-day token)."""
import json, os, urllib.request, ssl, sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.environ.get("IG_CONFIG") or os.path.join(BASE, "ig_config.json")
REFRESH_DAYS = 55  # refresh when <55 days remain (runs weekly)

ctx = ssl.create_default_context()

def api(url):
    return json.loads(urllib.request.urlopen(url, context=ctx).read())

# Load current token
cfg = json.load(open(CONFIG))
token = cfg["access_token"]
APP_ID = os.environ.get("META_APP_ID") or cfg.get("app_id")
APP_SECRET = os.environ.get("META_APP_SECRET") or cfg.get("app_secret")
if not APP_ID or not APP_SECRET:
    print("ERR: set app_id/app_secret in ig_config.json or META_APP_ID/META_APP_SECRET")
    sys.exit(1)

# Debug current token
try:
    debug_url = f"https://graph.facebook.com/v21.0/debug_token?input_token={token}&access_token={APP_ID}|{APP_SECRET}"
    info = api(debug_url)["data"]
except Exception as e:
    print(f"ERR: debug_token failed: {e}")
    sys.exit(1)

if not info.get("is_valid"):
    print(f"ERR: token not valid: {info}")
    sys.exit(1)

expires = info["expires_at"]
now = datetime.now(timezone.utc).timestamp()
days_left = (expires - now) / 86400

print(f"Token valid. Expires: {datetime.fromtimestamp(expires, tz=timezone.utc).strftime('%Y-%m-%d')} ({days_left:.0f} days left)")

if days_left > REFRESH_DAYS:
    print(f"Not refreshing (>{REFRESH_DAYS} days left).")
    sys.exit(0)

# Exchange for new long-lived token
print("Refreshing...")
try:
    exchange_url = (
        f"https://graph.facebook.com/v21.0/oauth/access_token"
        f"?grant_type=fb_exchange_token"
        f"&client_id={APP_ID}"
        f"&client_secret={APP_SECRET}"
        f"&fb_exchange_token={token}"
    )
    result = api(exchange_url)
except Exception as e:
    print(f"ERR: exchange failed: {e}")
    sys.exit(1)

new_token = result.get("access_token")
if not new_token:
    print(f"ERR: no token in response: {result}")
    sys.exit(1)

# Verify new token
try:
    verify_url = f"https://graph.facebook.com/v21.0/debug_token?input_token={new_token}&access_token={APP_ID}|{APP_SECRET}"
    vinfo = api(verify_url)["data"]
except Exception as e:
    print(f"ERR: verify new token failed: {e}")
    sys.exit(1)

if not vinfo.get("is_valid") or "instagram_content_publish" not in vinfo.get("scopes", []):
    print(f"ERR: new token invalid or missing scopes: {vinfo}")
    sys.exit(1)

new_exp = vinfo["expires_at"]
new_days = (new_exp - now) / 86400
print(f"New token valid. Expires: {datetime.fromtimestamp(new_exp, tz=timezone.utc).strftime('%Y-%m-%d')} ({new_days:.0f} days)")

# Save
cfg["access_token"] = new_token
with open(CONFIG, "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"Saved. Old expiry: {days_left:.0f}d → New expiry: {new_days:.0f}d")
