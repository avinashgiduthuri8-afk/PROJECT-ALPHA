"""
PROJECT-ALPHA Persistent Storage Engine
"""

import os
import json
import shutil
import threading
import time

from .config import *

# Single lock guarding the one TradingBotCrypto.json storage file.
_storage_lock = threading.Lock()

# ============================================================
# RUNTIME VARIABLES
# ============================================================

virtual_balance = 1000000

positions = {}

trade_log = []

price_history = {}

market_cache = {}

portfolio_history = []

trade_history = []

error_logs = []

metrics_summary = {}

# ============================================================
# STORAGE STATUS
# ============================================================

storage_state = {

    "status": "INITIALIZED",

    "last_sync": 0,

    "sync_count": 0,

    "backup_status": "NONE"

}


# ============================================================
# VERIFY FILE
# ============================================================

def _verify_file(path):

    if not os.path.exists(path):
        return False

    if os.path.getsize(path) == 0:
        return False

    try:

        with open(path, "r", encoding="utf-8") as f:

            json.load(f)

        return True

    except Exception:

        return False


# ============================================================
# NORMALIZE STORAGE
# ============================================================

def _normalise(data):

    defaults = {

        "virtual_balance": 1000000,

        "positions": {},

        "trade_log": [],

        "price_history": {},

        "market_cache": {},

        "portfolio_history": [],

        "trade_history": [],

        "error_logs": [],

        "metrics_summary": {}

    }

    for k, v in defaults.items():

        data.setdefault(k, v)

    return data


# ============================================================
# LOAD STORAGE
# ============================================================

def load_data():

    global virtual_balance

    global positions

    global trade_log

    global price_history

    global market_cache

    global portfolio_history

    global trade_history

    global error_logs

    global metrics_summary

    with _storage_lock:

        if not _verify_file(STORAGE_FILE):

            os.makedirs(STORAGE_DIR, exist_ok=True)

            # Release lock before calling save_data() which also acquires it
            pass

        else:

            with open(STORAGE_FILE, "r", encoding="utf-8") as f:

                data = json.load(f)

            data = _normalise(data)

            virtual_balance    = data["virtual_balance"]
            positions          = data["positions"]
            trade_log          = data["trade_log"]
            price_history      = data["price_history"]
            market_cache       = data["market_cache"]
            portfolio_history  = data["portfolio_history"]
            trade_history      = data["trade_history"]
            error_logs         = data["error_logs"]
            metrics_summary    = data["metrics_summary"]
            return

    # File missing or corrupt — initialise with defaults and persist
    os.makedirs(STORAGE_DIR, exist_ok=True)
    save_data()


# ============================================================
# SAVE STORAGE
# ============================================================

def save_data():

    with _storage_lock:

        os.makedirs(STORAGE_DIR, exist_ok=True)

        payload = {

            "virtual_balance": virtual_balance,

            "positions": positions,

            "trade_log": trade_log,
            "price_history": price_history,

            "market_cache": market_cache,

            "portfolio_history": portfolio_history,

            "trade_history": trade_history,

            "error_logs": error_logs,

            "metrics_summary": metrics_summary

        }

        temp_file = STORAGE_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:

            json.dump(payload, f, indent=4)

        if os.path.exists(STORAGE_FILE):

            shutil.copy2(

                STORAGE_FILE,

                STORAGE_BACKUP

            )

        os.replace(temp_file, STORAGE_FILE)

        storage_state["status"] = "SYNCED"

        storage_state["last_sync"] = time.time()

        storage_state["sync_count"] += 1


def get_open_positions() -> list[dict]:
    """Return current open VGX positions as list[dict] for risk-engine deployed-capital checks.

    Each dict carries at least one of the keys _deployed_capital() expects:
    ('total_invested', 'total_cost', 'amount', 'trade_amount').
    """
    data: dict = {}
    try:
        if _verify_file(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    positions_dict = data.get("positions", {})
    if not isinstance(positions_dict, dict):
        return []

    result = []
    for key, p in positions_dict.items():
        if not isinstance(p, dict):
            continue
        entry = {
            "coin":            p.get("coin", key.split("_")[0] if "_" in key else key),
            "buy_price":       p.get("buy_price", 0),
            "qty":             p.get("qty", 0),
            "amount":          p.get("amount", 0),
            "trade_amount":    p.get("amount", 0),
            "trailing_active": p.get("trailing_active", False),
        }
        result.append(entry)
    return result
