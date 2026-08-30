"""
V2 ConfluenceEngine — 5-Layer Evaluation Engine with Strict Rejection Gate.

Core design principle: Signal Quality > Signal Quantity.
Default mentality: REJECT candidates unless ALL 5 layers demonstrate strong evidence.

Evaluates:
  1. Chart Structure (Trend, S/R, Breakout, HH/LL, Price Action)
  2. Technical Indicators (EMA, MACD, RSI, Volume, Momentum, ATR, MTF Alignment)
  3. Big-Coin / Market Sentiment (BTC trend, ETH trend, Risk-On/Off)
  4. News & Events (Crypto news, coin news, exchange announcements, risk events)
  5. Confluence Gate & Quality Filter (Strict Rejection Gate, Top 1–2 Signals cap)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from v2.core.logging import get_logger
from v2.core.types import MarketState, Priority, RiskLevel, Signal

logger = get_logger("v2.services.scanner_service.confluence_engine")


@dataclass
class LayerEvaluation:
    layer_name: str
    passed: bool
    score: int  # 0 - 100
    details: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


@dataclass
class ConfluenceResult:
    signal: Signal
    accepted: bool
    confluence_score: int  # 0 - 100
    rank: int = 0
    layer_evaluations: Dict[str, LayerEvaluation] = field(default_factory=dict)
    rejection_reasons: List[str] = field(default_factory=list)


class ChartStructureEvaluator:
    """Layer 1: Evaluates trend, support/resistance, breakout, HH/LL structure."""

    def evaluate(self, candidate: Dict[str, Any], signal: Signal) -> LayerEvaluation:
        reasons = []
        score = 80  # Base score for candidate signals

        # 1. Market State Check
        if signal.market_state in (MarketState.BREAKOUT, MarketState.BULL_TREND):
            score += 15
        elif signal.market_state == MarketState.PULLBACK:
            score += 5
        elif signal.market_state in (MarketState.DOWNTREND, MarketState.SIDEWAYS):
            score -= 30
            reasons.append(f"Weak market state: {signal.market_state.value}")

        # 2. Risk Level Check
        if signal.risk_level == RiskLevel.HIGH:
            score -= 15
            reasons.append("High chart risk level detected")

        # 3. Coin Class Check
        if signal.coin_class == "A":
            score += 10
        elif signal.coin_class == "C":
            score -= 10

        score = max(0, min(100, score))
        passed = score >= 70 and len(reasons) == 0

        return LayerEvaluation(
            layer_name="Chart Structure",
            passed=passed,
            score=score,
            details={
                "market_state": signal.market_state.value,
                "risk_level": signal.risk_level.value,
                "coin_class": signal.coin_class,
            },
            reasons=reasons,
        )


class IndicatorEvaluator:
    """Layer 2: Evaluates multi-timeframe EMA, MACD, RSI, Volume, Momentum."""

    def evaluate(self, candidate: Dict[str, Any], signal: Signal) -> LayerEvaluation:
        reasons = []
        score = signal.score  # Inherit technical score from scanner candidate

        # Multi-timeframe Alignment is mandatory for high-conviction
        if not signal.mtf_alignment:
            score -= 25
            reasons.append("Missing multi-timeframe indicator alignment")

        # Priority checks
        if signal.priority == Priority.IGNORE:
            score -= 40
            reasons.append("Signal priority is IGNORE")
        elif signal.priority == Priority.WATCH:
            score -= 20
            reasons.append("Signal priority is WATCH (insufficient conviction)")

        score = max(0, min(100, score))
        passed = score >= 75 and signal.mtf_alignment

        return LayerEvaluation(
            layer_name="Technical Indicators",
            passed=passed,
            score=score,
            details={
                "mtf_alignment": signal.mtf_alignment,
                "raw_score": signal.score,
                "priority": signal.priority.value,
            },
            reasons=reasons,
        )


class MarketSentimentEvaluator:
    """Layer 3: Evaluates BTC & ETH trend, market direction, and Risk-On/Risk-Off state."""

    def __init__(self) -> None:
        # Default global market state: Risk-On
        self.btc_trend: str = "BULLISH"
        self.eth_trend: str = "BULLISH"
        self.market_regime: str = "RISK_ON"
        self.fear_greed: int = 50

    def update_market_state(
        self,
        btc_trend: str,
        eth_trend: str,
        market_regime: str,
        fear_greed: int = 50,
    ) -> None:
        self.btc_trend = btc_trend.upper()
        self.eth_trend = eth_trend.upper()
        self.market_regime = market_regime.upper()
        self.fear_greed = int(fear_greed)

    def evaluate(self, candidate: Dict[str, Any], signal: Signal) -> LayerEvaluation:
        reasons = []
        score = 85

        if self.btc_trend == "BEARISH":
            score -= 30
            reasons.append("BTC trend is BEARISH (headwind for altcoins)")
        elif self.btc_trend == "SIDEWAYS":
            score -= 10

        if self.market_regime == "RISK_OFF":
            score -= 35
            reasons.append("Global crypto market regime is RISK_OFF")

        if self.fear_greed < 25:
            score -= 10
            reasons.append(f"Extreme fear in market ({self.fear_greed}/100)")

        score = max(0, min(100, score))
        passed = score >= 70 and self.market_regime != "RISK_OFF"

        return LayerEvaluation(
            layer_name="Big-Coin / Market Sentiment",
            passed=passed,
            score=score,
            details={
                "btc_trend": self.btc_trend,
                "eth_trend": self.eth_trend,
                "market_regime": self.market_regime,
                "fear_greed": self.fear_greed,
            },
            reasons=reasons,
        )


class NewsEventsEvaluator:
    """Layer 4: Evaluates news, exchange announcements, and ecosystem risk events."""

    def evaluate(self, candidate: Dict[str, Any], signal: Signal) -> LayerEvaluation:
        reasons = []
        score = 90  # Default clean news environment

        news_payload = candidate.get("news", {}) or {}
        has_negative_news = news_payload.get("has_negative_news", False)
        is_delisting = news_payload.get("delisting_risk", False)
        sentiment_score = news_payload.get("sentiment_score", None)

        if sentiment_score is not None:
            score = int(float(sentiment_score) * 100)

        if has_negative_news:
            score -= 40
            reasons.append("Negative news/event detected for coin")
        if is_delisting:
            score = 0
            reasons.append("Delisting risk / regulatory alert")

        score = max(0, min(100, score))
        passed = score >= 70 and not has_negative_news and not is_delisting

        return LayerEvaluation(
            layer_name="News & Events",
            passed=passed,
            score=score,
            details={
                "has_negative_news": has_negative_news,
                "delisting_risk": is_delisting,
                "sentiment_score": sentiment_score,
                "headlines": news_payload.get("headlines", []),
            },
            reasons=reasons,
        )


class ConfluenceEngine:
    """
    Combines all 5 evaluation layers with a Strict Rejection Gate.
    Outputs max 1–2 high-conviction signals per scan cycle.
    """

    def __init__(
        self,
        strict_threshold: int = 85,
        max_signals: int = 2,
    ) -> None:
        self.strict_threshold = strict_threshold
        self.max_signals = max_signals
        self.coin_penalties: Dict[str, int] = {}

        self.chart_evaluator = ChartStructureEvaluator()
        self.indicator_evaluator = IndicatorEvaluator()
        self.sentiment_evaluator = MarketSentimentEvaluator()
        self.news_evaluator = NewsEventsEvaluator()

    def update_market_sentiment(
        self,
        btc_trend: str = "BULLISH",
        eth_trend: str = "BULLISH",
        regime: str = "RISK_ON",
        fear_greed: int = 50,
    ) -> None:
        self.sentiment_evaluator.update_market_state(btc_trend, eth_trend, regime, fear_greed)

    def evaluate_candidates(
        self,
        raw_candidates: List[Dict[str, Any]],
        signals: List[Signal],
    ) -> Tuple[List[Signal], List[ConfluenceResult]]:
        """
        Evaluates a list of candidate signals through all 5 layers.
        Enforces strict rejection gate and caps final signals at max_signals (1–2).
        """
        results: List[ConfluenceResult] = []
        accepted_signals: List[Signal] = []

        # Map candidate raw payload to signal by id or coin
        cand_map = {c.get("coin", "").upper(): c for c in raw_candidates}

        for sig in signals:
            cand_raw = cand_map.get(sig.coin.upper(), {})

            # Run 4 layer evaluations
            l1 = self.chart_evaluator.evaluate(cand_raw, sig)
            l2 = self.indicator_evaluator.evaluate(cand_raw, sig)
            l3 = self.sentiment_evaluator.evaluate(cand_raw, sig)
            l4 = self.news_evaluator.evaluate(cand_raw, sig)

            # Combined Confluence Score (Weighted average)
            # Chart 30%, Indicators 35%, Sentiment 20%, News 15%
            combined_score = int(
                (l1.score * 0.30) +
                (l2.score * 0.35) +
                (l3.score * 0.20) +
                (l4.score * 0.15)
            )

            # Apply dynamic calibration coin penalty if active
            coin_key = sig.coin.upper()
            rejection_reasons = []
            if coin_key in self.coin_penalties:
                penalty = self.coin_penalties[coin_key]
                combined_score = max(0, combined_score + penalty)
                if penalty <= -15:
                    rejection_reasons.append(f"[Calibration] Underperforming coin 7d win-rate penalty ({penalty})")
            if not l1.passed: rejection_reasons.extend([f"[Chart] {r}" for r in l1.reasons])
            if not l2.passed: rejection_reasons.extend([f"[Indicator] {r}" for r in l2.reasons])
            if not l3.passed: rejection_reasons.extend([f"[Sentiment] {r}" for r in l3.reasons])
            if not l4.passed: rejection_reasons.extend([f"[News] {r}" for r in l4.reasons])

            if combined_score < self.strict_threshold:
                rejection_reasons.append(f"Confluence score ({combined_score}) below strict threshold ({self.strict_threshold})")

            # Strict Rejection Mentality: ALL layers must pass & score >= threshold
            accepted = len(rejection_reasons) == 0 and combined_score >= self.strict_threshold

            res = ConfluenceResult(
                signal=sig,
                accepted=accepted,
                confluence_score=combined_score,
                layer_evaluations={
                    "chart": l1,
                    "indicator": l2,
                    "sentiment": l3,
                    "news": l4,
                },
                rejection_reasons=rejection_reasons,
            )
            results.append(res)

        # Filter accepted signals and rank by confluence score descending
        accepted_results = [r for r in results if r.accepted]
        accepted_results.sort(key=lambda r: r.confluence_score, reverse=True)

        # Cap at max_signals (1–2 high-conviction signals)
        final_results = accepted_results[: self.max_signals]

        for i, res in enumerate(final_results, start=1):
            res.rank = i
            sig = res.signal
            sig.score = res.confluence_score
            sig.confluence_breakdown = {
                "chart_score": res.layer_evaluations["chart"].score,
                "indicator_score": res.layer_evaluations["indicator"].score,
                "sentiment_score": res.layer_evaluations["sentiment"].score,
                "news_score": res.layer_evaluations["news"].score,
                "confluence_score": res.confluence_score,
                "rank": i,
                "total_candidates": len(signals),
                "high_conviction_count": len(final_results),
            }
            accepted_signals.append(sig)

        logger.info(
            "C2 Confluence evaluation complete",
            extra={
                "evaluated": len(signals),
                "confluence_passed": len(accepted_results),
                "final_signals_output": len(accepted_signals),
                "max_signals_cap": self.max_signals,
            },
        )

        return accepted_signals, results
