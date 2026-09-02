"""
Symbol normalizer for CoinResearchService.

Converts any user-supplied symbol string to canonical "BASE/QUOTE" form,
validates against the known CoinDCX pair universe, and provides the
searchable pairs list for the Research Hub autocomplete.
"""

from __future__ import annotations

from typing import Optional


# ── Known CoinDCX tradeable pairs ────────────────────────────────────────────

SUPPORTED_PAIRS: list[str] = [
    # INR pairs
    "BTC/INR",
    "ETH/INR",
    "BNB/INR",
    "SOL/INR",
    "XRP/INR",
    "ADA/INR",
    "MATIC/INR",
    "DOGE/INR",
    "TRX/INR",
    "SHIB/INR",
    "AVAX/INR",
    "LINK/INR",
    "DOT/INR",
    "LTC/INR",
    "ZEC/INR",
    "ATOM/INR",
    "FTM/INR",
    "NEAR/INR",
    "APT/INR",
    "SUI/INR",
    # USDT pairs
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "MATIC/USDT",
    "DOGE/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "DOT/USDT",
    "LTC/USDT",
    "ZEC/USDT",
    "ATOM/USDT",
    "FTM/USDT",
    "NEAR/USDT",
    "APT/USDT",
    "SUI/USDT",
]

# Quick lookup set
_SUPPORTED_SET: set[str] = set(SUPPORTED_PAIRS)

# Base → default quote mapping (prefer INR when ambiguous)
_BASE_DEFAULT_QUOTE: dict[str, str] = {
    "BTC":   "INR",
    "ETH":   "INR",
    "BNB":   "INR",
    "SOL":   "INR",
    "XRP":   "INR",
    "ADA":   "INR",
    "MATIC": "INR",
    "DOGE":  "INR",
    "TRX":   "INR",
    "SHIB":  "INR",
    "AVAX":  "INR",
    "LINK":  "INR",
    "DOT":   "INR",
    "LTC":   "INR",
    "ZEC":   "USDT",   # ZEC primary market is USDT on CoinDCX
    "ATOM":  "INR",
    "FTM":   "INR",
    "NEAR":  "INR",
    "APT":   "INR",
    "SUI":   "INR",
}

_KNOWN_QUOTES: tuple[str, ...] = ("USDT", "INR", "BTC", "ETH", "BNB")


def normalize_symbol(raw: str) -> str:
    """
    Normalize any user-supplied symbol to canonical "BASE/QUOTE" form.

    Examples:
        "BTC"         -> "BTC/INR"
        "btc/inr"     -> "BTC/INR"
        "BTCINR"      -> "BTC/INR"
        "B-BTC_INR"   -> "BTC/INR"
        "BTC-INR"     -> "BTC/INR"
        "SOL/USDT"    -> "SOL/USDT"
    """
    s = raw.strip().upper()

    # Already canonical with slash
    if "/" in s:
        parts = s.split("/", 1)
        return f"{parts[0]}/{parts[1]}"

    # CoinDCX wire format: "B-BTC_INR" or "I-BTC_INR"
    if s.startswith(("B-", "I-")):
        s = s[2:]  # strip prefix
        if "_" in s:
            base, quote = s.split("_", 1)
            return f"{base}/{quote}"

    # Hyphen separator: "BTC-INR"
    if "-" in s:
        parts = s.split("-", 1)
        return f"{parts[0]}/{parts[1]}"

    # Underscore separator: "BTC_INR"
    if "_" in s:
        parts = s.split("_", 1)
        return f"{parts[0]}/{parts[1]}"

    # No separator — try to split off known quote currencies
    for quote in _KNOWN_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"

    # Bare base symbol — apply default quote
    if s in _BASE_DEFAULT_QUOTE:
        return f"{s}/{_BASE_DEFAULT_QUOTE[s]}"

    # Unknown — return as-is with INR fallback
    return f"{s}/INR"


def is_supported_pair(pair: str) -> bool:
    """Return True if the canonical pair is in the known CoinDCX universe."""
    canonical = normalize_symbol(pair)
    return canonical in _SUPPORTED_SET


def get_supported_pairs_info() -> list[dict]:
    """Return list of {pair, base, quote} dicts for the Research Hub autocomplete."""
    result = []
    for pair in SUPPORTED_PAIRS:
        base, quote = pair.split("/")
        result.append({"pair": pair, "base": base, "quote": quote})
    return result
