"""
PROJECT-ALPHA Persistent Storage Engine
"""

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone

from .config import *

_logger = logging.getLogger("vgx.storage")

# Single lock guarding the one TradingBotCrypto.json storage file.
_storage_lock = threading.Lock()

# Default coin list — used when grid_coins key is absent from storage.
_DEFAULT_GRID_COINS: list = ["BTC", "ETH", "SOL", "BNB", "XRP", "ZEC"]

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

# ── Grid management globals ───────────────────────────────────────────────────
# grid_config: per-coin manual base-price overrides.
#   schema: {"BTC": {"base_price": float, "base_price_set_at": str, "base_price_set_by": str}}
# grid_coins: ordered list of active coins for the VGX grid.
grid_config: dict = {}
grid_coins: list = list(_DEFAULT_GRID_COINS)

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

        "metrics_summary": {},

        # Grid management — safe defaults so old storage files upgrade silently.
        "grid_config": {},
        "grid_coins":  list(_DEFAULT_GRID_COINS),

    }

    for k, v in defaults.items():

        data.setdefault(k, v)

    # Type-coerce grid management fields so corrupt/unexpected storage values
    # degrade to safe defaults rather than propagating into callers.
    if not isinstance(data["grid_config"], dict):
        _logger.warning(
            "[VGX] grid_config has unexpected type %s — resetting to {}",
            type(data["grid_config"]).__name__,
        )
        data["grid_config"] = {}
    else:
        # Purge any entries that are not dicts (corrupted sub-records).
        data["grid_config"] = {
            k: v for k, v in data["grid_config"].items()
            if isinstance(v, dict)
        }

    if not isinstance(data["grid_coins"], list):
        _logger.warning(
            "[VGX] grid_coins has unexpected type %s — resetting to default list",
            type(data["grid_coins"]).__name__,
        )
        data["grid_coins"] = list(_DEFAULT_GRID_COINS)
    else:
        # Keep only string entries; drop anything else silently.
        data["grid_coins"] = [c for c in data["grid_coins"] if isinstance(c, str)]
        if not data["grid_coins"]:
            data["grid_coins"] = list(_DEFAULT_GRID_COINS)

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
    global grid_config
    global grid_coins

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
            grid_config        = data["grid_config"]
            grid_coins         = data["grid_coins"]
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

            "metrics_summary": metrics_summary,

            # Grid management — must be included so save_data() never clobbers them.
            "grid_config": grid_config,
            "grid_coins":  grid_coins,

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


# ============================================================
# GRID MANAGEMENT — PUBLIC API
# ============================================================
# All six functions are synchronous; call them from async handlers
# via asyncio.to_thread (mutating operations carry file I/O via save_data).


def get_grid_config() -> dict:
    """Return the current grid_config dict (in-memory, always in sync with file).

    Returns {} when no manual base prices have been set.
    Synchronous — wrap in asyncio.to_thread when calling from an async handler.
    """
    with _storage_lock:
        return dict(grid_config)


def get_coin_base_price(coin: str) -> float | None:
    """Return the manual base price for *coin* if one is set, else None.

    None means the caller should fall back to the live market price.
    """
    with _storage_lock:
        entry = grid_config.get(coin)
    if entry and isinstance(entry, dict):
        price = entry.get("base_price")
        if price is not None and float(price) > 0:
            return float(price)
    return None


def set_coin_base_price(coin: str, price: float, set_by: str = "dashboard") -> bool:
    """Set a manual grid-centre base price for *coin*.

    Validates price > 0, writes to grid_config[coin] with ISO timestamp,
    then persists via save_data().

    Returns True on success, False on validation failure or write error.
    """
    global grid_config

    if not isinstance(price, (int, float)) or price <= 0:
        _logger.warning(
            "[VGX] set_coin_base_price rejected: coin=%s price=%r (must be > 0)",
            coin, price,
        )
        return False

    now_iso = datetime.now(timezone.utc).isoformat()

    with _storage_lock:
        # Build a fresh dict so we don't mutate a reference held by callers.
        grid_config = dict(grid_config)
        grid_config[coin] = {
            "base_price":        float(price),
            "base_price_set_at": now_iso,
            "base_price_set_by": str(set_by),
        }

    _logger.info(
        "[VGX] Base price set: coin=%s price=%s set_by=%s",
        coin, price, set_by,
    )

    save_data()
    return True


def remove_coin_base_price(coin: str) -> bool:
    """Remove the manual base price override for *coin*.

    Returns True if an entry was found and removed, False if coin not present.
    """
    global grid_config

    with _storage_lock:
        if coin not in grid_config:
            return False
        grid_config = dict(grid_config)
        grid_config.pop(coin, None)

    _logger.info("[VGX] Base price removed: coin=%s", coin)
    save_data()
    return True


def get_grid_coins() -> list:
    """Return the ordered list of active VGX grid coins.

    Falls back to _DEFAULT_GRID_COINS when the storage key is absent or empty.
    """
    with _storage_lock:
        coins = list(grid_coins)
    return coins if coins else list(_DEFAULT_GRID_COINS)


def set_grid_coins(coins: list) -> bool:
    """Replace the active VGX grid coin list.

    Validates:
    - List must not be empty.
    - Each coin must be alphanumeric (no special characters).
    - Maximum 20 coins.

    Returns True on success, False on validation failure or write error.
    """
    global grid_coins

    if not coins:
        _logger.warning("[VGX] set_grid_coins rejected: empty list")
        return False

    if len(coins) > 20:
        _logger.warning(
            "[VGX] set_grid_coins rejected: %d coins exceeds maximum of 20",
            len(coins),
        )
        return False

    for c in coins:
        if not isinstance(c, str) or not c.isalnum():
            _logger.warning(
                "[VGX] set_grid_coins rejected: %r is not alphanumeric", c
            )
            return False
        if len(c) > 10:
            _logger.warning(
                "[VGX] set_grid_coins rejected: %r exceeds 10-character limit", c
            )
            return False

    # Normalise to uppercase and deduplicate (preserve first occurrence order).
    seen: set = set()
    normalised: list = []
    for c in coins:
        up = c.upper()
        if up not in seen:
            seen.add(up)
            normalised.append(up)

    with _storage_lock:
        grid_coins = normalised

    _logger.info("[VGX] Grid coins updated: %s", normalised)
    save_data()
    return True
