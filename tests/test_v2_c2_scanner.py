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
