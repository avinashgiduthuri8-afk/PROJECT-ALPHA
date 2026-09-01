"""
CoinDCX Unified Capital Pool & Execution Manager Architecture.

Migrated from isolated sub-accounts to a Single Unified Capital Pool (₹10,000 shared ceiling)
with standardized micro-order allocation (₹200 per trade), master HMAC-SHA256 request signing,
order book precision rounding, mandatory ₹100 minimum notional enforcement, and live REST order dispatch.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from v2.core.logging import get_logger
from v2.core.types import BotName
from .precision_rules import round_price, round_qty, validate_order_notional

logger = get_logger("v2.trading.execution_manager")


@dataclass
class SubAccountConfig:
    bot_name: BotName
    subaccount_id: str
    api_key: str
    api_secret: str
    allocated_wallet_inr: float = 10000.0
    max_positions: int = 10
    default_trade_amount_inr: float = 200.0
    allowed_pairs: List[str] = field(default_factory=list)


class CoinDCXSubAccountClient:
    """
    Authenticated execution client managing orders under the Unified Capital Pool.
    Signs all authenticated endpoints using CoinDCX HMAC-SHA256 standard.
    """

    def __init__(
        self,
        config: SubAccountConfig,
        base_url: str = "https://api.coindcx.com",
        shared_pool_lock: Optional[threading.RLock] = None,
        shared_state: Optional[Dict[str, float]] = None,
        timeout: float = 10.0,
    ) -> None:
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._lock = shared_pool_lock or threading.RLock()
        self._shared_state = shared_state
        if self._shared_state is None:
            self._shared_state = {
                "wallet_balance_inr": config.allocated_wallet_inr,
                "deployed_capital_inr": 0.0,
            }
        self._open_orders: Dict[str, Dict[str, Any]] = {}

    @property
    def bot_name(self) -> BotName:
        return self.config.bot_name

    @property
    def subaccount_id(self) -> str:
        return self.config.subaccount_id

    @property
    def wallet_balance_inr(self) -> float:
        with self._lock:
            return self._shared_state["wallet_balance_inr"]

    @property
    def available_balance_inr(self) -> float:
        with self._lock:
            return max(0.0, self._shared_state["wallet_balance_inr"] - self._shared_state["deployed_capital_inr"])

    def generate_auth_headers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate HMAC-SHA256 authentication headers for CoinDCX API.
        Headers:
          - X-AUTH-APIKEY: API Key
          - X-AUTH-SIGNATURE: HMAC-SHA256 hex digest of payload JSON
        """
        if "timestamp" not in payload:
            payload["timestamp"] = int(time.time() * 1000)

        json_body = json.dumps(payload, separators=(",", ":"))
        secret_bytes = self.config.api_secret.encode("utf-8")
        signature = hmac.new(secret_bytes, json_body.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self.config.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

    # ── Synchronous / Simulated Order Placement ───────────────────────────────

    def place_order(
        self,
        pair: str,
        side: str,
        price: float,
        qty: float,
        order_type: str = "limit_order",
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place an order through the unified execution client with discrete rounding.
        """
        with self._lock:
            # 1. Discrete tick & lot precision rounding
            rounded_price = round_price(pair, price)
            rounded_qty = round_qty(pair, qty)
            notional = rounded_price * rounded_qty

            # 2. Hard validation: Minimum order value (INR 100) and min lot
            if not validate_order_notional(pair, rounded_price, rounded_qty):
                logger.warning(
                    "Order rejected by precision gate: notional INR %.2f below INR 100 or invalid qty %.6f for %s",
                    notional, rounded_qty, pair,
                )
                return {
                    "success": False,
                    "error": "ORDER_NOTIONAL_BELOW_MINIMUM",
                    "message": f"Order notional INR {notional:.2f} is below minimum INR 100.00 or invalid lot size",
                }

            # 3. Capital pool balance check
            if side.upper() == "BUY" and notional > self.available_balance_inr:
                logger.warning(
                    "Order rejected: Insufficient capital pool funds (Required INR %.2f > Available INR %.2f)",
                    notional, self.available_balance_inr,
                )
                return {
                    "success": False,
                    "error": "INSUFFICIENT_SUBACCOUNT_BALANCE",
                    "message": f"Required INR {notional:.2f} exceeds available capital pool balance INR {self.available_balance_inr:.2f}",
                }

            # 4. Generate payload and mock/real order ID
            order_id = client_order_id or f"ORD_{self.subaccount_id}_{int(time.time()*1000)}"
            payload = {
                "side": side.lower(),
                "order_type": order_type,
                "market": pair.replace("/", "").upper(),
                "price_per_unit": rounded_price,
                "total_quantity": rounded_qty,
                "timestamp": int(time.time() * 1000),
                "client_order_id": order_id,
            }

            headers = self.generate_auth_headers(payload)

            # Update shared capital tracking
            if side.upper() == "BUY":
                self._shared_state["deployed_capital_inr"] += notional

            order_record = {
                "order_id": order_id,
                "subaccount_id": self.subaccount_id,
                "bot_name": self.bot_name.value,
                "pair": pair,
                "side": side.upper(),
                "price": rounded_price,
                "qty": rounded_qty,
                "notional_inr": notional,
                "status": "FILLED",
                "auth_headers_verified": bool(headers.get("X-AUTH-SIGNATURE")),
                "timestamp": payload["timestamp"],
            }
            self._open_orders[order_id] = order_record

            logger.info(
                "[%s] Order dispatched successfully: %s %s @ INR %.2f (Qty: %s, Notional: INR %.2f)",
                self.subaccount_id, side.upper(), pair, rounded_price, rounded_qty, notional,
            )
            return {"success": True, "order": order_record}

    def close_position_fill(self, notional_returned: float, realized_pnl: float) -> None:
        """Update capital pool balance when a position closes."""
        with self._lock:
            self._shared_state["deployed_capital_inr"] = max(0.0, self._shared_state["deployed_capital_inr"] - notional_returned)
            self._shared_state["wallet_balance_inr"] += realized_pnl

    # ── Live Network Execution & Diagnostic REST Endpoints ────────────────────

    async def get_balances(
        self,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Query real CoinDCX user balances endpoint:
        POST https://api.coindcx.com/exchange/v1/users/balances
        """
        payload = {"timestamp": int(time.time() * 1000)}
        headers = self.generate_auth_headers(payload)
        url = f"{self.base_url}/exchange/v1/users/balances"

        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                balances_raw = resp.json()
                inr_balance = 0.0
                inr_locked = 0.0
                for b in balances_raw:
                    if b.get("currency") == "INR":
                        inr_balance = float(b.get("balance", 0.0))
                        inr_locked = float(b.get("locked_balance", 0.0))
                        break

                return {
                    "success": True,
                    "status_code": 200,
                    "inr_balance": inr_balance,
                    "inr_locked": inr_locked,
                    "balances": balances_raw,
                }
            elif resp.status_code == 401:
                logger.error("[%s] CoinDCX Authentication Failed (HTTP 401): %s", self.subaccount_id, resp.text)
                return {
                    "success": False,
                    "status_code": 401,
                    "error": "AUTH_FAILED",
                    "message": "Invalid API Key or HMAC Signature",
                    "details": resp.text,
                }
            elif resp.status_code == 429:
                logger.warning("[%s] CoinDCX Rate Limit Exceeded (HTTP 429)", self.subaccount_id)
                return {
                    "success": False,
                    "status_code": 429,
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded (HTTP 429)",
                }
            else:
                logger.error("[%s] Balance fetch error (HTTP %d): %s", self.subaccount_id, resp.status_code, resp.text)
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": "EXCHANGE_ERROR",
                    "message": f"CoinDCX returned HTTP {resp.status_code}",
                    "details": resp.text,
                }
        except Exception as e:
            logger.error("[%s] Error connecting to CoinDCX balance API: %s", self.subaccount_id, e)
            return {
                "success": False,
                "status_code": 0,
                "error": "NETWORK_ERROR",
                "message": str(e),
            }
        finally:
            if owns_client:
                await http.aclose()

    async def place_live_order(
        self,
        pair: str,
        side: str,
        price: float,
        qty: float,
        order_type: str = "limit_order",
        client_order_id: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch a live authenticated order to CoinDCX:
        POST https://api.coindcx.com/exchange/v1/orders/create
        """
        # 1. Round price and qty
        rounded_price = round_price(pair, price)
        rounded_qty = round_qty(pair, qty)
        notional = rounded_price * rounded_qty

        # 2. Hard validation: Minimum order value (INR 100) and min lot
        if not validate_order_notional(pair, rounded_price, rounded_qty):
            return {
                "success": False,
                "error": "ORDER_NOTIONAL_BELOW_MINIMUM",
                "message": f"Order notional INR {notional:.2f} is below minimum INR 100.00",
            }

        # 3. Capital pool check
        if side.upper() == "BUY" and notional > self.available_balance_inr:
            return {
                "success": False,
                "error": "INSUFFICIENT_SUBACCOUNT_BALANCE",
                "message": f"Required INR {notional:.2f} exceeds available capital pool balance INR {self.available_balance_inr:.2f}",
            }

        order_id = client_order_id or f"ORD_{self.subaccount_id}_{int(time.time()*1000)}"
        payload = {
            "side": side.lower(),
            "order_type": order_type,
            "market": pair.replace("/", "").upper(),
            "price_per_unit": rounded_price,
            "total_quantity": rounded_qty,
            "timestamp": int(time.time() * 1000),
            "client_order_id": order_id,
        }

        headers = self.generate_auth_headers(payload)
        url = f"{self.base_url}/exchange/v1/orders/create"

        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                with self._lock:
                    if side.upper() == "BUY":
                        self._shared_state["deployed_capital_inr"] += notional

                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "order": data,
                    "price": rounded_price,
                    "qty": rounded_qty,
                    "notional_inr": notional,
                }
            elif resp.status_code == 401:
                return {"success": False, "status_code": 401, "error": "AUTH_FAILED", "message": "Invalid API Key or HMAC Signature"}
            elif resp.status_code == 429:
                return {"success": False, "status_code": 429, "error": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"}
            else:
                return {"success": False, "status_code": resp.status_code, "error": "ORDER_REJECTED", "details": resp.text}
        except Exception as e:
            return {"success": False, "status_code": 0, "error": "NETWORK_ERROR", "message": str(e)}
        finally:
            if owns_client:
                await http.aclose()

    async def get_order_status(
        self,
        order_id: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Query status of an active or completed order:
        POST https://api.coindcx.com/exchange/v1/orders/status
        """
        payload = {"id": order_id, "timestamp": int(time.time() * 1000)}
        headers = self.generate_auth_headers(payload)
        url = f"{self.base_url}/exchange/v1/orders/status"

        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return {"success": True, "status_code": 200, "order": resp.json()}
            return {"success": False, "status_code": resp.status_code, "error": "FETCH_FAILED", "details": resp.text}
        except Exception as e:
            return {"success": False, "status_code": 0, "error": "NETWORK_ERROR", "message": str(e)}
        finally:
            if owns_client:
                await http.aclose()

    async def cancel_order(
        self,
        order_id: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Cancel an open limit order:
        POST https://api.coindcx.com/exchange/v1/orders/cancel
        """
        payload = {"id": order_id, "timestamp": int(time.time() * 1000)}
        headers = self.generate_auth_headers(payload)
        url = f"{self.base_url}/exchange/v1/orders/cancel"

        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return {"success": True, "status_code": 200, "result": resp.json()}
            return {"success": False, "status_code": resp.status_code, "error": "CANCEL_FAILED", "details": resp.text}
        except Exception as e:
            return {"success": False, "status_code": 0, "error": "NETWORK_ERROR", "message": str(e)}
        finally:
            if owns_client:
                await http.aclose()


# Aliases for unified architecture
CoinDCXExecutionClient = CoinDCXSubAccountClient


class CoinDCXSubAccountManager:
    """
    Thread-safe Unified Capital Pool Execution Manager & Multi-Strategy Router.
    All strategy bots (STE, HDA, VCP, BBS) share the single ₹10,000 capital pool.
    """

    def __init__(self, config_path: str = "Alpha/config.json") -> None:
        self.config_path = config_path
        self._clients: Dict[BotName, CoinDCXSubAccountClient] = {}
        self._lock = threading.RLock()
        self._shared_pool_state: Dict[str, float] = {
            "wallet_balance_inr": 10000.0,
            "deployed_capital_inr": 0.0,
        }
        self._initialize_execution_pool()

    def _initialize_execution_pool(self) -> None:
        """Load configuration from Alpha/config.json or environment fallback."""
        sub_configs: Dict[str, Dict[str, Any]] = {}
        pool_limit = 10000.0
        order_size = 200.0

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sub_configs = data.get("subaccounts", data.get("strategies", {}))
                    trading_cfg = data.get("trading", {})
                    pool_limit = float(trading_cfg.get("capital_pool", data.get("total_portfolio_capital_inr", 10000.0)))
                    order_size = float(trading_cfg.get("order_size_inr", 200.0))
            except Exception as e:
                logger.error("Failed to read %s: %s", self.config_path, e)

        self._shared_pool_state["wallet_balance_inr"] = pool_limit

        # Master API Credentials
        master_api_key = os.getenv("COINDCX_API_KEY", "mock_master_key_alpha12345")
        master_api_secret = os.getenv("COINDCX_API_SECRET", "mock_master_secret_alpha67890abcdef")

        # Default strategy configurations
        defaults = {
            "STE": {
                "subaccount_id": "ALPHA_STE_01",
                "max_positions": 10,
                "default_trade_amount_inr": order_size,
                "allowed_pairs": ["BTC/INR", "ETH/INR", "SOL/INR", "AVAX/INR", "LINK/INR", "BNB/INR"],
            },
            "HDA": {
                "subaccount_id": "ALPHA_HDA_01",
                "max_positions": 10,
                "default_trade_amount_inr": order_size,
                "allowed_pairs": ["BTC/INR", "ETH/INR", "SOL/INR", "MATIC/INR", "XRP/INR", "ADA/INR"],
            },
            "VCP": {
                "subaccount_id": "ALPHA_VCP_01",
                "max_positions": 10,
                "default_trade_amount_inr": order_size,
                "allowed_pairs": ["SOL/INR", "AVAX/INR", "LINK/INR", "ADA/INR", "MATIC/INR"],
            },
            "BBS": {
                "subaccount_id": "ALPHA_BBS_01",
                "max_positions": 10,
                "default_trade_amount_inr": order_size,
                "allowed_pairs": ["BTC/INR", "ETH/INR", "SOL/INR", "DOGE/INR", "TRX/INR", "SHIB/INR"],
            },
        }

        for bot_key, bot_name in [
            ("STE", BotName.STE),
            ("HDA", BotName.HDA),
            ("VCP", BotName.VCP),
            ("BBS", BotName.BBS),
        ]:
            cfg_dict = sub_configs.get(bot_key, defaults.get(bot_key, {}))
            api_key_var = cfg_dict.get("api_key_env", "COINDCX_API_KEY")
            secret_key_var = cfg_dict.get("secret_key_env", "COINDCX_API_SECRET")

            api_key = os.getenv(api_key_var, master_api_key)
            api_secret = os.getenv(secret_key_var, master_api_secret)

            sub_cfg = SubAccountConfig(
                bot_name=bot_name,
                subaccount_id=cfg_dict.get("subaccount_id", f"ALPHA_{bot_key}_01"),
                api_key=api_key,
                api_secret=api_secret,
                allocated_wallet_inr=pool_limit,
                max_positions=int(cfg_dict.get("max_positions", 10)),
                default_trade_amount_inr=float(cfg_dict.get("default_trade_amount_inr", order_size)),
                allowed_pairs=cfg_dict.get("allowed_pairs", []),
            )
            self._clients[bot_name] = CoinDCXSubAccountClient(
                config=sub_cfg,
                shared_pool_lock=self._lock,
                shared_state=self._shared_pool_state,
            )

    def get_client(self, bot_name: BotName = BotName.STE) -> CoinDCXSubAccountClient:
        """Retrieve execution client for a bot drawing from the unified pool."""
        with self._lock:
            if bot_name not in self._clients:
                return self._clients.get(BotName.STE, list(self._clients.values())[0])
            return self._clients[bot_name]

    def get_all_subaccount_telemetry(self) -> Dict[str, Dict[str, Any]]:
        """Return live telemetry across all strategy execution routers."""
        with self._lock:
            telemetry = {}
            for bot, client in self._clients.items():
                telemetry[bot.value] = {
                    "subaccount_id": client.subaccount_id,
                    "wallet_balance_inr": client.wallet_balance_inr,
                    "available_balance_inr": client.available_balance_inr,
                    "max_positions": client.config.max_positions,
                    "default_trade_amount_inr": client.config.default_trade_amount_inr,
                    "allowed_pairs": client.config.allowed_pairs,
                }
            return telemetry

    async def check_account_connectivity(self, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
        """Diagnostic utility to verify master API credentials against CoinDCX balances."""
        master_client = self.get_client(BotName.STE)
        return await master_client.get_balances(client=client)


# Alias for unified execution manager
CoinDCXExecutionManager = CoinDCXSubAccountManager
