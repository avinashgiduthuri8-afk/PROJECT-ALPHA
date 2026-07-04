"""
PROJECT-ALPHA Trading Bot Configuration
Railway Production Ready
"""

import os

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_KEY = os.getenv("API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

# Paper / live trading mode.  Always defaults to PAPER — set VGX_BOT_MODE=LIVE
# explicitly to enable real order execution.
BOT_MODE = os.getenv("VGX_BOT_MODE", "PAPER")

_VALID_BOT_MODES = {"PAPER", "LIVE", "PAUSED", "DISABLED"}
if BOT_MODE not in _VALID_BOT_MODES:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Invalid VGX_BOT_MODE %r — must be one of %s; forcing DISABLED",
        BOT_MODE, sorted(_VALID_BOT_MODES),
    )
    BOT_MODE = "DISABLED"

PROJECT_NAME = "TradingBotCrypto"

TRADE_AMOUNT = float(os.getenv("VGX_TRADE_AMOUNT", os.getenv("TRADE_AMOUNT", "110")))

# ============================================================
# PHASE 5 CONFIG
# ============================================================

PHASE5 = {

    "coins": [
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
        "ZEC"
    ],

    "trade": {

        "target_percent": 0.05,

        "stop_loss_percent": 0.05,

        "max_positions": 5

    },

    "signals": {

        "min_score": 70

    },

    "risk": {

        "safe": 0.20,

        "moderate": 0.40,

        "aggressive": 0.70,

        "active_profile": "MODERATE"

    }

}

# ============================================================
# FALLBACK PRICES
# ============================================================

buy_prices = {

    "BTC": 9000000,

    "ETH": 200000,

    "SOL": 8500,

    "BNB": 50000,

    "XRP": 50,

    "ZEC": 3200

}

# ============================================================
# STORAGE
# ============================================================

STORAGE_DIR = "storage"

STORAGE_FILE = os.path.join(
    STORAGE_DIR,
    f"{PROJECT_NAME}.json"
)

STORAGE_BACKUP = os.path.join(
    STORAGE_DIR,
    f"{PROJECT_NAME}_backup.json"
)

STORAGE_SYNC_INTERVAL = 30

VGX_MAX_SIGNAL_AGE_SECONDS = int(
    os.getenv("VGX_MAX_SIGNAL_AGE_SECONDS", "300")
)
