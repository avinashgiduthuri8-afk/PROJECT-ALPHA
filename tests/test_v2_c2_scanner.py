"""
Tests for C2 High-Conviction Crypto Scanner Architecture:
  - 5-Layer Evaluation Engine (Chart, Indicators, Sentiment, News, Confluence)
  - Strict Rejection Gate (Default to REJECT unless all layers pass)
  - Maximum 1–2 Signals Output Limit (Quality > Quantity)
  - 0 Signal Output on weak or conflicting market conditions
  - Integration with ScannerService
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from v2.core.types import MarketState, Priority, RiskLevel, Signal
from v2.services.scanner_service.confluence_engine import (
    ChartStructureEvaluator,
    ConfluenceEngine,
    IndicatorEvaluator,
    MarketSentimentEvaluator,
    NewsEventsEvaluator,
)


def _make_test_signal(
    coin: str = "BTC",
    score: int = 90,
    priority: Priority = Priority.ELITE,
    market_state: MarketState = MarketState.BREAKOUT,
    mtf_alignment: bool = True,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> Signal:
    now = datetime.now(timezone.utc)
    return Signal(
        id=f"sig_{coin}_1",
        coin=coin,
        pair=f"{coin}_USDT",
        market_state=market_state,
        opportunity_type=OppType.MOMENTUM_TRADE if hasattr(OppType, 'MOMENTUM_TRADE') else "momentum_trade",
        priority=priority,
        risk_level=risk_level,
        score=score,
        confidence=90,
        coin_class="A",
        mtf_alignment=mtf_alignment,
        generated_at=now,
        expires_at=now,
    )


from v2.core.types import OppType


class TestChartStructureEvaluator:

    def test_breakout_bull_trend_high_score(self):
        evaluator = ChartStructureEvaluator()
        sig = _make_test_signal(market_state=MarketState.BREAKOUT)
        res = evaluator.evaluate({}, sig)
        assert res.passed is True
        assert res.score >= 80

    def test_downtrend_causes_rejection(self):
        evaluator = ChartStructureEvaluator()
        sig = _make_test_signal(market_state=MarketState.DOWNTREND)
        res = evaluator.evaluate({}, sig)
        assert res.passed is False
        assert len(res.reasons) > 0


class TestIndicatorEvaluator:

    def test_mtf_alignment_required(self):
        evaluator = IndicatorEvaluator()
        sig_aligned = _make_test_signal(mtf_alignment=True, score=90)
        res_aligned = evaluator.evaluate({}, sig_aligned)
        assert res_aligned.passed is True

        sig_unaligned = _make_test_signal(mtf_alignment=False, score=90)
        res_unaligned = evaluator.evaluate({}, sig_unaligned)
        assert res_unaligned.passed is False
        assert "multi-timeframe" in res_unaligned.reasons[0].lower()


class TestMarketSentimentEvaluator:

    def test_risk_on_bullish_btc_passes(self):
        evaluator = MarketSentimentEvaluator()
        evaluator.update_market_state(btc_trend="BULLISH", eth_trend="BULLISH", market_regime="RISK_ON")
        sig = _make_test_signal()
        res = evaluator.evaluate({}, sig)
        assert res.passed is True

    def test_risk_off_causes_rejection(self):
        evaluator = MarketSentimentEvaluator()
        evaluator.update_market_state(btc_trend="BEARISH", eth_trend="BEARISH", market_regime="RISK_OFF")
        sig = _make_test_signal()
        res = evaluator.evaluate({}, sig)
        assert res.passed is False
        assert any("risk_off" in r.lower() for r in res.reasons)


class TestNewsEventsEvaluator:

    def test_clean_news_passes(self):
        evaluator = NewsEventsEvaluator()
        sig = _make_test_signal()
        res = evaluator.evaluate({"news": {"has_negative_news": False}}, sig)
        assert res.passed is True

    def test_negative_news_causes_rejection(self):
        evaluator = NewsEventsEvaluator()
        sig = _make_test_signal()
        res = evaluator.evaluate({"news": {"has_negative_news": True}}, sig)
        assert res.passed is False
        assert "negative news" in res.reasons[0].lower()


class TestConfluenceEngine:

    def test_strict_rejection_mentality(self):
        engine = ConfluenceEngine(strict_threshold=85, max_signals=2)
        engine.update_market_sentiment("BULLISH", "BULLISH", "RISK_ON")

        # 1 strong candidate + 1 weak candidate
        strong_sig = _make_test_signal("SOL", score=95, priority=Priority.ELITE, mtf_alignment=True)
        weak_sig = _make_test_signal("DOGE", score=60, priority=Priority.WATCH, mtf_alignment=False)

        raw_candidates = [{"coin": "SOL"}, {"coin": "DOGE"}]
        accepted, all_results = engine.evaluate_candidates(raw_candidates, [strong_sig, weak_sig])

        # Weak candidate must be rejected by strict rejection gate
        accepted_coins = [s.coin for s in accepted]
        assert "SOL" in accepted_coins
        assert "DOGE" not in accepted_coins

    def test_max_signals_cap_at_two(self):
        engine = ConfluenceEngine(strict_threshold=80, max_signals=2)
        engine.update_market_sentiment("BULLISH", "BULLISH", "RISK_ON")

        # 5 strong candidates
        signals = [
            _make_test_signal("BTC", score=95),
            _make_test_signal("ETH", score=92),
            _make_test_signal("SOL", score=90),
            _make_test_signal("AVAX", score=88),
            _make_test_signal("LINK", score=85),
        ]
        raw_candidates = [{"coin": s.coin} for s in signals]

        accepted, _ = engine.evaluate_candidates(raw_candidates, signals)

        # Scanner must cap output at top 2 high-conviction signals
        assert len(accepted) <= 2
        assert accepted[0].coin == "BTC"
        assert accepted[1].coin == "ETH"

    def test_zero_signals_when_market_environment_is_weak(self):
        engine = ConfluenceEngine(strict_threshold=85, max_signals=2)
        # Global market regime is RISK_OFF
        engine.update_market_sentiment("BEARISH", "BEARISH", "RISK_OFF")

        signals = [
            _make_test_signal("BTC", score=90),
            _make_test_signal("ETH", score=88),
        ]
        raw_candidates = [{"coin": s.coin} for s in signals]

        accepted, results = engine.evaluate_candidates(raw_candidates, signals)

        # Zero signals accepted during bad market conditions
        assert len(accepted) == 0
        for r in results:
            assert r.accepted is False

    def test_confluence_breakdown_attached_to_signal(self):
        engine = ConfluenceEngine(strict_threshold=80, max_signals=2)
        engine.update_market_sentiment("BULLISH", "BULLISH", "RISK_ON")

        sig = _make_test_signal("SOL", score=92)
        accepted, _ = engine.evaluate_candidates([{"coin": "SOL"}], [sig])

        assert len(accepted) == 1
        b = accepted[0].confluence_breakdown
        assert b is not None
        assert "chart_score" in b
        assert "indicator_score" in b
        assert "sentiment_score" in b
        assert "news_score" in b
        assert "confluence_score" in b
        assert b["high_conviction_count"] == 1


class TestDeduplicationAndPrecision:

    def test_dedup_key_and_filter(self):
        from v2.services.scanner_service.signal_filter import _dedup_key, deduplicate
        sig1 = _make_test_signal("BTC", score=90)
        sig1.source_bot = "VCP"
        assert _dedup_key(sig1) == "BTC::VCP"

        known = {"BTC::VCP"}
        new_sigs, new_keys = deduplicate([sig1], known)
        assert len(new_sigs) == 0
        assert len(new_keys) == 0

        sig2 = _make_test_signal("ETH", score=90)
        sig2.source_bot = "VCP"
        new_sigs2, new_keys2 = deduplicate([sig2], known)
        assert len(new_sigs2) == 1
        assert new_sigs2[0].coin == "ETH"
        assert new_keys2 == ["ETH::VCP"]

    def test_precision_rules_and_round_qty(self):
        from v2.trading.precision_rules import get_pair_spec, round_qty
        # BTC micro-lot
        btc_qty = round_qty("BTC/INR", 0.00002439)
        assert btc_qty == 0.00002
        assert btc_qty > 0

        # ZEC pair lookup & micro-lot
        spec_zec = get_pair_spec("ZEC/INR")
        assert spec_zec.lot_step_decimals >= 4
        zec_qty = round_qty("ZEC/INR", 0.0004912)
        assert zec_qty == 0.0004
        assert zec_qty > 0

        # Fallback pair with small qty
        custom_qty = round_qty("CUSTOM_COIN/INR", 0.000015)
        assert custom_qty == 0.000015
        assert custom_qty > 0

    def test_format_qty_and_telegram_alerts(self):
        from v2.services.notification_service.formatters import (
            format_qty,
            format_signal_ai_alert,
            format_telegram_orders,
            format_telegram_positions,
        )

        assert format_qty(0.00002) == "0.00002"
        assert format_qty(0.00049) == "0.00049"
        assert format_qty(0.0) == "0"
        assert format_qty(1.500) == "1.5"
        assert format_qty(10.0) == "10"

        # AI alert formatting with metadata
        ai_payload = {
            "coin": "BNB",
            "recommendation": "APPROVE",
            "confidence_score": 92,
            "trend_evaluation": "BULLISH_CONTINUATION",
            "setup_quality": "HIGH_PROBABILITY_BREAKOUT",
            "supporting_factors": ["Multi-timeframe EMA alignment", "Volume expansion"],
            "risk_factors": ["Overhead resistance at ₹55,000"],
        }
        alert = format_signal_ai_alert(ai_payload)
        assert "Trend:</b> BULLISH_CONTINUATION" in alert
        assert "Setup:</b> HIGH_PROBABILITY_BREAKOUT" in alert
        assert "N/A" not in alert

        # Orders formatting
        orders = [
            {"coin": "BTC", "side": "BUY", "qty": 0.00002, "price": 8200000.0, "mode": "PAPER", "status": "FILLED"}
        ]
        orders_text = format_telegram_orders(orders)
        assert "BUY</code> 0.00002 @" in orders_text
        assert "BUY 0.0 @" not in orders_text

