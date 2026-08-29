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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        description="Path to the V2 SQLite database file.",
    )

    # ── Capital limits (Isolated Sub-Account Wallets) ──────────────────────────
    total_capital_limit: float = Field(default=100000.0, alias="TOTAL_CAPITAL_LIMIT")
    ste_capital_limit:   float = Field(default=35000.0,  alias="STE_CAPITAL_LIMIT")
    hda_capital_limit:   float = Field(default=30000.0,  alias="HDA_CAPITAL_LIMIT")
    vcp_capital_limit:   float = Field(default=15000.0,  alias="VCP_CAPITAL_LIMIT")
    bbs_capital_limit:   float = Field(default=20000.0,  alias="BBS_CAPITAL_LIMIT")

    # ── Trade sizing & bot limits (Phase 5 / Sub-Account Fleet) ───────────────
    v2_default_trade_amount_ste: float = Field(default=500.0, alias="STE_TRADE_AMOUNT")
    v2_default_trade_amount_hda: float = Field(default=500.0, alias="HDA_TRADE_AMOUNT")
    v2_default_trade_amount_vcp: float = Field(default=500.0, alias="VCP_TRADE_AMOUNT")
    v2_default_trade_amount_bbs: float = Field(default=400.0, alias="BBS_TRADE_AMOUNT")
    v2_max_positions_ste:        int   = Field(default=3,     alias="STE_MAX_POSITIONS")
    v2_max_positions_hda:        int   = Field(default=3,     alias="HDA_MAX_POSITIONS")
    v2_max_positions_vcp:        int   = Field(default=2,     alias="VCP_MAX_POSITIONS")
    v2_max_positions_bbs:        int   = Field(default=4,     alias="BBS_MAX_POSITIONS")
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

    # ── WebSocket ─────────────────────────────────────────────────────────────
    v2_ws_heartbeat_interval: int = Field(default=15)
    v2_ws_max_connections:    int = Field(default=50)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    v2_metrics_snapshot_interval: int = Field(default=60)
    v2_health_check_interval:     int = Field(default=30)
    v2_event_log_retention_days:  int = Field(default=30)

    # ── Notification ──────────────────────────────────────────────────────────
    alert_bot_token: Optional[str] = Field(default=None, alias="ALERT_BOT_TOKEN")
    alert_chat_id:   Optional[str] = Field(default=None, alias="ALERT_CHAT_ID")

    # ── AI Intelligence (Phase 4) ─────────────────────────────────────────────
    gemini_api_key:             Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    v2_ai_enabled:              bool          = Field(default=True, description="Enable AI Intelligence Layer.")
    v2_ai_model:                str           = Field(default="gemini-2.5-flash", description="Gemini model identifier.")
    v2_ai_min_priority:         str           = Field(default="Medium", description="Min signal priority to trigger AI evaluation.")
    v2_ai_confidence_threshold: int           = Field(default=70, description="Confidence threshold (0-100) to confirm trade signals.")
    v2_ai_timeout_seconds:      float         = Field(default=10.0, description="Timeout in seconds for AI API calls.")
    v2_ai_max_retries:          int           = Field(default=2, description="Max retries on AI call failures.")

    # ── Auth (shared with V1) ─────────────────────────────────────────────────
    dashboard_api_key: Optional[str] = Field(default=None, alias="DASHBOARD_API_KEY")

    # ── V2 port ───────────────────────────────────────────────────────────────
    v2_port: int = Field(default=5001, description="Port for the V2 FastAPI app.")
    v2_host: str = Field(default="0.0.0.0")

    # ── Feature flags (all off by default) ───────────────────────────────────
    v2_websocket_enabled: bool = Field(default=False)
    v2_shadow_mode:       bool = Field(default=False)
    v2_trading_enabled:   bool = Field(default=False)

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
        }
        path = Path(override_path or "v2/data/config_override.json")
        if not path.exists():
            return self
        try:
            overrides = json.loads(path.read_text())
        except Exception:
            return self

        data = self.model_dump()
        for key, val in overrides.items():
            if key in HOT_RELOAD_KEYS:
                data[key] = val

        return V2Config.model_validate(data)


@lru_cache(maxsize=1)
def get_config() -> V2Config:
    """
    Return the singleton V2Config instance.

    Call invalidate_config() to force a reload (e.g. in tests).
    """
    return V2Config()


def invalidate_config() -> None:
    """Clear the cached config singleton (for tests and hot-reload)."""
    get_config.cache_clear()
