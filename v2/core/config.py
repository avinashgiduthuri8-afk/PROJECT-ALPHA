"""
PROJECT-ALPHA — Configuration System.

Canonical Pydantic BaseSettings model for application configuration.
Rules:
  - No service ever calls os.getenv() directly.
  - Environment variables are read once at startup and stored here.
  - A subset of keys is hot-reloadable via config_override.json.
  - Capital limits require a restart to change.

Canonical configuration class: AppConfig (aliased as V2Config for backward compatibility)
Canonical environment variables:
  - TRADING_ENABLED (fallback: V2_TRADING_ENABLED)
  - DEPLOYMENT_MODE (fallback: V2_DEPLOYMENT_MODE)
  - SHADOW_MODE (fallback: V2_SHADOW_MODE)
  - EXECUTION_TIMEOUT (fallback: V2_EXECUTION_TIMEOUT)
  - DB_PATH (fallback: V2_DB_PATH)

Canonical database path: data/project_alpha.db (fallback: v2/data/alpha_v2.db)

Usage:
    from v2.core.config import AppConfig, V2Config, get_config
    cfg = get_config()
    print(cfg.trading_enabled)
"""

from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ORDER_AMOUNT_INR: float = 200.0

LEGACY_FIELD_MAP = {
    "v2_trading_enabled": "trading_enabled",
    "v2_deployment_mode": "deployment_mode",
    "v2_shadow_mode": "shadow_mode",
    "v2_execution_timeout": "execution_timeout",
    "v2_db_path": "db_path",
}


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    db_path: str = Field(
        default="data/project_alpha.db",
        validation_alias=AliasChoices("DB_PATH", "V2_DB_PATH", "db_path", "v2_db_path"),
        description="Path to the canonical SQLite database file.",
    )

    # ── Unified Capital Pool & Sizing ─────────────────────────────────────────
    total_capital_limit: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("TOTAL_CAPITAL_LIMIT", "CAPITAL_POOL", "total_capital_limit"),
        description="Unified Capital Pool shared ceiling across all strategy bots (None = unconstrained/dynamic).",
    )
    trading_capital_pool: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("CAPITAL_POOL", "TRADING_CAPITAL_POOL", "trading_capital_pool"),
        description="Alias for unified capital pool.",
    )
    order_size_inr: float = Field(
        default=DEFAULT_ORDER_AMOUNT_INR,
        validation_alias=AliasChoices("ORDER_SIZE_INR", "DEFAULT_TRADE_AMOUNT", "order_size_inr"),
        description="Standard micro-order allocation (defaults to ₹200).",
    )
    max_concurrent_positions: int = Field(
        default=10,
        validation_alias=AliasChoices("MAX_CONCURRENT_POSITIONS", "max_concurrent_positions"),
        description="Maximum concurrent fleet-wide open positions.",
    )
    enforce_single_coin_lock: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENFORCE_SINGLE_COIN_LOCK", "enforce_single_coin_lock"),
        description="Enforce single-position asset lock across all strategies.",
    )

    # Master & Separated CoinDCX API Credentials (P0-05 Security Separation)
    coindcx_api_key:          Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_API_KEY", "coindcx_api_key"))
    coindcx_api_secret:       Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_API_SECRET", "coindcx_api_secret"))
    coindcx_live_api_key:     Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_LIVE_API_KEY", "coindcx_live_api_key"))
    coindcx_live_api_secret:  Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_LIVE_API_SECRET", "coindcx_live_api_secret"))
    coindcx_paper_api_key:    Optional[str] = Field(default="paper_key_demo", validation_alias=AliasChoices("COINDCX_PAPER_API_KEY", "coindcx_paper_api_key"))
    coindcx_paper_api_secret: Optional[str] = Field(default="paper_secret_demo", validation_alias=AliasChoices("COINDCX_PAPER_API_SECRET", "coindcx_paper_api_secret"))

    # Strategy bot capital limits. 0 means no separate bot ceiling; the shared
    # pool (when configured) remains the only capital limit.
    ste_capital_limit:   float = Field(default=0.0,  alias="STE_CAPITAL_LIMIT")
    hda_capital_limit:   float = Field(default=0.0,  alias="HDA_CAPITAL_LIMIT")
    vcp_capital_limit:   float = Field(default=0.0,  alias="VCP_CAPITAL_LIMIT")
    bbs_capital_limit:   float = Field(default=0.0,  alias="BBS_CAPITAL_LIMIT")

    # ── Trade sizing & bot limits (Phase 5 / Unified Fleet) ───────────────────
    v2_default_trade_amount_ste: float = Field(default=200.0, alias="STE_TRADE_AMOUNT")
    v2_default_trade_amount_hda: float = Field(default=200.0, alias="HDA_TRADE_AMOUNT")
    v2_default_trade_amount_vcp: float = Field(default=200.0, alias="VCP_TRADE_AMOUNT")
    v2_default_trade_amount_bbs: float = Field(default=200.0, alias="BBS_TRADE_AMOUNT")
    v2_max_positions_ste:        int   = Field(default=10,    alias="STE_MAX_POSITIONS")
    v2_max_positions_hda:        int   = Field(default=10,    alias="HDA_MAX_POSITIONS")
    v2_max_positions_vcp:        int   = Field(default=10,    alias="VCP_MAX_POSITIONS")
    v2_max_positions_bbs:        int   = Field(default=10,    alias="BBS_MAX_POSITIONS")
    v2_max_consecutive_losses:   int   = Field(default=5,     description="Max consecutive losses before circuit breaker trips.")
    v2_max_drawdown_pct:         float = Field(default=10.0,  description="Max daily drawdown pct before breaker trips.")

    # ── Scanner ───────────────────────────────────────────────────────────────
    v2_scanner_poll_interval: int = Field(
        default=60,
        description="Seconds between scanner polls.",
    )
    v2_scanner_signal_ttl: int = Field(
        default=300,
        description="Seconds a signal remains live after generation.",
    )
    v2_scanner_base_url: str = Field(
        default="http://localhost:5000/api/v1/scanner",
        description="Base URL of the V1 scanner HTTP API.",
    )
    v2_scanner_min_priority: str = Field(
        default="Medium",
        description="Minimum priority to persist (Elite|High|Medium|Watch|Ignore).",
    )
    v2_scanner_max_signals: int = Field(
        default=2,
        description="Maximum high-conviction signals allowed per scanner cycle (default 2).",
    )
    v2_scanner_strict_confluence_threshold: int = Field(
        default=85,
        description="Minimum confluence score (0-100) required to accept a signal.",
    )
    v2_scanner_dynamic_threshold_min: int = Field(
        default=80,
        description="Minimum dynamic C2 threshold bound.",
    )
    v2_scanner_dynamic_threshold_max: int = Field(
        default=92,
        description="Maximum dynamic C2 threshold bound.",
    )
    # B1 Composite Ranking Weights
    scanner_ranking_weight_volume: float = Field(
        default=0.40,
        description="Weight for 24h volume in top-N composite ranking.",
    )
    scanner_ranking_weight_liquidity: float = Field(
        default=0.35,
        description="Weight for liquidity/spread in top-N composite ranking.",
    )
    scanner_ranking_weight_volatility: float = Field(
        default=0.25,
        description="Weight for ATR/volatility in top-N composite ranking.",
    )
    scanner_ranking_top_n: int = Field(
        default=50,
        description="Top N coins selected after composite ranking.",
    )
    scanner_max_spread_pct: float = Field(
        default=2.0,
        description="Maximum bid/ask spread percentage allowed before candle fetches.",
    )
    # B2 Filter Cascade Thresholds
    scanner_min_24h_volume: float = Field(
        default=50000.0,
        description="Minimum 24h volume in INR for candidate coins.",
    )
    scanner_max_price_change_pct: float = Field(
        default=25.0,
        description="Maximum absolute 24h price change % to reject pump/dump moves.",
    )
    scanner_min_atr_pct: float = Field(
        default=0.5,
        description="Minimum ATR % of price (volatility sanity floor).",
    )
    scanner_max_atr_pct: float = Field(
        default=12.0,
        description="Maximum ATR % of price (volatility sanity ceiling).",
    )
    v2_scanner_market_sentiment_enabled: bool = Field(
        default=True,
        description="Enable BTC/ETH Market Sentiment Layer.",
    )
    v2_scanner_news_filter_enabled: bool = Field(
        default=True,
        description="Enable News & Risk Event Filtering Layer.",
    )
    v2_post_exit_cooldown_seconds: int = Field(
        default=900,
        description="Post-exit cooldown window in seconds (default 900s / 15m) preventing immediate re-entry on the same coin.",
    )

    # ── WebSocket ─────────────────────────────────────────────────────────────
    v2_ws_heartbeat_interval: int = Field(default=15)
    v2_ws_max_connections:    int = Field(default=50)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    v2_metrics_snapshot_interval: int = Field(default=60)
    v2_health_check_interval:     int = Field(default=30)
    v2_event_log_retention_days:  int = Field(default=30)

    # ── Notification & Telegram Interactive C2 ───────────────────────────────
    alert_bot_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ALERT_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "alert_bot_token"),
    )
    alert_chat_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ALERT_CHAT_ID", "TELEGRAM_CHAT_ID", "alert_chat_id"),
    )
    telegram_interactive_enabled: bool = Field(
        default=True,
        description="Enable interactive Telegram polling interface (C2 bot).",
    )
    telegram_allowed_chat_ids: Optional[str] = Field(
        default=None,
        description="Comma-separated whitelist of allowed Telegram chat/user IDs.",
    )

    # ── AI Intelligence (Phase 4) ─────────────────────────────────────────────
    gemini_api_key:                         Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    v2_ai_enabled:                          bool          = Field(default=True, description="Enable AI Intelligence Layer.")
    v2_ai_model:                            str           = Field(default="gemini-2.5-flash", description="Gemini model identifier.")
    v2_ai_min_priority:                     str           = Field(default="Medium", description="Min signal priority to trigger AI evaluation.")
    v2_ai_confidence_threshold:             int           = Field(default=70, description="Confidence threshold (0-100) to confirm trade signals.")
    v2_ai_timeout_seconds:                  float         = Field(default=10.0, description="Timeout in seconds for AI API calls.")
    v2_ai_max_retries:                      int           = Field(default=2, description="Max retries on AI call failures.")
    v2_ai_circuit_breaker_threshold:        int           = Field(default=3, description="Consecutive Gemini failures before circuit breaker trips to OPEN.")
    v2_ai_circuit_breaker_cooldown_seconds: float         = Field(default=60.0, description="Cooldown seconds before circuit breaker probes HALF_OPEN.")

    # ── Auth (shared with V1) ─────────────────────────────────────────────────
    dashboard_api_key: Optional[str] = Field(
        default="alpha-prod-key",
        validation_alias=AliasChoices("DASHBOARD_API_KEY", "dashboard_api_key"),
    )
    dashboard_security_password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "DASHBOARD_SECURITY_PASSWORD",
            "dashboard_security_password",
        ),
        description="Optional operator password required for live-mode transitions.",
    )

    # ── Network & Server Bindings ─────────────────────────────────────────────
    v2_port: int = Field(
        default=5001,
        validation_alias=AliasChoices("V2_PORT", "PORT", "v2_port"),
        description="Port for the FastAPI app.",
    )
    v2_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("V2_HOST", "HOST", "v2_host"),
        description="Host address for the FastAPI app.",
    )

    # ── Canonical Fields ──────────────────────────────────────────────────────
    deployment_mode: str = Field(
        default="PAPER",
        validation_alias=AliasChoices("DEPLOYMENT_MODE", "V2_DEPLOYMENT_MODE", "deployment_mode", "v2_deployment_mode"),
        description="Execution mode: PAPER, LIVE_MICROCASH, SHADOW, etc.",
    )
    websocket_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("WEBSOCKET_ENABLED", "V2_WEBSOCKET_ENABLED", "websocket_enabled", "v2_websocket_enabled"),
    )
    shadow_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("SHADOW_MODE", "V2_SHADOW_MODE", "shadow_mode", "v2_shadow_mode"),
        description="Run shadow execution alongside live/paper.",
    )
    trading_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("TRADING_ENABLED", "V2_TRADING_ENABLED", "trading_enabled", "v2_trading_enabled"),
        description="Master switch enabling live and automated trade dispatch.",
    )
    execution_timeout: float = Field(
        default=30.0,
        validation_alias=AliasChoices("EXECUTION_TIMEOUT", "V2_EXECUTION_TIMEOUT", "execution_timeout", "v2_execution_timeout"),
        description="Timeout in seconds for order execution and verification operations.",
    )

    # ── Backward Compatibility Properties for v2_* fields ────────────────────
    @property
    def v2_trading_enabled(self) -> bool:
        return self.trading_enabled

    @property
    def v2_deployment_mode(self) -> str:
        return self.deployment_mode

    @property
    def v2_shadow_mode(self) -> bool:
        return self.shadow_mode

    @property
    def v2_execution_timeout(self) -> float:
        return self.execution_timeout

    @property
    def v2_db_path(self) -> str:
        return self.db_path

    @property
    def v2_websocket_enabled(self) -> bool:
        return self.websocket_enabled

    def __setattr__(self, name: str, value: Any) -> None:
        if name in LEGACY_FIELD_MAP:
            super().__setattr__(LEGACY_FIELD_MAP[name], value)
            return
        if name == "v2_websocket_enabled":
            super().__setattr__("websocket_enabled", value)
            return
        super().__setattr__(name, value)

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> AppConfig:
        if update:
            normalized_update = {}
            for k, v in update.items():
                target_key = LEGACY_FIELD_MAP.get(k, k)
                if target_key == "v2_websocket_enabled":
                    target_key = "websocket_enabled"
                normalized_update[target_key] = v
            update = normalized_update
        return super().model_copy(update=update, deep=deep)

    @property
    def host(self) -> str:
        return self.v2_host

    @property
    def port(self) -> int:
        return self.v2_port

    @property
    def capital_pool(self) -> Optional[float]:
        return self.total_capital_limit if self.total_capital_limit is not None else self.trading_capital_pool

    @property
    def telegram_bot_token(self) -> Optional[str]:
        return self.alert_bot_token

    @property
    def telegram_chat_id(self) -> Optional[str]:
        return self.alert_chat_id

    @field_validator("order_size_inr")
    @classmethod
    def validate_order_size(cls, v: float) -> float:
        return max(200.0, float(v))

    @field_validator("v2_scanner_min_priority", "v2_ai_min_priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        valid = {"Elite", "High", "Medium", "Watch", "Ignore"}
        if v not in valid:
            raise ValueError(f"Priority must be one of {valid}")
        return v

    def validate_live_security(self) -> None:
        """
        Validate security requirements for LIVE trading mode.
        Raises SecurityConfigError if LIVE mode is active without non-dummy API keys or operator password.
        """
        try:
            from core.exceptions import SecurityConfigError
        except ImportError:
            from v2.core.exceptions import SecurityConfigError

        dep_mode = (self.deployment_mode or "").upper()
        if dep_mode == "LIVE_MICROCASH" and self.trading_enabled:
            DUMMY_VALUES = {
                "DUMMY_KEY", "SAMPLE_KEY", "ALPHA-PROD-KEY", "TEST", "SECRET",
                "12345", "CHANGE_ME", "DUMMY_SECRET", "DEMO", "SAMPLE", ""
            }

            key = (self.coindcx_live_api_key or self.coindcx_api_key or "").strip()
            secret = (self.coindcx_live_api_secret or self.coindcx_api_secret or "").strip()
            pwd = (self.dashboard_security_password or "").strip()

            if not key or key.upper() in DUMMY_VALUES:
                raise SecurityConfigError("LIVE trading mode blocked: valid non-dummy CoinDCX Live API key is required.")

            if not secret or secret.upper() in DUMMY_VALUES:
                raise SecurityConfigError("LIVE trading mode blocked: valid non-dummy CoinDCX Live API secret is required.")

            if not pwd or pwd.upper() in DUMMY_VALUES:
                raise SecurityConfigError("LIVE trading mode blocked: valid non-empty DASHBOARD_SECURITY_PASSWORD is required.")

    def get_sanitized_config_dict(self) -> dict:
        """Return dict of config values with secret keys safely redacted and legacy aliases supported."""
        data = self.model_dump()
        # Include legacy aliases for dashboard/API backward compatibility
        for legacy_key, canonical_key in LEGACY_FIELD_MAP.items():
            if canonical_key in data:
                data[legacy_key] = data[canonical_key]
        if "websocket_enabled" in data:
            data["v2_websocket_enabled"] = data["websocket_enabled"]

        SECRET_KEYS = {
            "coindcx_api_secret", "coindcx_live_api_secret", "coindcx_paper_api_secret",
            "coindcx_api_key", "coindcx_live_api_key", "alert_bot_token", "gemini_api_key",
            "dashboard_security_password", "dashboard_api_key"
        }
        for k, v in data.items():
            if k in SECRET_KEYS and v:
                data[k] = "***REDACTED***"
        return data

    def apply_override(self, override_path: str | None = None) -> "AppConfig":
        """
        Return a copy of this config with hot-reloadable keys overridden
        from *override_path* (defaults to data/config_override.json or v2/data/config_override.json).
        """
        HOT_RELOAD_KEYS = {
            "deployment_mode",
            "v2_deployment_mode",
            "websocket_enabled",
            "v2_websocket_enabled",
            "shadow_mode",
            "v2_shadow_mode",
            "trading_enabled",
            "v2_trading_enabled",
            "execution_timeout",
            "v2_execution_timeout",
            "db_path",
            "v2_db_path",
            "v2_scanner_poll_interval",
            "v2_scanner_signal_ttl",
            "v2_metrics_snapshot_interval",
            "v2_health_check_interval",
            "v2_ai_enabled",
            "v2_ai_model",
            "v2_ai_min_priority",
            "v2_ai_confidence_threshold",
            "v2_ai_timeout_seconds",
            "v2_ai_max_retries",
            "alert_bot_token",
            "alert_chat_id",
            "order_size_inr",
            "total_capital_limit",
            "trading_capital_pool",
        }
        candidates = [
            Path(override_path) if override_path else None,
            Path("data/config_override.json"),
            Path("v2/data/config_override.json"),
        ]
        target_path: Optional[Path] = None
        for p in candidates:
            if p and p.exists():
                target_path = p
                break

        if not target_path or not target_path.exists():
            return self
        try:
            overrides = json.loads(target_path.read_text(encoding="utf-8"))
        except Exception:
            return self

        raw_updates = {k: v for k, v in overrides.items() if k in HOT_RELOAD_KEYS}
        updates: dict[str, Any] = {}
        for k, v in raw_updates.items():
            target_key = LEGACY_FIELD_MAP.get(k, k)
            updates[target_key] = v

        if "order_size_inr" in updates:
            updates["order_size_inr"] = max(200.0, float(updates["order_size_inr"]))
        if not updates:
            return self
        return self.model_copy(update=updates)

    @classmethod
    def save_runtime_overrides(cls, overrides: dict[str, Any], override_path: Optional[str] = None) -> AppConfig:
        """Persist runtime overrides to config_override.json and reload cache."""
        path = Path(override_path or "data/config_override.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        elif Path("v2/data/config_override.json").exists():
            try:
                existing = json.loads(Path("v2/data/config_override.json").read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        if "order_size_inr" in overrides:
            overrides["order_size_inr"] = max(200.0, float(overrides["order_size_inr"]))
        existing.update(overrides)
        if "order_size_inr" in existing:
            existing["order_size_inr"] = max(200.0, float(existing["order_size_inr"]))
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        invalidate_config()
        return cls().apply_override(override_path=str(path))


# Canonical alias for backward compatibility
V2Config = AppConfig


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """
    Return the singleton AppConfig instance with runtime overrides applied.

    Call invalidate_config() to force a reload (e.g. in tests).
    """
    cfg = AppConfig()
    return cfg.apply_override()


def invalidate_config() -> None:
    """Clear the cached config singleton (for tests and hot-reload)."""
    get_config.cache_clear()
