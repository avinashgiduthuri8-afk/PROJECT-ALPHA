"""
V2 Configuration System.

Single Pydantic BaseSettings model for all V2 configuration.
Rules:
  - No service ever calls os.getenv() directly.
  - V1 environment variables are read once at startup and stored here.
  - A subset of keys is hot-reloadable via config_override.json.
  - Capital limits require a restart to change.

Usage:
    from v2.core.config import get_config
    cfg = get_config()
    print(cfg.v2_scanner_poll_interval)
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ORDER_AMOUNT_INR: float = 200.0


class V2Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    v2_db_path: str = Field(
        default="v2/data/alpha_v2.db",
        validation_alias=AliasChoices("V2_DB_PATH", "DB_PATH", "v2_db_path"),
        description="Path to the V2 SQLite database file.",
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

    # Master CoinDCX API Credentials
    coindcx_api_key:    Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_API_KEY", "coindcx_api_key"))
    coindcx_api_secret: Optional[str] = Field(default=None, validation_alias=AliasChoices("COINDCX_API_SECRET", "coindcx_api_secret"))

    # Strategy bot capital limits (defaults to unified pool)
    ste_capital_limit:   float = Field(default=10000.0,  alias="STE_CAPITAL_LIMIT")
    hda_capital_limit:   float = Field(default=10000.0,  alias="HDA_CAPITAL_LIMIT")
    vcp_capital_limit:   float = Field(default=10000.0,  alias="VCP_CAPITAL_LIMIT")
    bbs_capital_limit:   float = Field(default=10000.0,  alias="BBS_CAPITAL_LIMIT")

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
    gemini_api_key:             Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    v2_ai_enabled:              bool          = Field(default=True, description="Enable AI Intelligence Layer.")
    v2_ai_model:                str           = Field(default="gemini-2.5-flash", description="Gemini model identifier.")
    v2_ai_min_priority:         str           = Field(default="Medium", description="Min signal priority to trigger AI evaluation.")
    v2_ai_confidence_threshold: int           = Field(default=70, description="Confidence threshold (0-100) to confirm trade signals.")
    v2_ai_timeout_seconds:      float         = Field(default=10.0, description="Timeout in seconds for AI API calls.")
    v2_ai_max_retries:          int           = Field(default=2, description="Max retries on AI call failures.")

    # ── Auth (shared with V1) ─────────────────────────────────────────────────
    dashboard_api_key: Optional[str] = Field(
        default="alpha-dev-key",
        validation_alias=AliasChoices("DASHBOARD_API_KEY", "dashboard_api_key"),
    )

    # ── Network & Server Bindings ─────────────────────────────────────────────
    v2_port: int = Field(
        default=5001,
        validation_alias=AliasChoices("V2_PORT", "PORT", "v2_port"),
        description="Port for the V2 FastAPI app.",
    )
    v2_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("V2_HOST", "HOST", "v2_host"),
        description="Host address for the V2 FastAPI app.",
    )

    # ── Feature flags & Deployment Mode ──────────────────────────────────────
    v2_deployment_mode:   str  = Field(default="SHADOW", validation_alias=AliasChoices("V2_DEPLOYMENT_MODE", "DEPLOYMENT_MODE", "v2_deployment_mode"))
    v2_websocket_enabled: bool = Field(default=False)
    v2_shadow_mode:       bool = Field(default=False)
    v2_trading_enabled:   bool = Field(
        default=False,
        validation_alias=AliasChoices("V2_TRADING_ENABLED", "TRADING_ENABLED", "v2_trading_enabled"),
    )

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

    @field_validator("v2_scanner_min_priority", "v2_ai_min_priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        valid = {"Elite", "High", "Medium", "Watch", "Ignore"}
        if v not in valid:
            raise ValueError(f"Priority must be one of {valid}")
        return v

    def apply_override(self, override_path: str | None = None) -> "V2Config":
        """
        Return a copy of this config with hot-reloadable keys overridden
        from *override_path* (defaults to v2/data/config_override.json).

        Only the keys listed in HOT_RELOAD_KEYS are applied; all others
        are ignored so capital limits cannot be changed at runtime.
        """
        HOT_RELOAD_KEYS = {
            "v2_deployment_mode",
            "v2_websocket_enabled",
            "v2_shadow_mode",
            "v2_trading_enabled",
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
        path = Path(override_path or "v2/data/config_override.json")
        if not path.exists():
            return self
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self

        updates = {k: v for k, v in overrides.items() if k in HOT_RELOAD_KEYS}
        if not updates:
            return self
        return self.model_copy(update=updates)

    @classmethod
    def save_runtime_overrides(cls, overrides: dict[str, Any], override_path: Optional[str] = None) -> V2Config:
        """Persist runtime overrides to config_override.json and reload cache."""
        path = Path(override_path or "v2/data/config_override.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        existing.update(overrides)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        invalidate_config()
        return get_config()


@lru_cache(maxsize=1)
def get_config() -> V2Config:
    """
    Return the singleton V2Config instance with runtime overrides applied.

    Call invalidate_config() to force a reload (e.g. in tests).
    """
    cfg = V2Config()
    return cfg.apply_override()


def invalidate_config() -> None:
    """Clear the cached config singleton (for tests and hot-reload)."""
    get_config.cache_clear()
