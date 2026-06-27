"""Application-wide constants and default configuration.

Everything here is static and import-safe (no Qt / network imports) so that any
module can pull these values without side effects.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Application identity
# --------------------------------------------------------------------------- #
APP_NAME = "Claude Usage Monitor"
APP_ID = "ClaudeMonitor"          # used for folders / registry / single-instance
APP_VERSION = "1.0.0"
APP_AUTHOR = "Claude Usage Monitor"
ORG_DOMAIN = "claude-monitor.local"

# Author / project links (shown in the About dialog).
APP_AUTHOR_NAME = "MTMAK9"
APP_GITHUB = "https://github.com/mtmak9"

# --------------------------------------------------------------------------- #
# Filesystem locations
# --------------------------------------------------------------------------- #
def _appdata_dir() -> Path:
    """Return the per-user data directory (%APPDATA%/ClaudeMonitor on Windows)."""
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    path = Path(base) / APP_ID
    return path


DATA_DIR: Path = _appdata_dir()
DATABASE_PATH: Path = DATA_DIR / "usage.db"
USER_CONFIG_PATH: Path = DATA_DIR / "config.json"
LOG_PATH: Path = DATA_DIR / "monitor.log"
# Where we cache an access token *we* refreshed ourselves (never the source app's).
OAUTH_CACHE_PATH: Path = DATA_DIR / "oauth_cache.json"

# Claude Code / Claude desktop write the subscription OAuth token here (plaintext
# when signed in via the standalone CLI).  The desktop app keeps an *encrypted*
# copy instead — see src/api/oauth.py.
CREDENTIALS_PATH: Path = Path.home() / ".claude" / ".credentials.json"

# Project-relative resources
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
CONFIG_DIR: Path = PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH: Path = CONFIG_DIR / "default.toml"

# --------------------------------------------------------------------------- #
# Anthropic API
# --------------------------------------------------------------------------- #
API_BASE_URL = "https://api.anthropic.com"
API_MESSAGES_ENDPOINT = "/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Subscription usage endpoint — read with an OAuth Bearer token (no API key).
# Returns rolling 5h / 7d utilisation for the Pro/Max subscription.
OAUTH_USAGE_ENDPOINT = "/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
# Token-refresh endpoint + the public Claude Code OAuth client id (used when a
# credential doesn't carry its own issuing client id).
OAUTH_TOKEN_ENDPOINT = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Interactive login (PKCE) — lets any user authorise their own Claude account.
# We use the manual "show the code" redirect, which is registered for the public
# client above, so no local callback server / firewall exception is needed.
OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
# Exact scope set registered for the public client above.  Requesting a subset
# (e.g. just "user:inference user:profile") makes the authorize page reject the
# request with "Invalid request format", so keep all three in this order.
OAUTH_SCOPES = "org:create_api_key user:profile user:inference"

# Cheapest model — used for the lightweight "ping" that returns rate-limit headers
PING_MODEL = "claude-haiku-4-5-20251001"

# Keyring service name for the stored API key
KEYRING_SERVICE = f"{APP_ID}.api_key"
KEYRING_USERNAME = "default"

# Known models -> display metadata.  Keyed by a stable id prefix.
MODELS = {
    "claude-opus-4-8":   {"label": "Opus 4.8",   "short": "Opus",   "tier": "opus"},
    "claude-opus-4-7":   {"label": "Opus 4.7",   "short": "Opus",   "tier": "opus"},
    "claude-opus-4-6":   {"label": "Opus 4.6",   "short": "Opus",   "tier": "opus"},
    "claude-sonnet-4-6": {"label": "Sonnet 4.6", "short": "Sonnet", "tier": "sonnet"},
    "claude-sonnet-4-5": {"label": "Sonnet 4.5", "short": "Sonnet", "tier": "sonnet"},
    "claude-haiku-4-5":  {"label": "Haiku 4.5",  "short": "Haiku",  "tier": "haiku"},
    "claude-fable-5":    {"label": "Fable 5",    "short": "Fable",  "tier": "fable"},
}
DEFAULT_MODEL = "claude-opus-4-8"


def model_label(model_id: str | None) -> str:
    """Return a friendly label for a model id (best-effort prefix match)."""
    if not model_id:
        return "Unknown"
    for key, meta in MODELS.items():
        if model_id.startswith(key):
            return meta["label"]
    # Fall back to a cleaned-up version of the raw id.
    return model_id.replace("claude-", "").replace("-", " ").title()


# --------------------------------------------------------------------------- #
# Usage thresholds & polling
# --------------------------------------------------------------------------- #
# Utilisation percentages that change the icon colour / trigger notifications.
THRESHOLD_OK = 50.0       # below this -> green
THRESHOLD_WARN = 80.0     # below this -> yellow, at/above -> red
NOTIFY_THRESHOLDS = (80.0, 90.0, 100.0)

# Polling cadence (seconds)
MIN_POLL_INTERVAL = 15
MAX_POLL_INTERVAL = 3600
DEFAULT_POLL_INTERVAL = 180

# The /api/oauth/usage endpoint rate-limits to roughly one request every ~2
# minutes, so OAuth mode never polls faster than this floor (regardless of the
# configured interval or smart-polling) to avoid 429 Too Many Requests.
MIN_OAUTH_POLL_INTERVAL = 150

# Smart polling: poll faster when usage is high.
SMART_POLL_FAST = 30
SMART_POLL_SLOW = 300

# --------------------------------------------------------------------------- #
# Peak hours (US / Pacific) — Anthropic's documented heavy-traffic window.
# Off-peak is generally cheaper / less contended.
# --------------------------------------------------------------------------- #
PEAK_TIMEZONE = "America/Los_Angeles"
PEAK_START_HOUR = 9       # 09:00 Pacific
PEAK_END_HOUR = 18        # 18:00 Pacific
PEAK_WEEKDAYS_ONLY = True  # weekends are treated as off-peak

# --------------------------------------------------------------------------- #
# UI sizing
# --------------------------------------------------------------------------- #
OVERLAY_WIDTH = 280
OVERLAY_HEIGHT_EXPANDED = 600
OVERLAY_HEIGHT_COMPACT = 200
WINDOW_MARGIN = 18

# --------------------------------------------------------------------------- #
# Default configuration (mirrors config/default.toml; used as a safe fallback
# when the TOML file cannot be read).
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG: dict = {
    "auth": {
        # Default to OAuth: subscription users get real 5h/7d utilisation from
        # the locally discovered Claude token with no API key required.
        "auth_type": "oauth",       # one of: oauth | api_key | mock
        "api_key": "",              # stored in keyring when possible; here only as fallback
        "model": DEFAULT_MODEL,
    },
    "display": {
        "opacity": 0.95,
        "always_on_top": True,
        "compact": False,
        "language": "pl",           # pl | en
        "pos_x": -1,                # -1 => auto place top-right
        "pos_y": -1,
        "active_tab": 0,            # 0=DZIŚ 1=TYDZIEŃ 2=MIESIĄC
    },
    "polling": {
        "interval": DEFAULT_POLL_INTERVAL,
        "smart_polling": True,
    },
    "notifications": {
        "enabled": True,
        "threshold_80": True,
        "threshold_90": True,
        "threshold_100": True,
    },
    "system": {
        "autostart": False,
        "minimize_to_tray": True,
    },
}
